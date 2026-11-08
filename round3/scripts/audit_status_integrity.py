#!/usr/bin/env python3
"""Audit: status integrity — the certificate and final report must not mark
BLOCKED or NOT_RUN tests as PASS; every PASS must trace to evidence."""
import json, os, re, sys

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CERT = os.path.join(R3, "audit", "VALIDATION_CERTIFICATE.json")
FAILS = []


def ck(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def main():
    if not os.path.exists(CERT):
        print("FAIL certificate_missing")
        return 1
    cert = json.load(open(CERT))
    tests = cert.get("tests", {})
    bad = []
    for name, t in tests.items():
        status = t.get("status")
        if status not in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
            bad.append(f"{name}: invalid status {status}")
        if status == "PASS":
            ev = t.get("evidence")
            if not ev or not all(os.path.exists(os.path.join(R3, "..", p)) or
                                 os.path.exists(os.path.join(R3, p)) for p in ev):
                bad.append(f"{name}: PASS without resolvable evidence {ev}")
        if status in ("BLOCKED", "NOT_RUN"):
            reason = t.get("reason", "")
            if not reason:
                bad.append(f"{name}: {status} without reason")
    ck("statuses_valid_and_traced", not bad, "; ".join(bad[:5]))
    counts = cert.get("counts", {})
    real = {}
    for t in tests.values():
        real[t["status"]] = real.get(t["status"], 0) + 1
    for k, v in real.items():
        if counts.get(k) != v:
            bad.append(f"counts[{k}] {counts.get(k)} != actual {v}")
    ck("declared_counts_match", not bad, "; ".join(bad[:5]))
    if bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
