#!/usr/bin/env python3
"""Audit: secrets scan — no tokens, credentials or private keys in round3/."""
import os, re, sys

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PATTERNS = [
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat token"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "gh token"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"https://[A-Za-z0-9_]+:(?:ghp_|github_pat_)?[A-Za-z0-9_]{20,}@"), "credentialed URL"),
    (re.compile(r"(?i)aws_access_key_id\s*=\s*AKIA[0-9A-Z]{16}"), "AWS key"),
]
ALLOW = re.compile(r"REDACTED|TOKEN_PLACEHOLDER")


def main():
    hits = []
    for root, _, files in os.walk(R3):
        for f in files:
            p = os.path.join(root, f)
            if f.endswith((".bin", ".pt", ".safetensors", ".whl", ".png", ".jpg")):
                continue
            try:
                txt = open(p, errors="ignore").read()
            except Exception:
                continue
            for rx, what in PATTERNS:
                for m in rx.finditer(txt):
                    if ALLOW.search(m.group(0)):
                        continue
                    hits.append(f"{what}: {p}:{txt[:m.start()].count(chr(10))+1}")
    if hits:
        print("FAIL secrets_scan")
        for h in hits:
            print("  " + h)
        return 1
    print("PASS secrets_scan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
