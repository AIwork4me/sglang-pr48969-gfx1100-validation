#!/usr/bin/env python3
"""Audit: anti-forgery recompute of the published performance results.

Everything published in results/ is re-derived from the raw bench JSONs and
the execution order log, never from other derived files:
  1. order.jsonl must cover every raw leg 1:1 (and vice versa), all 'ok';
  2. per_leg.csv must be a bijection with the raw legs (no extra, duplicate
     or missing rows) and carry the raw values;
  3. performance_summary.csv medians/min/max/valid_runs must recompute;
  4. statistics.json paired ratios, geometric means, CIs and pair counts must
     recompute from the RAW legs under the declared PAIRS schedule, and every
     pair must be adjacent in the original execution order;
  5. missing_legs must equal the independently recomputed shortfall;
  6. arm totals must match the certificate's measured totals.

The log-ratio CI here mirrors the campaign's pre-declared statistical method
(paired log-ratio, normal approximation, conf=1.96) — no new statistics."""
import csv, glob, json, math, os, sys
from statistics import median

R3 = os.environ.get("AUDIT_R3_ROOT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")
CAMP = os.path.normpath(os.path.join(R3, ".."))
RES = os.path.join(R3, "results")
EV = os.path.join(R3, "evidence", "performance")
sys.path.insert(0, os.path.join(R3, "scripts"))
from analyze_r3 import CELLS, REQUIRED_LEGS, PAIRS  # declared campaign schedule

FAILS = []
REL_TOL = 1e-9
MED_TOL = 1e-6


def ck(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def close(a, b, tol=REL_TOL):
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def load_leg(path):
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception:
        return None
    v = d.get("output_throughput")
    if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        return None
    return d


def log_ratio_ci(pairs, conf=1.96):
    """Paired log-ratio estimate (same pre-declared method as analyze_r3)."""
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


def collect_raw():
    """raw[(cell, arm, run:int)] = bench dict (valid) | None (recorded error)."""
    raw = {}
    unknown = []
    for cell in os.listdir(EV):
        cdir = os.path.join(EV, cell)
        if not os.path.isdir(cdir):
            continue
        if cell.startswith("_"):
            continue
        if cell not in CELLS:
            unknown.append(cell)
            continue
        for f in glob.glob(os.path.join(cdir, "bench_*_r*.json")):
            if "_warmup" in f:
                continue
            base = os.path.basename(f)[len("bench_"):-len(".json")]
            arm, runno = base.rsplit("_r", 1)
            raw[(cell, arm, int(runno))] = load_leg(f)
    return raw, unknown


def main():
    raw, unknown = collect_raw()
    ck("no_unknown_cells", not unknown, f"unknown cells: {sorted(unknown)}")
    n_total = len(raw)

    # ---- 1. execution order covers every raw leg 1:1 --------------------
    order_entries = []
    try:
        with open(os.path.join(EV, "order.jsonl")) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    order_entries.append(json.loads(line))
    except Exception as e:
        ck("order_covers_raw_legs", False, f"order.jsonl unreadable: {e!r}")
        order_entries = []
    pos = {}
    obad = []
    for i, rec in enumerate(order_entries):
        key = (rec.get("cell"), rec.get("arm"), int(rec.get("run", -1)))
        if key in pos:
            obad.append(f"duplicate order entry {key}")
        pos[key] = i
        if rec.get("status") != "ok":
            obad.append(f"non-ok order entry {key}: {rec.get('status')}")
    for key in raw:
        if key not in pos:
            obad.append(f"raw leg not in order.jsonl: {key}")
    for key in pos:
        if key not in raw:
            obad.append(f"order entry without raw leg: {key}")
    ck("order_covers_raw_legs", not obad,
       f"{len(pos)} order entries / {n_total} raw legs; " + "; ".join(obad[:4]))

    valid = {k: v for k, v in raw.items() if v is not None}

    # ---- 2. per_leg.csv bijection with raw legs --------------------------
    try:
        with open(os.path.join(RES, "per_leg.csv")) as fh:
            rows = list(csv.DictReader(fh))
    except Exception as e:
        ck("per_leg_matches_raw_json", False, f"per_leg.csv unreadable: {e!r}")
        rows = []
    seen = {}
    pbad = []
    for r in rows:
        key = (r.get("cell"), r.get("arm"), int(r.get("run", -1)))
        if key in seen:
            pbad.append(f"duplicate CSV row {key}")
            continue
        seen[key] = r
    for key in raw:
        if key not in seen:
            pbad.append(f"leg missing from per_leg.csv: {key}")
    for key in seen:
        if key not in raw:
            pbad.append(f"CSV row without raw leg: {key}")
    for key, r in seen.items():
        d = raw.get(key)
        if d is None:
            if not r.get("error"):
                pbad.append(f"{key}: raw load error not flagged in CSV")
            continue
        if r.get("error"):
            pbad.append(f"{key}: CSV flags error but raw loads fine")
        v = d["output_throughput"]
        try:
            cv = float(r["output_throughput"])
        except Exception:
            pbad.append(f"{key}: non-numeric CSV throughput")
            continue
        if abs(cv - v) > 1e-6 * max(1, v):
            pbad.append(f"throughput drift: {key}")
    ck("per_leg_matches_raw_json", not pbad,
       f"{n_total} raw legs, {len(rows)} CSV rows; " + "; ".join(pbad[:4]))

    # ---- 3. summary medians recompute ------------------------------------
    bycell = {}
    for (cell, arm, run), d in valid.items():
        bycell.setdefault((cell, arm), []).append(d["output_throughput"])
    ttft_by_cell = {}
    for (cell, arm, run), d in valid.items():
        ttft_by_cell.setdefault(cell, []).append(d["mean_ttft_ms"])
    try:
        with open(os.path.join(RES, "performance_summary.csv")) as fh:
            summ = list(csv.DictReader(fh))
    except Exception as e:
        ck("summary_medians_recompute", False, f"summary unreadable: {e!r}")
        summ = []
    drift = []
    skeys = []
    for r in summ:
        key = (r.get("cell"), r.get("arm"))
        skeys.append(key)
        vals = bycell.get(key, [])
        if not vals:
            drift.append(f"{key}: no raw legs for summary row")
            continue
        m = median(vals)
        if abs(float(r["thr_median"]) - m) > MED_TOL * max(1, m):
            drift.append(f"median drift {key}: csv={r['thr_median']} raw={m}")
        if abs(float(r["thr_min"]) - min(vals)) > MED_TOL * max(1, min(vals)):
            drift.append(f"min drift {key}")
        if abs(float(r["thr_max"]) - max(vals)) > MED_TOL * max(1, max(vals)):
            drift.append(f"max drift {key}")
        if int(r["valid_runs"]) != len(vals):
            drift.append(f"count drift {key}: csv={r['valid_runs']} raw={len(vals)}")
    if len(set(skeys)) != len(skeys):
        drift.append("duplicate (cell,arm) summary rows")
    if set(skeys) != set(bycell):
        for k in set(bycell) - set(skeys):
            drift.append(f"summary row missing for {k}")
    ck("summary_medians_recompute", not drift, f"{len(drift)} drifts; " + "; ".join(drift[:4]))

    # ---- 4. statistics.json recomputed from raw paired legs ---------------
    try:
        stats = json.load(open(os.path.join(RES, "statistics.json")))
    except Exception as e:
        ck("statistics_pairs_recomputed_from_raw", False,
           f"statistics.json unreadable: {e!r}")
        stats = None
    if stats is not None:
        sbad = []
        # recompute TTFT outliers per the pre-declared 5x-cell-median rule
        outlier = set()
        for cell, ttfts in ttft_by_cell.items():
            med = median(ttfts)
            for (c, a, rn), d in valid.items():
                if c == cell and d["mean_ttft_ms"] > 5 * med:
                    outlier.add((c, a, rn))
        checked = 0
        # position index for the pairing-vs-execution-order validation
        def pair_window_ok(k1, k2, comp_arm):
            """The two legs of a pair must sit in the same execution window with
            no OTHER leg of the comparator arm or the new arm between them
            (cycle-position pairing; a third arm's leg may interleave)."""
            if k1 not in pos or k2 not in pos:
                return True  # missing legs are reported by other checks
            lo, hi = sorted((pos[k1], pos[k2]))
            for kk, p in pos.items():
                if p > lo and p < hi and kk != k1 and kk != k2:
                    if kk[0] == cell and kk[1] in (comp_arm, "new"):
                        return False
            return True
        for cell, groups in PAIRS.items():
            for comp_arm, pairs in groups.items():
                vals, vals_t = [], []
                for a1, r1, a2, r2 in pairs:
                    A = valid.get((cell, a1, r1))
                    B = valid.get((cell, a2, r2))
                    k1, k2 = (cell, a1, r1), (cell, a2, r2)
                    if not pair_window_ok(k1, k2, comp_arm):
                        sbad.append(f"pair not cycle-contiguous in execution "
                                    f"order {cell}: {a1}_r{r1} vs {a2}_r{r2}")
                    if A and B:
                        if a1 == "new":
                            comp, new = B, A
                        else:
                            comp, new = A, B
                        vals.append((comp["output_throughput"], new["output_throughput"]))
                        if k1 not in outlier and k2 not in outlier:
                            vals_t.append((comp["output_throughput"],
                                           new["output_throughput"]))
                cmp_full = f"new_vs_{comp_arm}_paired"
                cmp_cnt = f"new_vs_{comp_arm}_pair_count"
                cmp_trim = f"new_vs_{comp_arm}_paired_ttft_trimmed"
                got = (stats.get("cells", {}).get(cell, {})
                       .get("comparisons", {}))
                # trimmed variant is published iff trimming removed any pair
                # (the campaign's pre-declared disclosure rule)
                for name, mine in ((cmp_full, log_ratio_ci(vals)),
                                   (cmp_trim, log_ratio_ci(vals_t)
                                    if len(vals_t) != len(vals) else None)):
                    checked += 1
                    theirs = got.get(name)
                    if mine is None and theirs is None:
                        continue
                    if mine is None or theirs is None:
                        sbad.append(f"{cell}/{name}: presence mismatch "
                                    f"(recomputed={'yes' if mine else 'no'})")
                        continue
                    for f in ("geo_mean_ratio", "ci_low", "ci_high"):
                        if not close(mine[f], theirs.get(f)):
                            sbad.append(f"{cell}/{name}.{f}: "
                                        f"published={theirs.get(f)} raw={mine[f]}")
                    if mine["n_pairs"] != theirs.get("n_pairs"):
                        sbad.append(f"{cell}/{name}.n_pairs: "
                                    f"published={theirs.get('n_pairs')} raw={mine['n_pairs']}")
                    pr = theirs.get("paired_ratios") or []
                    if len(pr) != len(mine["paired_ratios"]) or any(
                            not close(x, y) for x, y in zip(pr, mine["paired_ratios"])):
                        sbad.append(f"{cell}/{name}.paired_ratios do not match raw recompute")
                cnt = got.get(cmp_cnt)
                if not isinstance(cnt, dict) or cnt.get("planned") != len(pairs) \
                        or cnt.get("matched") != len(vals):
                    sbad.append(f"{cell}/{cmp_cnt}: published={cnt} "
                                f"raw planned={len(pairs)} matched={len(vals)}")
        ck("statistics_pairs_recomputed_from_raw", not sbad,
           f"{checked} comparisons; " + "; ".join(sbad[:4]))

        # ---- 5. missing legs recomputed -----------------------------------
        ml = []
        for cell, req in REQUIRED_LEGS.items():
            for arm, n_req in req.items():
                n_ok = sum(1 for (c, a, r) in valid if c == cell and a == arm)
                if n_ok < n_req:
                    ml.append({"cell": cell, "arm": arm, "valid": n_ok, "required": n_req})
        published = stats.get("missing_legs", [])
        norm = lambda L: sorted((d["cell"], d["arm"], d["valid"], d["required"]) for d in L)
        ck("missing_legs_recomputed", norm(ml) == norm(published),
           f"recomputed={norm(ml)} published={norm(published)}")

        # ---- 6. arm totals vs certificate --------------------------------
        totals = {}
        for (c, a, r) in valid:
            totals[a] = totals.get(a, 0) + 1
        bad_totals = totals != stats.get("arm_totals", {})
        try:
            cert = json.load(open(os.path.join(R3, "audit", "VALIDATION_CERTIFICATE.json")))
            cert_totals = cert.get("measured_totals", {})
        except Exception:
            cert_totals = None
            bad_totals = True
        bad_totals = bad_totals or (cert_totals != totals)
        ck("arm_totals_match_certificate", not bad_totals,
           f"raw={totals} statistics={stats.get('arm_totals')} certificate={cert_totals}")

    if FAILS:
        print("PERFORMANCE AUDIT FAIL:", FAILS)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
