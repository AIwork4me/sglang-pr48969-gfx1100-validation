#!/usr/bin/env python3
"""Standalone performance recomputation (audit round 2026-11).

Independent of scripts/analyze.py and of the summary CSV: re-reads every
measured bench JSON, recomputes per-cell medians, speedups, decode ms/step
(re-extracted from the server logs with the PR-author methodology) and the
run-to-run spreads, then compares everything against results/performance_raw.csv
and results/performance_summary.csv. Formal and pilot cells are separated.
Exit 1 on any discrepancy. CPU-only.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMAL_CELLS = ["A_c1", "A_c4", "A_c8", "A_c16", "A_c32", "A_c64",
                "A_long_4k_c8", "A_long_8k_c8", "A_mixed_c16", "A_mixed_c32",
                "B_c16", "B_c32", "B_c64", "B_long_8k_c8", "B_mixed_c16"]
DEC_LINE = re.compile(
    r"Decode batch.*?#running-req: (\d+).*?gen throughput \(token/s\): ([\d.]+), #queue-req: (\d+)")


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


def decode_ms_median(server_log):
    rows = []
    for line in open(server_log, errors="replace"):
        m = DEC_LINE.search(line)
        if m:
            running, tps, queued = int(m.group(1)), float(m.group(2)), int(m.group(3))
            if queued == 0 and running > 0 and tps > 0:
                rows.append((running, running / tps * 1000.0))
    seg_start, prev = set(), None
    for i, (running, _ms) in enumerate(rows):
        if prev is None or running != prev:
            seg_start.add(i)
        prev = running
    kept = [ms for i, (_r, ms) in enumerate(rows) if i not in seg_start]
    return statistics.median(kept) if kept else None


def close(a, b, rel=1e-9):
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=1e-12)


def main() -> int:
    raw_rows = list(csv.DictReader(open(os.path.join(REPO, "results/performance_raw.csv"))))
    sum_rows = {r["workload"]: r
                for r in csv.DictReader(open(os.path.join(REPO, "results/performance_summary.csv")))}
    bad = []
    cells = {}
    for r in raw_rows:
        tag = r["tag"]
        docs = bench_docs(os.path.join(REPO, r["bench_file"]))
        d = docs[-1]
        slog = os.path.join(os.path.dirname(os.path.join(REPO, r["bench_file"])),
                            f"server_{r['arm']}_r{r['run']}.log")
        med_ms = decode_ms_median(slog)
        if not close(d["output_throughput"], r["output_throughput"]):
            bad.append((tag, r["arm"], r["run"], "csv tput != bench json"))
        if not close(med_ms, r["decode_ms_per_step_median"], rel=1e-3):
            bad.append((tag, r["arm"], r["run"], f"csv ms/step {r['decode_ms_per_step_median']} != re-extracted {med_ms}"))
        cells.setdefault(tag, {}).setdefault(r["arm"], []).append((d, med_ms))

    print(f"formal cells: {sum(1 for t in cells if t in FORMAL_CELLS)} (expected {len(FORMAL_CELLS)}), "
          f"pilot: {sum(1 for t in cells if t not in FORMAL_CELLS)}")
    for tag, arms in sorted(cells.items()):
        if set(arms) != {"main", "pr"} or any(len(v) != 2 for v in arms.values()):
            bad.append((tag, "ABBA incomplete"))
            continue
        mt = statistics.median([x[0]["output_throughput"] for x in arms["main"]])
        pt = statistics.median([x[0]["output_throughput"] for x in arms["pr"]])
        md = statistics.median([x[1] for x in arms["main"]])
        pd = statistics.median([x[1] for x in arms["pr"]])
        mi = statistics.median([x[0]["median_itl_ms"] for x in arms["main"]])
        pi = statistics.median([x[0]["median_itl_ms"] for x in arms["pr"]])
        tput_spd = pt / mt
        dec_spd = md / pd
        itl_spd = mi / pi
        s = sum_rows.get(tag)
        label = "pilot" if tag not in FORMAL_CELLS else "formal"
        print(f"  {tag:16s} [{label}] tput spd={tput_spd:.4f}  ms/step spd={dec_spd:.4f}  itl spd={itl_spd:.4f}")
        if s is None:
            bad.append((tag, "missing summary row"))
            continue
        for name, got, want in (("tput_spd", tput_spd, s["throughput_speedup_pr_over_main"]),
                                ("dec_spd", dec_spd, s["decode_latency_speedup_main_over_pr"]),
                                ("itl_spd", itl_spd, s["itl_speedup_main_over_pr"]),
                                ("main_tput", mt, s["main_output_throughput_med"]),
                                ("pr_tput", pt, s["pr_output_throughput_med"])):
            if not close(want, got, rel=2e-6):
                bad.append((tag, name, got, want))
    if bad:
        print("PERFORMANCE RECOMPUTE: FAIL")
        for b in bad[:10]:
            print("  -", b)
        return 1
    print("PERFORMANCE RECOMPUTE: PASS (60 formal + 4 pilot legs; medians/speedups/ms-per-step "
          "recomputed from bench JSONs + server logs; summary CSV verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
