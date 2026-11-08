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
        cells.setdefault(tag, {}).setdefault(
            ("main" if "/bench_main_" in bf else "pr", re.search(r"_r(\d+)", bf).group(1)), (d, bf))
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
    for tag, legs in cells.items():
        med = {}
        for arm in ("main", "pr"):
            t = [legs[(arm, "1")][0]["output_throughput"], legs[(arm, "2")][0]["output_throughput"]]
            dec = []
            for run in ("1", "2"):
                slog = os.path.join(FU, "evidence_performance", tag, f"server_{arm}_r{run}.log")
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
    dec_csv = list(csv.DictReader(open(os.path.join(FU, "results", "performance_followup_raw.csv"))))
    dec_bad = []
    for r in dec_csv:
        slog = os.path.join(FU, "evidence_performance", r["tag"], f"server_{r['arm']}_r{r['run']}.log")
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

    failed = [c for c in CHECKS if not c[1]]
    print(f"\nFOLLOWUP VERIFY: {'PASS' if not failed else 'FAIL'} "
          f"({len(CHECKS) - len(failed)}/{len(CHECKS)} checks)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
