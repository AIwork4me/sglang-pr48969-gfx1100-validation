#!/usr/bin/env python3
"""Paired McNemar statistics for the round3 GSM8K A/B runs (sgl-eval 0.1.3
schema: metrics.json aggregate.score, output-rs0.jsonl per-question records
with `id` / `symbolic_correct` / `finish_reason`)."""
import glob, json, os, sys
from math import comb

out = sys.argv[1]
rows = {}
for arm in ("main", "new"):
    hits = glob.glob(os.path.join(out, f"run_{arm}", "sgl_eval_gsm8k_*"))
    if not hits:
        print(f"no run dir for {arm}")
        sys.exit(1)
    run = hits[0]
    m = json.load(open(os.path.join(run, "metrics.json")))
    correct, trunc = {}, {}
    for line in open(os.path.join(run, "output-rs0.jsonl")):
        d = json.loads(line)
        correct[str(d["id"])] = bool(d["symbolic_correct"])
        trunc[str(d["id"])] = d.get("finish_reason") == "length"
    rows[arm] = {"metrics": m, "correct": correct, "trunc": trunc,
                 "metrics_path": os.path.relpath(os.path.join(run, "metrics.json"), out)}

mA, mB = rows["main"]["metrics"], rows["new"]["metrics"]
res = {
    "main_score": mA["aggregate"]["score"],
    "new_score": mB["aggregate"]["score"],
    "main_truncated_rate": mA["aggregate"]["truncated_rate"],
    "new_truncated_rate": mB["aggregate"]["truncated_rate"],
    "main_gen": {k: mA["gen"][k] for k in ("max_tokens", "temperature", "seed", "top_p")},
    "new_gen": {k: mB["gen"][k] for k in ("max_tokens", "temperature", "seed", "top_p")},
    "settings_identical": mA["gen"] == mB["gen"],
    "n_examples": (mA["num_examples"], mB["num_examples"]),
    "model": mA["model"],
    "ns_commit_sha": mA["ns_commit_sha"],
    "sgl_eval_version": mA["sgl_eval_version"],
}
qa, qb = rows["main"]["correct"], rows["new"]["correct"]
common = sorted(set(qa) & set(qb))
if common:
    b01 = sum(1 for k in common if not qa[k] and qb[k])
    b10 = sum(1 for k in common if qa[k] and not qb[k])
    n = b01 + b10
    if n:
        k_min = min(b01, b10)
        p = min(1.0, 2 * sum(comb(n, k) for k in range(0, k_min + 1)) / 2 ** n)
    else:
        p = 1.0
    res.update({
        "n_paired": len(common),
        "discordant": n, "main_wrong_new_right": b01,
        "main_right_new_wrong": b10, "mcnemar_exact_p": p,
        "truncation_agreement": sum(1 for k in common
                                    if rows["main"]["trunc"][k] == rows["new"]["trunc"][k]),
    })
else:
    res["n_paired"] = 0
json.dump(res, open(os.path.join(out, "paired_stats.json"), "w"), indent=2)
print(json.dumps(res, indent=2))
