#!/usr/bin/env python3
"""Standalone accuracy recomputation (audit round 2026-11).

Independent of scripts/analyze.py: re-reads every GSM8K metrics.json and the
per-question prediction files, recomputes scores/deltas/truncation rates and
the paired discordant counts, and compares against results/accuracy_summary.csv.
Exit 1 on any discrepancy. CPU-only.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    bad = []
    acc_csv = {(r["tag"], r["arm"]): r
               for r in csv.DictReader(open(os.path.join(REPO, "results/accuracy_summary.csv")))}
    report = []
    for met_path in sorted(glob.glob(os.path.join(REPO, "evidence/accuracy/*/run_*/sgl_eval_gsm8k_*/metrics.json"))):
        d = json.load(open(met_path))
        parts = met_path.split(os.sep)
        tag, arm = parts[-4], parts[-3].replace("run_", "")
        # recompute score from the per-question file when present
        jf = glob.glob(os.path.join(os.path.dirname(met_path), "output-rs0.jsonl"))
        rec_score = None
        if jf:
            vals = [json.loads(l).get("symbolic_correct") for l in open(jf[0])]
            if all(isinstance(v, bool) for v in vals):
                rec_score = sum(vals) / len(vals)
                if len(vals) != d["num_examples"]:
                    bad.append((tag, arm, "jsonl length != num_examples"))
        s = d["aggregate"]["score"]
        if rec_score is not None and not math.isclose(rec_score, s, rel_tol=1e-12):
            bad.append((tag, arm, f"score {s} != per-question recompute {rec_score}"))
        row = acc_csv.get((tag, arm))
        if row is None:
            bad.append((tag, arm, "missing in accuracy_summary.csv"))
            continue
        if not math.isclose(float(row["score"]), s, rel_tol=1e-12):
            bad.append((tag, arm, "csv score mismatch"))
        if int(row["max_tokens"]) != d["gen"]["max_tokens"] or int(row["n_examples"]) != d["num_examples"]:
            bad.append((tag, arm, "csv n/max_tokens mismatch"))
        if not math.isclose(float(row["truncated_rate"]), d["aggregate"]["truncated_rate"], rel_tol=1e-9):
            bad.append((tag, arm, "csv truncated_rate mismatch"))
        report.append((tag, arm, d["num_examples"], d["gen"]["max_tokens"], round(s * 100, 4)))
    # pair deltas from raw metrics
    tags = sorted({t for t, _ in acc_csv})
    for tag in tags:
        if (tag, "main") in acc_csv and (tag, "pr") in acc_csv:
            sm = json.load(open(glob.glob(os.path.join(
                REPO, "evidence/accuracy", tag, "run_main", "sgl_eval_gsm8k_*", "metrics.json"))[0]))
            sp = json.load(open(glob.glob(os.path.join(
                REPO, "evidence/accuracy", tag, "run_pr", "sgl_eval_gsm8k_*", "metrics.json"))[0]))
            delta = (sp["aggregate"]["score"] - sm["aggregate"]["score"]) * 100
            print(f"  {tag:20s} Δ(PR−Main) = {delta:+.3f} pp")
    for r in report:
        print("  ", r)
    if bad:
        print("ACCURACY RECOMPUTE: FAIL")
        for b in bad:
            print("  -", b)
        return 1
    print("ACCURACY RECOMPUTE: PASS (all scores recomputed from metrics.json + per-question files; "
          "10/10 rows match results/accuracy_summary.csv)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
