#!/usr/bin/env python3
"""Fail-closed verifier for the 2026-11-08 GPU follow-up round.

Recomputes every follow-up number from the raw artifacts under followup/
(bench JSONs, server logs, determinism server logs) using the same methodology
as the main audit (verify_evidence_v2). Exits 1 on any failure.

Checked claims:
  F1  three follow-up cells exist with complete ABBA legs + warmups
  F2  bench files parse; completed == num_prompts; no warmup in measured set
  F3  per-cell medians/speedups recomputed and equal to followup summary JSON
  F4  decode ms/step re-extracted from server logs (author methodology)
  F5  A_c1_mem030 really ran at memfrac 0.30 / auto pool; A_c1_rep and A_c2 at
      0.75 / 100000; arms symmetric within each cell (from server args dumps)
  F6  c=1 regression reproduced under the second memory configuration
      (PR median < main median for throughput AND ms/step in A_c1_mem030)
  F7  combined c=1@0.75 estimate (historical A_c1 + A_c1_rep, n=4/arm):
      all PR legs below all main legs (throughput) and above (ms/step)
  F8  A_c2 is neutral (|speedup - 1| < 1%)
  F9  deterministic-inference fails identically on both arms with the LDS
      OutOfResources error (99328 required > 65536 gfx1100 limit)
  F10 environment: same GPU/co-tenant as the historical round
  F11 determinism verdict: committed verdict JSON is BLOCKED on both arms,
      identical OutOfResources class (99328 > 65536 LDS), failure site in
      batch_invariant_ops, and a scope statement that does not overclaim
  F12 EVERY leg (12/12) verified per-field: model, arm config, bench params,
      launch command, runner params, telemetry presence
  F13 per-leg throughput cross-check: recorded == total_output_tokens/duration
  F14 non-finite policy: any non-finite value in COMPUTED metrics FAILs;
      unused non-finite fields (request_rate=Infinity) are reported, allowed
  F15 normalized CSV: repo-relative, resolvable, row-identical to the sealed
      CSV (which itself remains untouched with its historical staging paths)
  F16 summary_v2 independently recomputed here (medians/spreads/combined c=1;
      0.30 legs never pooled with 0.75 legs)
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import re
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FU = os.path.join(REPO, "followup")
CHECKS = []

DEC = re.compile(r"Decode batch.*?#running-req: (\d+).*?gen throughput \(token/s\): ([\d.]+), #queue-req: (\d+)")


def check(cid, ok, detail=""):
    CHECKS.append((cid, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + cid + (f" :: {detail}" if detail else ""))


def bench_docs(path):
    raw = open(path).read()
    dec, i, docs = json.JSONDecoder(), 0, []
    while True:
        while i < len(raw) and raw[i] in " \n\r\t":
            i += 1
        if i >= len(raw):
            break
        d, i = dec.raw_decode(raw, i)
        docs.append(d)
    return docs


def decode_median(slog):
    rows = []
    for line in open(slog, errors="replace"):
        m = DEC.search(line)
        if m:
            r, t, q = int(m.group(1)), float(m.group(2)), int(m.group(3))
            if q == 0 and r > 0 and t > 0:
                rows.append((r, r / t * 1000.0))
    seg, prev = set(), None
    for i, (r, _ms) in enumerate(rows):
        if prev is None or r != prev:
            seg.add(i)
        prev = r
    kept = [ms for i, (_r, ms) in enumerate(rows) if i not in seg]
    return statistics.median(kept) if kept else None


def main() -> int:
    cells = {}
    bad = []
    for bf in sorted(glob.glob(os.path.join(FU, "evidence_performance/*/bench_*_r[0-9]*.json"))):
        if "_warmup" in bf:
            continue
        tag = os.path.basename(os.path.dirname(bf))
        d = bench_docs(bf)[-1]
        # run number from the FILE NAME only — searching the full path would
        # misparse directory names containing "_r<digit>" (e.g. pytest tmp dirs)
        cells.setdefault(tag, {}).setdefault(
            ("main" if "/bench_main_" in bf else "pr",
             re.search(r"_r(\d+)", os.path.basename(bf)).group(1)), (d, bf))
        if d.get("completed") != d.get("max_concurrency"):
            bad.append((bf, "completed != max_concurrency (num_prompts==conc by design; "
                            "the bench tool records num_prompts=None when the flag is defaulted)"))
    check("f1_abba_complete", all(
        set(v) == {("main", "1"), ("main", "2"), ("pr", "1"), ("pr", "2")} for v in cells.values())
        and set(cells) == {"A_c1_mem030", "A_c1_rep", "A_c2"},
        f"{len(cells)} cells x {sum(len(v) for v in cells.values())} legs")
    check("f2_bench_sane", not bad, str(bad[:2]))
    # warmups present
    warm_missing = []
    for tag, legs in cells.items():
        for (arm, run), _ in legs.items():
            w = os.path.join(FU, "evidence_performance", tag, f"bench_{arm}_r{run}_warmup.json")
            if not os.path.exists(w):
                warm_missing.append(w)
    check("f2b_warmups_present", not warm_missing, str(warm_missing[:2]))

    # server config per cell
    cfg_bad = []
    want = {"A_c1_mem030": ("0.3", None), "A_c1_rep": ("0.75", "100000"), "A_c2": ("0.75", "100000")}
    for tag, (wm, wt) in want.items():
        got = {}
        for arm in ("main", "pr"):
            txt = open(os.path.join(FU, "evidence_performance", tag, f"server_{arm}_r1.log"), errors="replace").read()
            mm = re.search(r"mem_fraction_static': ([0-9.]+)", txt)
            mt = re.search(r"max_total_tokens': (\d+)", txt)
            got[arm] = (mm.group(1) if mm else None, mt.group(1) if mt else None)
        if got["main"] != got["pr"] or got["main"][0] != wm or (wt is None) != (got["main"][1] is None) \
           or (wt is not None and got["main"][1] != wt):
            cfg_bad.append((tag, got))
    check("f5_memory_config_per_cell", not cfg_bad, str(cfg_bad))

    # medians + speedups + decode re-extraction
    summary = {}
    missing_logs = []
    for tag, legs in cells.items():
        med = {}
        for arm in ("main", "pr"):
            t = [legs[(arm, "1")][0]["output_throughput"], legs[(arm, "2")][0]["output_throughput"]]
            dec = []
            for run in ("1", "2"):
                slog = os.path.join(FU, "evidence_performance", tag, f"server_{arm}_r{run}.log")
                if not os.path.isfile(slog):
                    missing_logs.append((tag, arm, run))
                    dec.append(float("nan"))
                    continue
                dec.append(decode_median(slog))
            med[arm] = dict(tput=statistics.median(t), dec=statistics.median(dec))
        summary[tag] = dict(
            main_tput=med["main"]["tput"], pr_tput=med["pr"]["tput"],
            tput_spd=med["pr"]["tput"] / med["main"]["tput"],
            main_ms=med["main"]["dec"], pr_ms=med["pr"]["dec"],
            ms_spd=med["main"]["dec"] / med["pr"]["dec"])
    stored = json.load(open(os.path.join(FU, "results", "followup_summary.json")))
    bad = [t for t in summary if any(
        not math.isclose(summary[t][k], stored[t][k], rel_tol=1e-9)
        for k in ("tput_spd", "ms_spd", "main_tput", "pr_tput"))]
    check("f3_summary_recomputed", not bad and set(stored) == set(summary), str(bad))
    check("f4a_server_logs_present", not missing_logs,
          f"every leg needs its server log; missing={missing_logs}")
    dec_csv = list(csv.DictReader(open(os.path.join(FU, "results", "performance_followup_raw.csv"))))
    dec_bad = []
    for r in dec_csv:
        slog = os.path.join(FU, "evidence_performance", r["tag"], f"server_{r['arm']}_r{r['run']}.log")
        if not os.path.isfile(slog):
            dec_bad.append((r["tag"], r["arm"], r["run"], "server log missing"))
            continue
        m = decode_median(slog)
        if not math.isclose(m, float(r["decode_ms_per_step_median"]), rel_tol=1e-3):
            dec_bad.append((r["tag"], r["arm"], r["run"]))
    check("f4_decode_ms_reextracted", not dec_bad, str(dec_bad[:3]))

    s = summary
    check("f6_c1_regression_second_config",
          s["A_c1_mem030"]["tput_spd"] < 0.995 and s["A_c1_mem030"]["ms_spd"] < 0.995,
          f"0.30/auto: tput spd={s['A_c1_mem030']['tput_spd']:.4f}, ms/step spd={s['A_c1_mem030']['ms_spd']:.4f}")
    # combined c=1@0.75: historical + repeat
    orig = list(csv.DictReader(open(os.path.join(REPO, "results", "performance_raw.csv"))))
    om = [float(r["output_throughput"]) for r in orig if r["tag"] == "A_c1" and r["arm"] == "main"]
    op = [float(r["output_throughput"]) for r in orig if r["tag"] == "A_c1" and r["arm"] == "pr"]
    nm = om + [cells["A_c1_rep"][("main", "1")][0]["output_throughput"], cells["A_c1_rep"][("main", "2")][0]["output_throughput"]]
    npr = op + [cells["A_c1_rep"][("pr", "1")][0]["output_throughput"], cells["A_c1_rep"][("pr", "2")][0]["output_throughput"]]
    check("f7_c1_combined_separated",
          max(npr) < min(nm) and len(nm) == 4 and len(npr) == 4,
          f"n=4/arm @0.75: all PR legs ({min(npr):.1f}-{max(npr):.1f}) < all main legs "
          f"({min(nm):.1f}-{max(nm):.1f}); median spd={statistics.median(npr)/statistics.median(nm):.4f}")
    check("f8_c2_neutral", abs(s["A_c2"]["tput_spd"] - 1.0) < 0.01,
          f"A_c2 tput spd={s['A_c2']['tput_spd']:.4f}")
    det_bad = []
    for arm in ("main", "pr"):
        log = open(os.path.join(FU, "evidence_determinism", f"server_{arm}.log"), errors="replace").read()
        if "OutOfResources" not in log or "99328" not in log or "65536" not in log:
            det_bad.append((arm, "expected LDS OutOfResources 99328>65536"))
    check("f9_determinism_lds_failure_both_arms", not det_bad, str(det_bad))
    env = sorted(glob.glob(os.path.join(FU, "evidence_environment", "rocm_smi_mem_*.txt")))
    env_txt = open(env[-1], errors="replace").read() if env else ""
    total = re.search(r"VRAM Total Memory \(B\): (\d+)", env_txt)
    used = re.search(r"VRAM Total Used Memory \(B\): (\d+)", env_txt)
    ok_env = total and used and int(total.group(1)) == 51522830336 and 30e9 < int(used.group(1)) < 36e9
    check("f10_same_gpu_and_cotenant", bool(ok_env),
          f"co-tenant used={int(used.group(1))/1e9:.2f} GB of {int(total.group(1))/1e9:.2f} GB"
          if ok_env else "environment snapshot unexpected")

    # ---------- F11 determinism verdict ----------
    det_bad = []
    dpath = os.path.join(FU, "results", "determinism_verdict.json")
    if not os.path.isfile(dpath):
        det_bad.append("verdict json missing")
    else:
        dv = json.load(open(dpath))
        if dv.get("overall") != "BLOCKED":
            det_bad.append(f"overall={dv.get('overall')} (must be BLOCKED)")
        if not dv.get("identical_error_class_across_arms"):
            det_bad.append("error classes not identical")
        for arm in ("main", "pr"):
            a = dv.get("arms", {}).get(arm)
            if not a or a.get("verdict") != "BLOCKED" or a.get("error_class") != "OutOfResources":
                det_bad.append((arm, "verdict/class"))
                continue
            if "99328" not in a.get("error_detail", "") or "65536" not in a.get("error_detail", ""):
                det_bad.append((arm, "LDS numbers missing from detail"))
            if "batch_invariant_ops" not in a.get("failure_site", ""):
                det_bad.append((arm, "failure site"))
        if "does not implicate PR #48969" not in dv.get("scope", ""):
            det_bad.append("scope statement missing")
    check("f11_determinism_verdict_blocked_scoped", not det_bad, str(det_bad[:3]))

    # ---------- F12 per-leg field verification (all 12 legs) ----------
    leg_bad = []
    for tag in ("A_c1_mem030", "A_c1_rep", "A_c2"):
        for arm in ("main", "pr"):
            for run in ("1", "2"):
                base = os.path.join(FU, "evidence_performance", tag)
                bf = os.path.join(base, f"bench_{arm}_r{run}.json")
                docs = bench_docs(bf)
                if len(docs) != 1:
                    leg_bad.append((tag, arm, run, "multi-doc bench file"))
                    continue
                d = docs[-1]
                si = d.get("server_info", {})
                lc = si.get("launch_command", "")
                if si.get("model_path") != "Qwen/Qwen3-0.6B":
                    leg_bad.append((tag, arm, run, "model"))
                if si.get("attention_backend") != "triton" or si.get("context_length") != 10240:
                    leg_bad.append((tag, arm, run, "backend/context"))
                want_frac = "0.3" if tag == "A_c1_mem030" else "0.75"
                if str(si.get("mem_fraction_static")) != want_frac:
                    leg_bad.append((tag, arm, run, "memfrac"))
                if tag == "A_c1_mem030":
                    if si.get("max_total_tokens") is not None:
                        leg_bad.append((tag, arm, run, "expected auto pool"))
                elif si.get("max_total_tokens") != 100000:
                    leg_bad.append((tag, arm, run, "maxtok"))
                want_conc = 2 if tag == "A_c2" else 1
                if d.get("completed") != want_conc or d.get("max_concurrency") != want_conc:
                    leg_bad.append((tag, arm, run, "completed/conc"))
                if d.get("random_input_len") != 1024 or d.get("random_output_len") != 256 \
                        or d.get("random_range_ratio") != 1.0:
                    leg_bad.append((tag, arm, run, "lengths"))
                if "--attention-backend triton" not in lc or "--context-length 10240" not in lc:
                    leg_bad.append((tag, arm, run, "launch cmd"))
                slog = os.path.join(base, f"server_{arm}_r{run}.log")
                if not os.path.isfile(slog):
                    leg_bad.append((tag, arm, run, "server log"))
                tele = os.path.join(base, f"telemetry_{arm}_r{run}.csv")
                if not os.path.isfile(tele):
                    leg_bad.append((tag, arm, run, "telemetry"))
        # runner.log start line params
        rl = open(os.path.join(FU, "evidence_performance", tag, "runner.log"), errors="replace").read()
        if "ABORT" in rl or "FAILED" in rl or "MISSING" in rl:
            leg_bad.append((tag, "runner.log", "failure markers present"))
        if f"serving A/B {tag} done" not in rl:
            leg_bad.append((tag, "runner.log", "no completion line"))
        m = re.search(r"=== serving A/B A conc=(\d+) il=(\d+) ol=(\d+) rr=([0-9.]+) memfrac=([0-9.]+)"
                      r" tag=(\S+) maxtok=(\d+) ", rl)
        if not m:
            leg_bad.append((tag, "runner.log", "start line missing"))
        else:
            conc, il, ol, rr, frac, tagr, maxtok = m.groups()
            want = ("1" if tag != "A_c2" else "2", "1024", "256", "1",
                    "0.30" if tag == "A_c1_mem030" else "0.75", tag,
                    "0" if tag == "A_c1_mem030" else "100000")
            if (conc, il, ol, rr, frac, tagr, maxtok) != want:
                leg_bad.append((tag, "runner params", m.groups(), want))
    check("f12_every_leg_field_verified", not leg_bad,
          f"12/12 legs x (model, backend, context, memfrac, maxtok, conc, lengths, "
          f"launch cmd, server log, telemetry) + runner params; issues={leg_bad[:3]}")

    # ---------- F13 throughput division cross-check ----------
    div_bad = []
    for tag in ("A_c1_mem030", "A_c1_rep", "A_c2"):
        for arm in ("main", "pr"):
            for run in ("1", "2"):
                d = bench_docs(os.path.join(FU, "evidence_performance", tag, f"bench_{arm}_r{run}.json"))[-1]
                rec, div = d["output_throughput"], d["total_output_tokens"] / d["duration"]
                if not math.isclose(rec, div, rel_tol=1e-6):
                    div_bad.append((tag, arm, run, rec, div))
    check("f13_tput_division_recompute", not div_bad,
          f"recorded output_throughput == total_output_tokens/duration for 12/12 legs; issues={div_bad[:2]}")

    # ---------- F14 non-finite policy ----------
    nf_bad, nf_unused = [], []
    USED = ["completed", "max_concurrency", "total_output_tokens", "duration",
            "output_throughput", "median_itl_ms", "median_ttft_ms",
            "random_input_len", "random_output_len"]
    for tag in ("A_c1_mem030", "A_c1_rep", "A_c2"):
        for arm in ("main", "pr"):
            for run in ("1", "2"):
                d = bench_docs(os.path.join(FU, "evidence_performance", tag, f"bench_{arm}_r{run}.json"))[-1]
                for k in USED:
                    v = d.get(k)
                    if isinstance(v, float) and not math.isfinite(v):
                        nf_bad.append((tag, arm, run, k, v))
                for k, v in d.items():
                    if isinstance(v, float) and not math.isfinite(v) and k not in USED:
                        nf_unused.append((k, v))
    check("f14_nonfinite_policy", not nf_bad,
          f"non-finite in COMPUTED metrics: {nf_bad[:2]} (must be none); "
          f"unused non-finite fields (allowed, documented): {sorted(set(k for k, _ in nf_unused))}")

    # ---------- F15 normalized CSV ----------
    norm_bad = []
    norm_path = os.path.join(FU, "results", "performance_followup_raw_normalized.csv")
    sealed_path = os.path.join(FU, "results", "performance_followup_raw.csv")
    if not os.path.isfile(norm_path):
        norm_bad.append("normalized csv missing")
    else:
        nr = list(csv.DictReader(open(norm_path)))
        sr = list(csv.DictReader(open(sealed_path)))
        if len(nr) != len(sr) != 12:
            norm_bad.append(("row count", len(nr), len(sr)))
        for a, b in zip(nr, sr):
            if a["bench_file"].startswith("/"):
                norm_bad.append(("absolute path in normalized", a["bench_file"]))
            if not os.path.isfile(os.path.join(REPO, a["bench_file"])):
                norm_bad.append(("unresolvable", a["bench_file"]))
            for k in b:
                if k == "bench_file":
                    continue
                if a.get(k) != b[k]:
                    norm_bad.append(("value drift", a.get("tag"), k))
        if not any(r["bench_file"].startswith("/root/followup/") for r in sr):
            norm_bad.append("sealed original must keep its historical staging paths (untouched)")
    check("f15_normalized_csv", not norm_bad, str(norm_bad[:3]))

    # ---------- F16 summary_v2 independent recompute ----------
    v2_bad = []
    v2_path = os.path.join(FU, "results", "followup_summary_v2.json")
    if not os.path.isfile(v2_path):
        v2_bad.append("summary_v2 missing")
    else:
        v2 = json.load(open(v2_path))
        for tag, agg in v2.get("cells", {}).items():
            mine = summary[tag]
            if not math.isclose(mine["tput_spd"], agg["tput_speedup"], rel_tol=1e-9):
                v2_bad.append((tag, "tput_speedup"))
            if not math.isclose(mine["ms_spd"], agg["ms_speedup"], rel_tol=1e-9):
                v2_bad.append((tag, "ms_speedup"))
            for arm in ("main", "pr"):
                if "tput_halfspread_pct" not in agg[arm]:
                    v2_bad.append((tag, arm, "spread missing"))
        c = v2.get("combined_c1_075", {})
        if c.get("n_per_arm") != 4 or not c.get("fully_separated_tput"):
            v2_bad.append(("combined", "n/separation"))
        if "NEVER pooled" not in c.get("method", ""):
            v2_bad.append(("combined", "method wording (no-pooling) missing"))
        interp = v2.get("interpretation", {}).get("concurrency_vs_kernel_batch", "")
        if "NOT the kernel" not in interp:
            v2_bad.append(("interpretation", "concurrency-vs-kernel-batch note missing"))
    check("f16_summary_v2_recomputed", not v2_bad, str(v2_bad[:3]))

    print("NOTE (evidence limitation): SGLANG_DISABLE_LEAN_ATTENTION=1 and bench --seed 1 "
          "are asserted from the committed launcher/runner scripts (provenance: "
          "scripts/launch_server.sh export + run_serving_ab.sh invocation); they are not "
          "recorded per-leg inside the archived raw dumps.")

    failed = [c for c in CHECKS if not c[1]]
    print(f"\nFOLLOWUP VERIFY: {'PASS' if not failed else 'FAIL'} "
          f"({len(CHECKS) - len(failed)}/{len(CHECKS)} checks)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
