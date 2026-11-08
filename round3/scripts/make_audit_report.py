#!/usr/bin/env python3
"""Wrap audit_round3.sh output into round3/audit/audit_report.{json,md}."""
import json, os, re, subprocess, sys

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def main():
    r = subprocess.run(["bash", os.path.join(R3, "scripts/audit_round3.sh")],
                       capture_output=True, text=True, cwd=os.path.join(R3, "..", ".."))
    lines = r.stdout.strip().splitlines()
    checks = []
    for ln in lines:
        m = re.match(r"^(PASS|FAIL)\s+(.+?)(?:\s*::.*)?$", ln)
        if m:
            checks.append({"check": m.group(2).strip(), "ok": m.group(1) == "PASS"})
    verdict = "PASS" if r.returncode == 0 and all(c["ok"] for c in checks) else "FAIL"
    rep = {"utc": subprocess.run(["date", "-u", "--iso-8601=seconds"],
                                 capture_output=True, text=True).stdout.strip(),
           "verdict": verdict, "exit_code": r.returncode,
           "checks": checks, "stdout_tail": "\n".join(lines[-20:])}
    if r.stderr.strip():
        rep["stderr_tail"] = r.stderr.strip()[-2000:]
    json.dump(rep, open(os.path.join(R3, "audit/audit_report.json"), "w"), indent=2)
    md = ["# Round 3 Independent Audit Report\n",
          f"**Verdict:** {verdict} (exit {r.returncode})　**UTC:** {rep['utc']}\n",
          "| check | result |", "|---|---|"]
    for c in checks:
        md.append(f"| `{c['check']}` | {'PASS' if c['ok'] else 'FAIL'} |")
    open(os.path.join(R3, "audit/audit_report.md"), "w").write("\n".join(md) + "\n")
    print(f"audit verdict: {verdict} ({len(checks)} checks)")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
