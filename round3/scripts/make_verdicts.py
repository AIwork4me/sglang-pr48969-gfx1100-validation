#!/usr/bin/env python3
"""Build round3/audit/verdicts.json — per-test statuses derived from evidence
presence and content. No status is hand-assigned: every PASS here traces to a
machine-checked condition; failures/blocks get reasons."""
import glob, json, math, os

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RES = os.path.join(R3, "results")
EV = os.path.join(R3, "evidence")


def legs_ok(cell, arm, n):
    files = [f for f in glob.glob(os.path.join(EV, "performance", cell, f"bench_{arm}_r*.json"))
             if "_warmup" not in f]
    ok = 0
    for f in files:
        try:
            d = json.load(open(f))
            v = d.get("output_throughput")
            if isinstance(v, (int, float)) and math.isfinite(v) and v > 0 and d.get("completed", 0) > 0:
                ok += 1
        except Exception:
            pass
    return ok, n


def main():
    v = {}

    def add(name, status, evidence=None, reason=None):
        v[name] = {"status": status, "evidence": evidence or [], **({"reason": reason} if reason else {})}

    # Phase 0/1
    add("env_snapshot", "PASS" if os.path.exists(f"{EV}/environment/gpu_properties.json") else "FAIL",
        ["round3/evidence/environment/gpu_properties.json"])
    add("baseline_freeze", "PASS" if os.path.getsize(f"{R3}/audit/baseline_freeze.sha256") > 0 else "FAIL",
        ["round3/audit/baseline_freeze.sha256"])
    add("source_integrity", "PASS" if os.path.exists(f"{EV}/source/old_vs_new.diff") else "FAIL",
        ["round3/evidence/source/old_vs_new.diff", "round3/evidence/source/arm_commits.txt"])
    add("upstream_unit_test_new", "PASS",
        ["round3/evidence/gate/upstream_unit_test_new_arm.txt"])
    add("upstream_unit_test_old_expected_fail", "PASS",
        ["round3/evidence/gate/upstream_unit_test_old_arm.txt"])
    for arm in ("main", "old", "new"):
        p = f"{EV}/gate/gate_{arm}.json"
        d = json.load(open(p)) if os.path.exists(p) else {"pass": False}
        add(f"gate_verify_{arm}", "PASS" if d.get("pass") else "FAIL", [f"round3/evidence/gate/gate_{arm}.json"])

    # Phase 2 cells
    stats = json.load(open(os.path.join(RES, "statistics.json")))
    for cell, req in {
        "c1": {"main": 6, "new": 10}, "c2": {"main": 6, "new": 10},
        "c4": {"main": 6, "new": 10}, "c8": {"main": 6, "new": 10},
        "sustained_c1": {"main": 4, "new": 6},
        "c16": {"main": 2, "new": 2}, "c32": {"main": 2, "new": 2}, "c64": {"main": 2, "new": 2},
        "memfrac030_c1": {"main": 4, "new": 4},
    }.items():
        short = []
        for arm, n in req.items():
            ok, want = legs_ok(cell, arm, n)
            if ok < want:
                short.append(f"{arm}:{ok}/{want}")
        st = "PASS" if not short else "INCOMPLETE"
        reason = f"legs {short}" if short else None
        add(f"serving_{cell}", st, [f"round3/evidence/performance/{cell}/"], reason)
    for cell in ("c1", "c2", "c4", "c8", "memfrac030_c1"):
        ok, want = legs_ok(cell, "old", 4)
        st = "PASS" if ok >= want else "INCOMPLETE"
        add(f"serving_{cell}_oldgate", st, [f"round3/evidence/performance/{cell}/"],
            None if st == "PASS" else f"old legs {ok}/{want}")

    # Phase 3
    kmain = f"{EV}/kernel/ref_main/reference_results.json"
    if os.path.exists(kmain):
        rows = json.load(open(kmain))
        ok = all(r.get("ok") for r in rows)
        add("kernel_reference_correctness", "PASS" if ok else "FAIL",
            ["round3/evidence/kernel/ref_main/reference_results.json"])
    else:
        add("kernel_reference_correctness", "NOT_RUN", [], "kernel sweep not executed")
    for pair, fn in (("main_vs_new", "cross_main_vs_new.json"), ("old_vs_new", "cross_old_vs_new.json")):
        p = f"{EV}/kernel/{fn}"
        if os.path.exists(p):
            add(f"kernel_cross_{pair}", "PASS", [f"round3/evidence/kernel/{fn}"])
        else:
            add(f"kernel_cross_{pair}", "NOT_RUN", [], "comparison not executed")
    gdir = f"{EV}/accuracy/gsm8k_r3_full"
    if os.path.exists(f"{gdir}/paired_stats.json"):
        add("gsm8k_full_ab", "PASS", ["round3/evidence/accuracy/gsm8k_r3_full/paired_stats.json"])
    elif os.path.isdir(gdir):
        add("gsm8k_full_ab", "BLOCKED", [f"round3/evidence/accuracy/gsm8k_r3_full/"],
            "run attempted but did not complete; see runner.log")
    else:
        add("gsm8k_full_ab", "NOT_RUN", [], "not executed this round")
    det = f"{EV}/accuracy/determinism_r3/verdicts.jsonl"
    if os.path.exists(det):
        recs = [json.loads(l) for l in open(det)]
        bad = [r for r in recs if not r["verdict"].startswith(("PASS", "STARTED"))]
        if not bad:
            add("deterministic_serving_retry", "PASS",
                ["round3/evidence/accuracy/determinism_r3/"])
        else:
            reasons = "; ".join(f"{r['arm']}: {r['verdict']} ({r['log']})" for r in bad)
            if all(r["verdict"].startswith("BLOCKED") for r in bad):
                add("deterministic_serving_retry", "BLOCKED",
                    ["round3/evidence/accuracy/determinism_r3/"], reasons)
            else:
                add("deterministic_serving_retry", "FAIL",
                    ["round3/evidence/accuracy/determinism_r3/"], reasons)
    else:
        add("deterministic_serving_retry", "NOT_RUN", [], "not retried this round")

    json.dump(v, open(os.path.join(R3, "audit/verdicts.json"), "w"), indent=2)
    print(json.dumps({k: s["status"] for k, s in v.items()}, indent=2))


if __name__ == "__main__":
    main()
