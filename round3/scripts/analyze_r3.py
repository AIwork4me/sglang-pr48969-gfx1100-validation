#!/usr/bin/env python3
"""Round 3 independent measurement analysis.

Recomputes every published performance number directly from the raw bench
JSONs under round3/evidence/performance/<cell>/bench_<arm>_r<runno>.json.
Never trusts generated summaries. Handles missing/malformed/non-finite records
as explicit failures. Emits:
  results/per_leg.csv
  results/performance_summary.csv
  results/statistics.json
"""
import glob, json, math, os, sys
from collections import defaultdict
from statistics import median

EV_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "evidence", "performance")
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "results")

CELLS = ["c1", "c2", "c4", "c8", "c16", "c32", "c64",
         "sustained_c1", "memfrac030_c1"]
ARMS = ["main", "old", "new"]

REQUIRED_LEGS = {
    "c1": {"main": 6, "new": 10, "old": 4},
    "c2": {"main": 6, "new": 10, "old": 4},
    "c4": {"main": 6, "new": 10, "old": 4},
    "c8": {"main": 6, "new": 10, "old": 4},
    "c16": {"main": 2, "new": 2, "old": 0},
    "c32": {"main": 2, "new": 2, "old": 0},
    "c64": {"main": 2, "new": 2, "old": 0},
    "sustained_c1": {"main": 4, "new": 6, "old": 2},
    "memfrac030_c1": {"main": 4, "new": 4, "old": 4},
}


# Explicit cycle-position pairing, mirroring run_grid.py's leg schedule.
# Each tuple is (armA, runA, armB, runB) for legs that are CONSECUTIVE positions
# of the same A/B cycle (A-then-B or B-then-A). ABBA/BAAB orientation alternates
# across cycles; pairing is positional, never same-runno across cycles.
PAIRS = {
    "c1": {"main": [("main", 1, "new", 1), ("new", 2, "main", 2),
                     ("new", 5, "main", 3), ("main", 4, "new", 6),
                     ("main", 5, "new", 9), ("new", 10, "main", 6)],
           "old": [("old", 1, "new", 3), ("new", 4, "old", 2),
                    ("new", 7, "old", 3), ("old", 4, "new", 8)]},
    "c2": None, "c4": None, "c8": None,  # same schedule as c1 (filled below)
    "c16": {"main": [("main", 1, "new", 1), ("new", 2, "main", 2)], "old": []},
    "c32": {"main": [("main", 1, "new", 1), ("new", 2, "main", 2)], "old": []},
    "c64": {"main": [("main", 1, "new", 1), ("new", 2, "main", 2)], "old": []},
    "sustained_c1": {"main": [("main", 1, "new", 1), ("new", 2, "main", 2),
                               ("new", 5, "main", 3), ("main", 4, "new", 6)],
                     "old": [("old", 1, "new", 3), ("new", 4, "old", 2)]},
    "memfrac030_c1": {"main": [("main", 1, "new", 1), ("new", 2, "main", 2),
                                ("new", 3, "main", 3), ("main", 4, "new", 4)],
                      "old": [("new", 1, "old", 1), ("old", 2, "new", 2),
                               ("new", 3, "old", 3), ("old", 4, "new", 4)]},
}
for _c in ("c2", "c4", "c8"):
    PAIRS[_c] = PAIRS["c1"]


def load_leg(path):
    try:
        d = json.load(open(path))
    except Exception as e:
        return {"error": f"unparseable: {e!r}"}
    req = ["output_throughput", "mean_ttft_ms", "mean_itl_ms", "completed"]
    for k in req:
        v = d.get(k)
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            return {"error": f"missing/non-finite {k}"}
    return {"output_throughput": d["output_throughput"],
            "input_throughput": d.get("input_throughput"),
            "request_throughput": d.get("request_throughput"),
            "mean_ttft_ms": d["mean_ttft_ms"],
            "median_ttft_ms": d.get("median_ttft_ms"),
            "mean_itl_ms": d["mean_itl_ms"],
            "median_itl_ms": d.get("median_itl_ms"),
            "mean_tpot_ms": d.get("mean_tpot_ms"),
            "completed": d["completed"],
            "duration": d.get("duration")}


def log_ratio_ci(pairs, conf=1.96):
    """Paired log-ratio estimate: geometric-mean ratio + normal CI.
    pairs: list of (a, b) with ratio b/a."""
    if not pairs:
        return None
    lrs = []
    for a, b in pairs:
        if a <= 0 or b <= 0:
            return {"error": "nonpositive leg in pair"}
        lrs.append(math.log(b / a))
    n = len(lrs)
    m = sum(lrs) / n
    var = sum((x - m) ** 2 for x in lrs) / max(1, n - 1)
    se = math.sqrt(var / n)
    return {"n_pairs": n, "geo_mean_ratio": math.exp(m),
            "ci_low": math.exp(m - conf * se) if n > 1 else None,
            "ci_high": math.exp(m + conf * se) if n > 1 else None,
            "paired_ratios": [math.exp(x) for x in lrs]}


def main():
    os.makedirs(RES, exist_ok=True)
    per_leg = []
    data = defaultdict(dict)  # cell -> arm -> {runno: metrics}
    failures = []

    for cell in CELLS:
        cdir = os.path.join(EV_ROOT, cell)
        files = sorted(glob.glob(os.path.join(cdir, "bench_*_r*.json")))
        files = [f for f in files if "_warmup" not in f]
        for f in files:
            base = os.path.basename(f)[len("bench_"):-len(".json")]
            arm, runno = base.rsplit("_r", 1)
            m = load_leg(f)
            row = {"cell": cell, "arm": arm, "run": int(runno),
                   "file": os.path.basename(f)}
            row.update(m)
            per_leg.append(row)
            if "error" in m:
                failures.append({"cell": cell, "leg": base, **m})
            else:
                data[cell].setdefault(arm, {})[int(runno)] = m

    with open(os.path.join(RES, "per_leg.csv"), "w") as fh:
        keys = ["cell", "arm", "run", "file", "output_throughput",
                "input_throughput", "request_throughput", "mean_ttft_ms",
                "median_ttft_ms", "mean_itl_ms", "median_itl_ms",
                "mean_tpot_ms", "completed", "duration", "error"]
        fh.write(",".join(keys) + "\n")
        for r in per_leg:
            fh.write(",".join(str(r.get(k, "")) for k in keys) + "\n")

    summary_rows = []
    stats = {"cells": {}, "failures": failures,
             "missing_legs": [], "arm_totals": {},
             "ttft_outliers": []}
    # pre-declared outlier rule: a leg whose mean TTFT exceeds 5x the cell's
    # cross-arm median TTFT carries a first-use stall (observed only at c4,
    # arm-symmetric); medians are robust to it, paired CIs are reported both
    # raw and TTFT-trimmed.
    for cell, arms in data.items():
        ttfts = sorted(v["mean_ttft_ms"] for a in arms.values() for v in a.values())
        if not ttfts:
            continue
        med_ttft = median(ttfts)
        for arm, legs in arms.items():
            for rn, m in legs.items():
                if m["mean_ttft_ms"] > 5 * med_ttft:
                    m["ttft_outlier"] = True
                    stats["ttft_outliers"].append(
                        {"cell": cell, "leg": f"{arm}_r{rn}",
                         "ttft_ms": m["mean_ttft_ms"], "cell_median_ttft_ms": med_ttft})
    for cell in CELLS:
        cstat = {"legs": {}, "medians": {}, "comparisons": {}}
        for arm in ARMS:
            legs = data.get(cell, {}).get(arm, {})
            n_ok = len(legs)
            n_req = REQUIRED_LEGS.get(cell, {}).get(arm, 0)
            cstat["legs"][arm] = {"valid": n_ok, "required": n_req}
            if n_ok < n_req:
                stats["missing_legs"].append(
                    {"cell": cell, "arm": arm, "valid": n_ok, "required": n_req})
            if legs:
                thr = sorted(v["output_throughput"] for v in legs.values())
                itl = sorted(v["mean_itl_ms"] for v in legs.values())
                ttft = sorted(v["mean_ttft_ms"] for v in legs.values())
                spread = (max(thr) - min(thr)) / min(thr) if len(thr) > 1 else 0.0
                cstat["medians"][arm] = {
                    "output_throughput_median": median(thr),
                    "output_throughput_min": min(thr), "output_throughput_max": max(thr),
                    "repeat_spread_frac": spread,
                    "mean_itl_ms_median": median(itl),
                    "mean_ttft_ms_median": median(ttft)}
                summary_rows.append(
                    {"cell": cell, "arm": arm, "valid_runs": n_ok,
                     "required": n_req,
                     "thr_median": median(thr), "thr_min": min(thr),
                     "thr_max": max(thr), "spread_frac": spread,
                     "itl_median": median(itl), "ttft_median": median(ttft)})
        # cycle-position paired comparisons: explicit PAIRS map mirroring the
        # run_grid.py schedule; each pair joins consecutive legs of one A/B cycle
        for pa, pairs in PAIRS.get(cell, {}).items():
            vals = []
            vals_t = []
            for a1, r1, a2, r2 in pairs:
                A = data.get(cell, {}).get(a1, {}).get(r1)
                B = data.get(cell, {}).get(a2, {}).get(r2)
                if A and B:
                    # ratio is always new/comparator regardless of cycle leg order
                    if a1 == "new":
                        comp, new = B, A
                    else:
                        comp, new = A, B
                    vals.append((comp["output_throughput"], new["output_throughput"]))
                    if not (A.get("ttft_outlier") or B.get("ttft_outlier")):
                        vals_t.append((comp["output_throughput"], new["output_throughput"]))
            cstat["comparisons"][f"new_vs_{pa}_paired"] = log_ratio_ci(vals)
            cstat["comparisons"][f"new_vs_{pa}_pair_count"] = {
                "planned": len(pairs), "matched": len(vals)}
            if len(vals_t) != len(vals):
                cstat["comparisons"][f"new_vs_{pa}_paired_ttft_trimmed"] = log_ratio_ci(vals_t)
        stats["cells"][cell] = cstat

    with open(os.path.join(RES, "performance_summary.csv"), "w") as fh:
        keys = ["cell", "arm", "valid_runs", "required", "thr_median",
                "thr_min", "thr_max", "spread_frac", "itl_median", "ttft_median"]
        fh.write(",".join(keys) + "\n")
        for r in summary_rows:
            fh.write(",".join(str(r.get(k, "")) for k in keys) + "\n")


    for arm in ARMS:
        stats["arm_totals"][arm] = sum(
            1 for r in per_leg if r["arm"] == arm and "error" not in r)

    json.dump(stats, open(os.path.join(RES, "statistics.json"), "w"), indent=2)
    print(json.dumps({"failures": len(failures),
                      "missing_legs": stats["missing_legs"],
                      "arm_totals": stats["arm_totals"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
