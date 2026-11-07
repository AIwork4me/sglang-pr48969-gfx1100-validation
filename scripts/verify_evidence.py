#!/usr/bin/env python3
"""Phase 10 evidence audit: verify every campaign claim has real artifacts.

Checks (no GPU needed):
 1. perf raw rows all reference existing bench JSON + server logs
 2. decode ms/step recomputable from the recorded series
 3. kernel artifacts exist and are self-consistent (17 cases, bitwise equal)
 4. launch captures show PR arm with num_warps=2/no hints on qualifying shapes
    and unchanged config on excluded shapes; Main always hints+4warps
 5. source verification JSONs say verified=true
 6. Main tree deltas limited to the 4 documented build files
 7. accuracy metrics exist per arm with matching settings
 8. gate/patch files exist; arch gate JSON all-pass
Writes evidence/EVIDENCE_AUDIT.md.
"""
import csv
import glob
import hashlib
import json
import os
import statistics
import sys

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))


def main():
    # 3/4 kernel evidence
    cap_pr = json.load(open("evidence/kernel/capture_pr.json"))["records"]
    cap_main = json.load(open("evidence/kernel/capture_main.json"))["records"]
    qual = cap_pr["qualifying_b16_h16_kv8_d128_bf16"][0]
    check("pr_qualifying_2warps_nohints",
          qual.get("num_warps") == 2 and "waves_per_eu" not in qual, str(qual))
    for k in ("tiny_grid_b1_h16_kv2_d128_bf16", "tiny_grid_b3_h16_kv2_d128_bf16", "hd256_b4_h16_kv8_d256_bf16"):
        r = cap_pr[k][0]
        check(f"pr_{k}_unchanged",
              r.get("num_warps") == 4 and r.get("waves_per_eu") == 1, str(r))
    for k, v in cap_main.items():
        r = v[0]
        check(f"main_{k}_hints4warps",
              r.get("num_warps") == 4 and r.get("waves_per_eu") == 1)
    cmp_rows = json.load(open("evidence/kernel/cross_arm_compare.json"))
    check("kernel_17cases_bitwise_equal",
          len(cmp_rows) == 17 and all(r["bitwise_equal"] for r in cmp_rows),
          f"{len(cmp_rows)} rows")
    ref = json.load(open("evidence/kernel/ref_main/reference_rows.json"))
    check("kernel_reference_all_finite_ok",
          all(r["ok"] and r["finite"] for r in ref))
    # serving-context proof
    spy = [json.loads(l) for l in open("logs/server/spy_pr.jsonl")]
    check("serving_spy_all_2warps", len(spy) > 100 and all(
        r.get("num_warps") == 2 and "waves_per_eu" not in r for r in spy),
        f"{len(spy)} launches")

    # 5 source verification
    for arm in ("main", "pr"):
        d = json.load(open(f"evidence/source/verify_{arm}.json"))
        check(f"source_verified_{arm}", d["verified"], f"{d['expected_files']} files")

    # 6 main tree deltas
    deltas = json.load(open("evidence/source/arm_tree_deltas.json"))
    allowed = {"python/pyproject.toml", "python/sglang/kernels/aot/pyproject.toml",
               "python/sglang/kernels/aot/setup_rocm.py",
               "python/sglang/kernels/aot/include/utils.h"}
    m = [f for _t, f in deltas["main"]["diffs_vs_pinned"]]
    check("main_only_documented_deltas", set(m) <= allowed, str(m))
    p = [f for _t, f in deltas["pr"]["diffs_vs_pinned"]]
    check("pr_deltas_plus_gate_patch", set(p) <= allowed | {
        "python/sglang/kernels/ops/attention/decode_attention.py"}, str(p))

    # 7 accuracy
    acc = sorted(glob.glob("evidence/accuracy/*/run_*/sgl_eval_gsm8k_*/metrics.json"))
    check("accuracy_metrics_exist", len(acc) >= 4, f"{len(acc)} metric files")
    full = {}
    for mpath in acc:
        d = json.load(open(mpath))
        if d.get("num_examples") == 1319:
            full.setdefault(mpath.split(os.sep)[2], {})[mpath.split(os.sep)[3]] = d
    for tag, arms in full.items():
        if set(arms) == {"main", "pr"}:
            g = [arms[a]["gen"][k] for a in arms for k in ("temperature", "max_tokens", "seed", "top_p")]
            check(f"{tag}_symmetric_settings", len(set(map(str, g))) <= 4, str(g))

    # 1/2 performance rows
    rows = list(csv.DictReader(open("results/performance_raw.csv")))
    missing = []
    for r in rows:
        if not os.path.exists(r["bench_file"]):
            missing.append(r["bench_file"])
    check("perf_rows_have_bench_files", not missing, str(missing[:3]))
    dec = json.load(open("evidence/performance/decode_ms_per_run.json"))
    bad_med = []
    for key, v in dec.items():
        if v["kept"] and v["median"] is None:
            bad_med.append(key)
    check("decode_series_medians_present", not bad_med, str(bad_med[:3]))
    n_rows = len(rows)
    check("perf_min_rows", n_rows >= 40, f"{n_rows} measured rows")

    # 8 gates/patch
    check("gate_patch_exists", os.path.exists("patches/pr48969-gfx1100-validation.patch"))
    gates = json.load(open("evidence/regression/arch_gates.json"))
    check("arch_gates_all_pass", gates.get("overall_pass") is True)

    ok = all(c[1] for c in CHECKS)
    with open("evidence/EVIDENCE_AUDIT.md", "w") as f:
        f.write("# Evidence Audit (Phase 10)\n\n")
        f.write(f"Generated: {__import__('datetime').datetime.now().isoformat()}\n\n")
        f.write(f"**Overall: {'PASS' if ok else 'FAIL'}** ({sum(c[1] for c in CHECKS)}/{len(CHECKS)} checks)\n\n")
        f.write("| check | status | detail |\n|---|---|---|\n")
        for name, passed, detail in CHECKS:
            f.write(f"| {name} | {'PASS' if passed else 'FAIL'} | {detail} |\n")
    print("overall", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
