#!/usr/bin/env python3
"""Audit: server configuration symmetry — every server log's effective launch
configuration must be identical across arms within a cell except the arm
identity itself. Parse failures and missing required arms are explicit FAILs,
never silent skips."""
import glob, json, os, re, sys

R3 = os.environ.get("AUDIT_R3_ROOT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")
EV = os.path.join(R3, "evidence", "performance")
sys.path.insert(0, os.path.join(R3, "scripts"))
from analyze_r3 import REQUIRED_LEGS  # declared campaign schedule

FAILS = []


def ck(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def server_config(path):
    """Extract the effective server configuration from a server log."""
    try:
        with open(path, errors="replace") as fh:
            txt = fh.read()
    except Exception:
        return None
    m = re.search(r"server_args=({.*})", txt)
    if not m:
        return None
    raw = m.group(1)
    try:
        cfg = json.loads(raw.replace("'", '"').replace("None", "null")
                         .replace("True", "true").replace("False", "false"))
    except Exception:
        return {"unparsed": raw[:200]}
    drop = {"model_path", "port", "tp_size",
            "random_seed"}  # sglang draws a fresh server seed per launch (same policy on every arm)
    return {k: v for k, v in sorted(cfg.items()) if k not in drop}


def main():
    n_checked = 0
    parse_fail = []
    coverage_fail = []
    asym = 0
    for cell in sorted(REQUIRED_LEGS):
        cdir = os.path.join(EV, cell)
        required_arms = {a for a, n in REQUIRED_LEGS[cell].items() if n > 0}
        cfgs = {}
        for arm in sorted(required_arms):
            logs = sorted(glob.glob(os.path.join(cdir, f"server_{arm}_r*.log")))
            if not logs:
                coverage_fail.append(f"{cell}/{arm}: no server log for required arm")
                continue
            for f in logs:
                cfg = server_config(f)
                if cfg is None or "unparsed" in cfg:
                    parse_fail.append(f"{cell}/{os.path.basename(f)}")
                    continue
                cfgs.setdefault(arm, []).append(json.dumps(cfg, sort_keys=True))
        per_arm = {a: set(v) for a, v in cfgs.items() if v}
        # every arm must have exactly one distinct effective config within the cell
        for a, s in per_arm.items():
            if len(s) != 1:
                asym += 1
                print(f"  config varies within arm {cell}/{a}: {len(s)} variants")
        if len(per_arm) < 2:
            continue
        ref_arm = sorted(per_arm)[0]
        ref = next(iter(per_arm[ref_arm]))
        for a, s in per_arm.items():
            for v in s:
                n_checked += 1
                if v != ref:
                    asym += 1
                    print(f"  config differs across arms: {cell} {ref_arm} vs {a}")
    ck("server_configs_parsed", not parse_fail,
       f"{len(parse_fail)} unparseable; " + "; ".join(parse_fail[:3]))
    ck("server_config_arm_coverage", not coverage_fail,
       "; ".join(coverage_fail[:3]))
    ck("server_config_symmetric_across_arms", asym == 0, f"{n_checked} configs checked")
    if FAILS:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
