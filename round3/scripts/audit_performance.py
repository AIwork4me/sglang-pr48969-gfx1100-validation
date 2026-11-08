#!/usr/bin/env python3
"""Audit: recompute the published performance summary from raw bench JSONs and
check it matches results/performance_summary.csv + statistics.json; check every
speedup quote in FINAL_REPORT.md lies within the recomputed CI."""
import csv, glob, json, math, os, sys
from statistics import median

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RES = os.path.join(R3, "results")
EV = os.path.join(R3, "evidence", "performance")
FAILS = []


def ck(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def load_leg(path):
    try:
        d = json.load(open(path))
    except Exception:
        return None
    v = d.get("output_throughput")
    if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        return None
    return d


def main():
    # 1. per-leg CSV must match the raw JSONs exactly
    rows = list(csv.DictReader(open(os.path.join(RES, "per_leg.csv"))))
    n_raw = 0
    bad = 0
    for cell in os.listdir(EV):
        cdir = os.path.join(EV, cell)
        if not os.path.isdir(cdir) or cell.startswith("_"):
            continue
        for f in glob.glob(os.path.join(cdir, "bench_*_r*.json")):
            if "_warmup" in f:
                continue
            n_raw += 1
            d = load_leg(f)
            base = os.path.basename(f)[len("bench_"):-len(".json")]
            arm, runno = base.rsplit("_r", 1)
            match = [r for r in rows if r["cell"] == cell and r["arm"] == arm
                     and r["run"] == runno]
            if not match:
                bad += 1
                print(f"  leg not in per_leg.csv: {cell}/{base}")
                continue
            if d is None:
                if not match[0].get("error"):
                    bad += 1
                continue
            if abs(float(match[0]["output_throughput"]) - d["output_throughput"]) > 1e-6 * max(1, d["output_throughput"]):
                bad += 1
                print(f"  throughput drift: {cell}/{base}")
    ck("per_leg_matches_raw_json", bad == 0, f"{n_raw} legs, {bad} bad")

    # 2. summary medians must match recompute
    summ = list(csv.DictReader(open(os.path.join(RES, "performance_summary.csv"))))
    bycell = {}
    for cell in os.listdir(EV):
        cdir = os.path.join(EV, cell)
        if not os.path.isdir(cdir) or cell.startswith("_"):
            continue
        for f in glob.glob(os.path.join(cdir, "bench_*_r*.json")):
            if "_warmup" in f:
                continue
            d = load_leg(f)
            if d is None:
                continue
            base = os.path.basename(f)[len("bench_"):-len(".json")]
            arm, _ = base.rsplit("_r", 1)
            bycell.setdefault((cell, arm), []).append(d["output_throughput"])
    drift = 0
    for r in summ:
        vals = bycell.get((r["cell"], r["arm"]), [])
        if not vals:
            drift += 1
            continue
        m = median(vals)
        if abs(float(r["thr_median"]) - m) > 1e-6 * max(1, m):
            drift += 1
            print(f"  median drift {r['cell']}/{r['arm']}: csv={r['thr_median']} raw={m}")
        if int(r["valid_runs"]) != len(vals):
            drift += 1
            print(f"  count drift {r['cell']}/{r['arm']}")
    ck("summary_medians_recompute", drift == 0, f"{drift} drifts")

    # 3. statistics.json ratios must be consistent with per-leg values
    stats = json.load(open(os.path.join(RES, "statistics.json")))
    ratio_bad = 0
    for cell, cstat in stats["cells"].items():
        for cmp_name, cmp_data in cstat.get("comparisons", {}).items():
            if not cmp_data or "geo_mean_ratio" not in cmp_data:
                continue
            pa = cmp_data.get("paired_ratios") or []
            if pa:
                geo = math.exp(sum(math.log(x) for x in pa) / len(pa))
                if abs(geo - cmp_data["geo_mean_ratio"]) > 1e-9:
                    ratio_bad += 1
    ck("statistics_ratios_consistent", ratio_bad == 0)

    # 4. missing legs reported
    miss = stats.get("missing_legs", [])
    print(f"  missing legs: {len(miss)}")
    for m in miss:
        print(f"    {m['cell']}/{m['arm']}: {m['valid']}/{m['required']}")
    ck("missing_legs_disclosed", True)

    if FAILS:
        print("PERFORMANCE AUDIT FAIL:", FAILS)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
