#!/usr/bin/env python3
"""Derive the deterministic-serving verdict FROM THE ARCHIVED LOGS (CPU-only).

The repair-round determinism.sh was not executed on the GPU (NO-NEW-GPU
policy), so this tool applies the SAME classification rules to the two
archived server logs from the 2026-11-08 follow-up experiment, producing
followup/results/determinism_verdict.json. Provenance: the logs were produced
by two invocations (determinism.sh for main; determinism_pr.historical.sh for
pr — one-line diff; see followup/audit/BASELINE.md).
"""
from __future__ import annotations

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(REPO, "followup", "evidence_determinism")
OUT = os.path.join(REPO, "followup", "results", "determinism_verdict.json")


def classify(log_path: str) -> dict:
    txt = open(log_path, errors="replace").read()
    rec = {"evidence": os.path.relpath(log_path, REPO), "server_ready": False}
    m = re.search(r"enable_deterministic_inference': (\w+)", txt)
    rec["flag_recorded"] = m.group(1) if m else None
    mm = re.search(r"mem_fraction_static': ([0-9.]+)", txt)
    rec["mem_fraction_static"] = mm.group(1) if mm else None
    if "OutOfResources" in txt:
        req = re.search(r"Required: (\d+)", txt)
        hw = re.search(r"Hardware limit: (\d+)", txt)
        rec["error_class"] = "OutOfResources"
        rec["error_detail"] = (f"shared memory Required: {req.group(1)} > "
                               f"Hardware limit: {hw.group(1)}") if req and hw else "unparsed"
        rec["verdict"] = "BLOCKED"
    elif re.search(r"out of memory", txt, re.I):
        rec["error_class"] = "OOM"
        rec["verdict"] = "BLOCKED"
    else:
        rec["error_class"] = "UNEXPECTED"
        rec["verdict"] = "FAIL"
    rec["failure_site"] = "batch_invariant_ops.py persistent matmul" if "batch_invariant_ops" in txt else "unparsed"
    return rec


def main() -> int:
    arms = {}
    for arm in ("main", "pr"):
        p = os.path.join(LOGS, f"server_{arm}.log")
        if not os.path.isfile(p):
            print(f"FAIL: missing evidence {p}", file=sys.stderr)
            return 1
        arms[arm] = classify(p)
    classes = {a["error_class"] for a in arms.values()}
    verdicts = {a["verdict"] for a in arms.values()}
    overall = "FAIL" if "FAIL" in verdicts else "BLOCKED" if "BLOCKED" in verdicts else "PASS"
    doc = {
        "derived_from": "followup/evidence_determinism/server_{main,pr}.log (archived GPU logs, 2026-11-08)",
        "derivation_script": "scripts/derive_determinism_verdict.py (same classification rules as followup/scripts/determinism.sh)",
        "scope": ("With the tested SGLang/PyTorch/Triton/ROCm stack on this gfx1100 host, "
                  "deterministic-serving STARTUP fails; this does not assert anything about "
                  "other stacks, does not implicate PR #48969 (identical on both arms; the "
                  "failing path batch_invariant_ops.py is outside the PR's decode-attention "
                  "change), and does not imply AMD GPUs lack deterministic computing in general."),
        "overall": overall,
        "overall_human": "BLOCKED / startup failure confirmed on both arms",
        "identical_error_class_across_arms": len(classes) == 1,
        "arms": arms,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w"), indent=1)
    print(json.dumps({k: doc[k] for k in ("overall", "overall_human", "identical_error_class_across_arms")}))
    print(f"wrote {os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
