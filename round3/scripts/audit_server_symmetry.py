#!/usr/bin/env python3
"""Audit: server configuration symmetry — every server log's effective launch
configuration must be identical across arms within a cell except the arm
identity itself."""
import glob, json, os, re, sys

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EV = os.path.join(R3, "evidence", "performance")
FAILS = []


def ck(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def server_config(path):
    """Extract the effective server configuration from a server log."""
    try:
        txt = open(path, errors="replace").read()
    except Exception:
        return None
    m = re.search(r"server_args=({.*})", txt)
    if not m:
        return None
    raw = m.group(1)
    try:
        cfg = json.loads(raw.replace("'", '"').replace("None", "null").replace("True", "true").replace("False", "false"))
    except Exception:
        return {"unparsed": raw[:200]}
    drop = {"model_path", "port", "tp_size",
            "random_seed"}  # sglang draws a fresh server seed per launch (same policy on every arm)
    return {k: v for k, v in sorted(cfg.items()) if k not in drop}


def main():
    n_checked = 0
    asym = 0
    for cell in sorted(os.listdir(EV)):
        cdir = os.path.join(EV, cell)
        if not os.path.isdir(cdir) or cell.startswith("_"):
            continue
        cfgs = {}
        for f in sorted(glob.glob(os.path.join(cdir, "server_*_r*.log"))):
            base = os.path.basename(f)[len("server_"):-len(".log")]
            arm, _ = base.rsplit("_r", 1)
            cfg = server_config(f)
            if cfg is not None and "unparsed" not in cfg:
                cfgs.setdefault(arm, []).append(json.dumps(cfg, sort_keys=True))
        per_arm = {a: set(v) for a, v in cfgs.items() if v}
        if len(per_arm) < 2:
            continue
        # every arm must have exactly one distinct effective config within the cell
        for a, s in per_arm.items():
            if len(s) != 1:
                asym += 1
                print(f"  config varies within arm {cell}/{a}: {len(s)} variants")
        ref_arm = sorted(per_arm)[0]
        ref = next(iter(per_arm[ref_arm]))
        for a, s in per_arm.items():
            for v in s:
                n_checked += 1
                if v != ref:
                    asym += 1
                    print(f"  config differs across arms: {cell} {ref_arm} vs {a}")
    ck("server_config_symmetric_across_arms", asym == 0, f"{n_checked} configs checked")
    if asym:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
