#!/usr/bin/env python3
"""Generate normalized follow-up analysis artifacts from raw evidence (CPU).

Produces (never modifies sealed inputs):
  followup/results/performance_followup_raw_normalized.csv
      — identical rows to the sealed performance_followup_raw.csv but with
        repo-relative bench_file paths (the sealed original records the
        historical staging paths under /root/followup; the normalized copy is
        resolvable from a fresh clone)
  followup/results/followup_summary_v2.json
      — per-leg recomputed table + per-cell aggregates (medians, PR/Main
        ratios, run spreads) + combined-c1 block + interpretation metadata,
        all derived from the raw bench JSONs and server logs

Inputs (read-only): followup/evidence_performance/**, sealed raw CSV, and the
historical results/performance_raw.csv for the combined c=1 block.
"""
from __future__ import annotations

import csv
import json
import os
import re
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FU = os.path.join(REPO, "followup")
DEC = re.compile(r"Decode batch.*?#running-req: (\d+).*?gen throughput \(token/s\): ([\d.]+), #queue-req: (\d+)")
CELLS = ["A_c1_mem030", "A_c1_rep", "A_c2"]


def bench_last_doc(path):
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
    # ---------- normalized CSV ----------
    src_csv = os.path.join(FU, "results", "performance_followup_raw.csv")
    rows = list(csv.DictReader(open(src_csv)))
    norm_path = os.path.join(FU, "results", "performance_followup_raw_normalized.csv")
    staging = "/root/followup/evidence/performance/"
    for r in rows:
        p = r["bench_file"]
        if p.startswith(staging):
            p = "followup/evidence_performance/" + p[len(staging):]
        elif p.startswith("/root/followup/"):
            p = "followup/" + p[len("/root/followup/"):]
        r["bench_file"] = p
        if not os.path.exists(os.path.join(REPO, p)):
            print(f"FAIL: normalized path does not resolve: {p}", file=sys.stderr)
            return 1
    with open(norm_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---------- per-leg recompute ----------
    legs = []
    for cell in CELLS:
        for arm in ("main", "pr"):
            for run in ("1", "2"):
                bf = os.path.join(FU, "evidence_performance", cell, f"bench_{arm}_r{run}.json")
                docs = bench_last_doc(bf)
                if len(docs) != 1:
                    return _fail(f"{bf}: expected 1 JSON doc, got {len(docs)}")
                d = docs[-1]
                slog = os.path.join(os.path.dirname(bf), f"server_{arm}_r{run}.log")
                legs.append({
                    "cell": cell, "arm": arm, "run": run,
                    "completed": d["completed"],
                    "max_concurrency": d["max_concurrency"],
                    "total_output_tokens": d["total_output_tokens"],
                    "duration_s": d["duration"],
                    "output_throughput_recorded": d["output_throughput"],
                    "output_throughput_division": d["total_output_tokens"] / d["duration"],
                    "median_itl_ms": d["median_itl_ms"],
                    "median_ttft_ms": d["median_ttft_ms"],
                    "decode_ms_per_step_reextracted": decode_median(slog),
                })
    cells = {}
    for cell in CELLS:
        sel = [l for l in legs if l["cell"] == cell]
        agg = {}
        for arm in ("main", "pr"):
            t = [l["output_throughput_division"] for l in sel if l["arm"] == arm]
            ms = [l["decode_ms_per_step_reextracted"] for l in sel if l["arm"] == arm]
            itl = [l["median_itl_ms"] for l in sel if l["arm"] == arm]
            agg[arm] = {"tput_median": statistics.median(t), "ms_median": statistics.median(ms),
                        "itl_median": statistics.median(itl),
                        "tput_halfspread_pct": abs(t[0] - t[1]) / statistics.median(t) * 100}
        cells[cell] = {
            **agg,
            "tput_speedup": agg["pr"]["tput_median"] / agg["main"]["tput_median"],
            "ms_speedup": agg["main"]["ms_median"] / agg["pr"]["ms_median"],
            "itl_speedup": agg["main"]["itl_median"] / agg["pr"]["itl_median"],
        }

    # ---------- combined c=1 @0.75 (historical A_c1 + A_c1_rep) ----------
    orig = list(csv.DictReader(open(os.path.join(REPO, "results", "performance_raw.csv"))))
    om = [float(r["output_throughput"]) for r in orig if r["tag"] == "A_c1" and r["arm"] == "main"]
    op = [float(r["output_throughput"]) for r in orig if r["tag"] == "A_c1" and r["arm"] == "pr"]
    nm = om + [l["output_throughput_division"] for l in legs
               if l["cell"] == "A_c1_rep" and l["arm"] == "main"]
    npr = op + [l["output_throughput_division"] for l in legs
                if l["cell"] == "A_c1_rep" and l["arm"] == "pr"]
    combined = {
        "method": ("medians computed WITHIN the 0.75 configuration only (historical A_c1 legs "
                   "+ follow-up A_c1_rep legs, n=4/arm); the 0.30/auto cell (A_c1_mem030) is "
                   "reported separately and NEVER pooled with the 0.75 legs"),
        "n_per_arm": 4,
        "main_legs": nm, "pr_legs": npr,
        "main_median": statistics.median(nm), "pr_median": statistics.median(npr),
        "speedup": statistics.median(npr) / statistics.median(nm),
        "fully_separated_tput": max(npr) < min(nm),
    }

    out = {
        "generated_by": "scripts/generate_followup_analysis.py",
        "inputs": ["followup/evidence_performance/ (raw bench JSONs + server logs)",
                   "followup/results/performance_followup_raw.csv (sealed; only read)",
                   "results/performance_raw.csv (historical, sealed; only read)"],
        "notes": [
            "output_throughput_division = total_output_tokens/duration recomputed per leg "
            "(cross-check of the recorder's output_throughput)",
            "median ITL/TTFT are the bench recorder's per-run aggregates; per-request "
            "latency series were not archived, so they cannot be recomputed from raw "
            "samples (evidence limitation)",
            "decode ms/step re-extracted from server logs with the PR-author methodology",
        ],
        "interpretation": {
            "concurrency_vs_kernel_batch": ("Serving concurrency is NOT the kernel's batch: "
                                            "the grouped decode kernel sees the running/padded "
                                            "batch (cuda-graph buckets 1,2,4,8,...) with "
                                            "head_tiles=8 for this model; any upstream gate "
                                            "change must reason about batch*head_tiles on the "
                                            "kernel's view, never about client concurrency"),
            "labels": {"A_c2": "near-neutral (|spd-1| < 0.5%)", "A_c4_historical": "not a claimed gain (0.998, within spread)",
                       "A_c8_historical": "first clearly positive point (1.047)"},
            "no_gate_code_change": ("This validation repo does not propose a specific gate "
                                    "implementation such as 'if concurrency >= 8'; upstream "
                                    "gate design is a separate task"),
        },
        "legs": legs,
        "cells": cells,
        "combined_c1_075": combined,
    }
    with open(os.path.join(FU, "results", "followup_summary_v2.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {len(legs)} legs, {len(cells)} cells; combined c=1 speedup "
          f"{combined['speedup']:.4f} (separated={combined['fully_separated_tput']})")
    print(f"wrote {os.path.relpath(norm_path, REPO)}")
    return 0


def _fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
