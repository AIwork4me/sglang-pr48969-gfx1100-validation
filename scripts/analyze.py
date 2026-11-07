#!/usr/bin/env python3
"""Phase 8 analysis: performance summary, accuracy summary, plots."""
import csv
import json
import os
import statistics
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PERF = "results/performance_raw.csv"
OUTDIR = "plots"


def load_perf():
    rows = list(csv.DictReader(open(PERF)))
    for r in rows:
        for k in ("concurrency", "output_throughput", "request_throughput",
                  "median_ttft_ms", "p99_ttft_ms", "median_itl_ms", "p99_itl_ms",
                  "median_tpot_ms", "decode_ms_per_step_median"):
            if r.get(k):
                r[k] = float(r[k])
            else:
                r[k] = None
    return rows


def group(rows):
    g = defaultdict(lambda: defaultdict(list))
    for r in rows:
        model = r["tag"].split("_")[0]
        workload = r["tag"]
        g[(model, workload, r["concurrency"])][r["arm"]].append(r)
    return g


def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def spread(vals):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return 0.0
    return (max(vals) - min(vals)) / 2.0


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    rows = load_perf()
    g = group(rows)
    summary = []
    for (model, wl, conc), arms in sorted(g.items(), key=lambda kv: (kv[0][0], kv[0][2] or 0)):
        m, p = arms.get("main", []), arms.get("pr", [])
        if not m or not p:
            continue
        rec = {
            "model": model, "workload": wl, "concurrency": conc,
            "n_runs_main": len(m), "n_runs_pr": len(p),
            "main_output_throughput_med": med([r["output_throughput"] for r in m]),
            "pr_output_throughput_med": med([r["output_throughput"] for r in p]),
            "main_output_throughput_halfspread": spread([r["output_throughput"] for r in m]),
            "pr_output_throughput_halfspread": spread([r["output_throughput"] for r in p]),
            "main_itl_ms_med": med([r["median_itl_ms"] for r in m]),
            "pr_itl_ms_med": med([r["median_itl_ms"] for r in p]),
            "main_ttft_ms_med": med([r["median_ttft_ms"] for r in m]),
            "pr_ttft_ms_med": med([r["median_ttft_ms"] for r in p]),
            "main_decode_ms_step": med([r["decode_ms_per_step_median"] for r in m]),
            "pr_decode_ms_step": med([r["decode_ms_per_step_median"] for r in p]),
        }
        if rec["main_output_throughput_med"] and rec["pr_output_throughput_med"]:
            rec["throughput_speedup_pr_over_main"] = (
                rec["pr_output_throughput_med"] / rec["main_output_throughput_med"]
            )
        if rec["main_decode_ms_step"] and rec["pr_decode_ms_step"]:
            rec["decode_latency_speedup_main_over_pr"] = (
                rec["main_decode_ms_step"] / rec["pr_decode_ms_step"]
            )
        if rec["main_itl_ms_med"] and rec["pr_itl_ms_med"]:
            rec["itl_speedup_main_over_pr"] = rec["main_itl_ms_med"] / rec["pr_itl_ms_med"]
        summary.append(rec)
    with open("results/performance_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary[0].keys())
        w.writeheader()
        w.writerows(summary)
    print(f"wrote {len(summary)} summary rows")

    # plots: only the 1024/256/rr1 main grid per model
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    colors = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green"}
    for model in ("A", "B", "C"):
        grid = [r for r in summary if r["model"] == model and r["workload"] == f"{model}_c{int(r['concurrency'])}"]
        grid.sort(key=lambda r: r["concurrency"])
        if not grid:
            continue
        xs = [r["concurrency"] for r in grid]
        axes[0][0].plot(xs, [r["main_output_throughput_med"] for r in grid], "o--", color=colors[model], label=f"{model} main")
        axes[0][0].plot(xs, [r["pr_output_throughput_med"] for r in grid], "o-", color=colors[model], label=f"{model} PR")
        axes[0][1].errorbar(xs, [r["throughput_speedup_pr_over_main"] for r in grid],
                            yerr=[max(r["main_output_throughput_halfspread"] / r["main_output_throughput_med"],
                                      r["pr_output_throughput_halfspread"] / r["pr_output_throughput_med"]) for r in grid],
                            fmt="o-", color=colors[model], label=model)
        axes[1][0].plot(xs, [r["main_itl_ms_med"] for r in grid], "o--", color=colors[model], label=f"{model} main")
        axes[1][0].plot(xs, [r["pr_itl_ms_med"] for r in grid], "o-", color=colors[model], label=f"{model} PR")
        axes[1][1].plot(xs, [r["main_decode_ms_step"] for r in grid], "o--", color=colors[model], label=f"{model} main")
        axes[1][1].plot(xs, [r["pr_decode_ms_step"] for r in grid], "o-", color=colors[model], label=f"{model} PR")
    axes[0][0].set_title("Output throughput vs concurrency (1024in/256out/rr1)")
    axes[0][0].set_ylabel("output tok/s")
    axes[0][1].set_title("PR/Main throughput speedup vs concurrency")
    axes[0][1].axhline(1.0, color="gray", lw=0.5)
    axes[0][1].set_ylabel("speedup (PR/Main)")
    axes[1][0].set_title("Median ITL vs concurrency")
    axes[1][0].set_ylabel("ms")
    axes[1][1].set_title("Decode ms/step vs concurrency (queue-req:0 median)")
    axes[1][1].set_ylabel("ms/step")
    for ax in axes.flat:
        ax.set_xlabel("concurrency")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{OUTDIR}/throughput_latency_grids.png", dpi=140)
    print("wrote plots")

    # accuracy summary
    acc_rows = []
    import glob
    for met in sorted(glob.glob("evidence/accuracy/*/run_*/sgl_eval_gsm8k_*/metrics.json")):
        d = json.load(open(met))
        parts = met.split(os.sep)
        tag = parts[2]
        arm = parts[3].replace("run_", "")
        acc_rows.append({
            "tag": tag, "arm": arm,
            "n_examples": d.get("num_examples"),
            "score": d["aggregate"]["score"],
            "error_rate": d["aggregate"]["error_rate"],
            "stop_rate": d["aggregate"]["stop_rate"],
            "truncated_rate": d["aggregate"]["truncated_rate"],
            "max_tokens": d["gen"]["max_tokens"], "temperature": d["gen"]["temperature"],
            "seed": d["gen"].get("seed"), "latency_s": d.get("latency_seconds"),
        })
    with open("results/accuracy_summary.csv", "w", newline="") as f:
        if acc_rows:
            w = csv.DictWriter(f, fieldnames=acc_rows[0].keys())
            w.writeheader()
            w.writerows(acc_rows)
    print(f"wrote {len(acc_rows)} accuracy rows")
    for r in acc_rows:
        print(r["tag"], r["arm"], r["n_examples"], f"{r['score']*100:.2f}%")


if __name__ == "__main__":
    main()
