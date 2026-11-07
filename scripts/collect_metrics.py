#!/usr/bin/env python3
"""Collect Phase 4/5 artifacts into results/performance_raw.csv and decode
ms/step series.

bench JSON fields (sglang.benchmark.serving): includes
  completed, total_input_tokens, total_output_tokens,
  output_throughput, request_throughput, mean_ttft_ms, median_ttft_ms,
  p99_ttft_ms, mean_itl_ms, median_itl_ms, p99_itl_ms, mean_tpot_ms,
  median_tpot_ms ...

Decode ms/step per the PR author's documented methodology:
  from server log 'Decode batch' lines with '#queue-req: 0',
  ms/step = running-req / gen throughput (tok/s),
  dropping the first line of each contiguous segment, median per run.
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics

DEC = re.compile(
    r"Decode batch.*?#running-req: (\d+).*?gen throughput \(token/s\): ([\d.]+), #queue-req: (\d+)"
)


def decode_ms_series(server_log_path):
    rows = []
    for line in open(server_log_path, errors="replace"):
        m = DEC.search(line)
        if m:
            running, tps, queued = int(m.group(1)), float(m.group(2)), int(m.group(3))
            if queued == 0 and running > 0 and tps > 0:
                rows.append((running, tps, running / tps * 1000.0))
    # segment split: contiguous rows where running-req constant; drop first of each
    seg_start_idx = set()
    prev = None
    for i, (running, _t, _m) in enumerate(rows):
        if prev is None or running != prev:
            seg_start_idx.add(i)
        prev = running
    kept = [m for i, (_r, _t, m) in enumerate(rows) if i not in seg_start_idx]
    return rows, kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perf-dir", default="evidence/performance")
    ap.add_argument("--out-csv", default="results/performance_raw.csv")
    ap.add_argument("--out-decode", default="evidence/performance/decode_ms_per_run.json")
    a = ap.parse_args()

    bench_files = sorted(
        glob.glob(os.path.join(a.perf_dir, "*", "bench_*_r[0-9]*.json"))
    )
    bench_files = [f for f in bench_files if "_warmup" not in f]
    out_rows = []
    decode_out = {}
    for bf in bench_files:
        run_dir = os.path.dirname(bf)
        tag = os.path.basename(run_dir)
        base = os.path.basename(bf)[:-5]
        arm = "main" if base.startswith("bench_main") else "pr"
        m = re.match(r"bench_(main|pr)_r(\d+)", base)
        runno = m.group(2)
        raw = open(bf).read()
        dec = json.JSONDecoder()
        d = None
        i = 0
        while True:
            while i < len(raw) and raw[i] in " \n\r\t":
                i += 1
            if i >= len(raw):
                break
            d, i = dec.raw_decode(raw, i)
        # server log for the same leg
        slog = os.path.join(run_dir, f"server_{arm}_r{runno}.log")
        ms_rows, ms_kept = ([], [])
        if os.path.exists(slog):
            ms_rows, ms_kept = decode_ms_series(slog)
        med_ms = statistics.median(ms_kept) if ms_kept else None
        row = {
            "tag": tag,
            "arm": arm,
            "run": runno,
            "concurrency": d.get("max_concurrency"),
            "num_prompts": d.get("num_prompts") or d.get("completed"),
            "completed": d.get("completed"),
            "output_throughput": d.get("output_throughput"),
            "request_throughput": d.get("request_throughput"),
            "median_ttft_ms": d.get("median_ttft_ms"),
            "p99_ttft_ms": d.get("p99_ttft_ms"),
            "mean_ttft_ms": d.get("mean_ttft_ms"),
            "median_itl_ms": d.get("median_itl_ms"),
            "p99_itl_ms": d.get("p99_itl_ms"),
            "mean_itl_ms": d.get("mean_itl_ms"),
            "median_tpot_ms": d.get("median_tpot_ms"),
            "mean_tpot_ms": d.get("mean_tpot_ms"),
            "decode_ms_per_step_median": med_ms,
            "decode_log_lines_used": len(ms_kept),
            "input_len": (d.get("random_input_len") or ""),
            "bench_file": bf,
        }
        out_rows.append(row)
        decode_out[f"{tag}/{arm}/r{runno}"] = {
            "all_rows": [round(m, 3) for _r, _t, m in ms_rows],
            "kept": [round(m, 3) for m in ms_kept],
            "median": med_ms,
        }
    os.makedirs(os.path.dirname(a.out_csv), exist_ok=True)
    with open(a.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_rows[0].keys())
        w.writeheader()
        w.writerows(out_rows)
    json.dump(decode_out, open(a.out_decode, "w"), indent=2)
    print(f"wrote {len(out_rows)} rows to {a.out_csv}")
    for r in out_rows:
        print(
            f"{r['tag']:24s} {r['arm']:4s} r{r['run']} c={r['concurrency']} "
            f"out_tput={r['output_throughput']} med_itl={r['median_itl_ms']} "
            f"ms/step={r['decode_ms_per_step_median']}"
        )


if __name__ == "__main__":
    main()
