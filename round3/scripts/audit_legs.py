#!/usr/bin/env python3
"""Audit: benchmark leg completeness against the campaign's required-legs map."""
import glob, json, math, os, sys

R3 = os.environ.get("AUDIT_R3_ROOT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")
EV = os.path.join(R3, "evidence", "performance")
sys.path.insert(0, os.path.join(R3, "scripts"))
from analyze_r3 import REQUIRED_LEGS  # noqa: E402

FAILS = []


def valid_leg(path):
    try:
        d = json.load(open(path))
        v = d.get("output_throughput")
        return isinstance(v, (int, float)) and math.isfinite(v) and v > 0 \
            and d.get("completed", 0) > 0
    except Exception:
        return False


def main():
    all_ok = True
    for cell, req in REQUIRED_LEGS.items():
        cdir = os.path.join(EV, cell)
        for arm, n_req in req.items():
            legs = [f for f in glob.glob(os.path.join(cdir, f"bench_{arm}_r*.json"))
                    if "_warmup" not in f and valid_leg(f)]
            status = "ok" if len(legs) >= n_req else "SHORT"
            print(f"  {cell}/{arm}: {len(legs)}/{n_req} {status}")
            if status == "SHORT":
                all_ok = False
    if all_ok:
        print("PASS leg_completeness")
        return 0
    print("FAIL leg_completeness (short cells above; disclosed in statistics.json missing_legs)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
