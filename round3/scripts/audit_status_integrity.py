#!/usr/bin/env python3
"""Audit: status integrity — the certificate, the independent verdict file and
the raw per-test verdict records must agree; BLOCKED/NOT_RUN must never be
presented as PASS; every PASS must trace to resolvable evidence.

BLOCKED is a standard status; specific causes (e.g. BLOCKED_LDS_LIMIT) are
recorded in the reason field, never in the status field itself."""
import glob, json, os, sys

R3 = os.environ.get("AUDIT_R3_ROOT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")
CAMP = os.path.normpath(os.path.join(R3, ".."))
CERT = os.path.join(R3, "audit", "VALIDATION_CERTIFICATE.json")
VERDICTS = os.path.join(R3, "audit", "verdicts.json")
VALID_STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
FAILS = []


def ck(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def resolve(p):
    return os.path.exists(os.path.join(CAMP, p)) or os.path.exists(os.path.join(R3, p))


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def raw_blocked_verdicts(paths):
    """Collect raw BLOCKED/FAIL execution verdicts from *.jsonl records under
    the test's evidence paths. Raw execution records outrank any derived
    certificate claim, so a PASS contradicted here is rejected."""
    hits = []
    for p in paths:
        cand = [os.path.join(CAMP, p), os.path.join(R3, p)]
        base = next((c for c in cand if os.path.isdir(c)), None)
        if base is None:
            continue
        for f in sorted(glob.glob(os.path.join(base, "**", "*.jsonl"),
                                  recursive=True)):
            rel = os.path.relpath(f, CAMP)
            try:
                for line in open(f, errors="replace"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    v = str(rec.get("verdict", rec.get("status", "")))
                    if v.startswith(("BLOCKED", "FAIL")):
                        hits.append(f"{rel}: {v}")
            except Exception:
                hits.append(f"{rel}: unreadable")
    return hits


def main():
    if not os.path.exists(CERT):
        print("FAIL certificate_missing")
        return 1
    cert = load_json(CERT)
    tests = cert.get("tests", {})
    bad = []
    for name, t in tests.items():
        status = t.get("status")
        if status not in VALID_STATUSES:
            bad.append(f"{name}: invalid status {status}")
        if status == "PASS":
            ev = t.get("evidence")
            if not ev or not all(resolve(p) for p in ev):
                bad.append(f"{name}: PASS without resolvable evidence {ev}")
        if status in ("BLOCKED", "NOT_RUN"):
            reason = t.get("reason", "")
            if not reason:
                bad.append(f"{name}: {status} without reason")
    ck("statuses_valid_and_traced", not bad, "; ".join(bad[:5]))

    # declared counts must match reality; BLOCKED must never fold into PASS
    counts = cert.get("counts", {})
    real = {}
    for t in tests.values():
        real[t.get("status")] = real.get(t.get("status"), 0) + 1
    cbad = []
    for k in sorted(set(real) | set(counts)):
        if counts.get(k, 0) != real.get(k, 0):
            cbad.append(f"counts[{k}] {counts.get(k, 0)} != actual {real.get(k, 0)}")
    ck("declared_counts_match", not cbad, "; ".join(cbad[:5]))

    # certificate must agree test-by-test with the independent verdict file
    vbad = []
    if not os.path.exists(VERDICTS):
        vbad.append("verdicts.json missing")
    else:
        verd = load_json(VERDICTS)
        ct, vt = set(tests), set(verd)
        if ct - vt:
            vbad.append(f"tests only in certificate: {sorted(ct - vt)}")
        if vt - ct:
            vbad.append(f"tests only in verdicts: {sorted(vt - ct)}")
        for name in sorted(ct & vt):
            cs = tests[name].get("status")
            vs = verd[name].get("status")
            if cs != vs:
                vbad.append(f"{name}: certificate={cs} verdicts={vs}")
    ck("certificate_matches_verdicts", not vbad, "; ".join(vbad[:5]))

    # a PASS claim contradicted by raw BLOCKED/FAIL execution records
    rbad = []
    for name, t in tests.items():
        if t.get("status") != "PASS":
            continue
        hits = raw_blocked_verdicts(t.get("evidence") or [])
        if hits:
            rbad.append(f"{name}: " + "; ".join(hits[:3]))
    ck("pass_not_contradicted_by_raw_verdicts", not rbad, "; ".join(rbad[:5]))

    if FAILS:
        print("STATUS AUDIT FAIL:", FAILS)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
