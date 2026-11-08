#!/usr/bin/env python3
"""Fail-closed SHA256 manifest verifier (PR #2 repair round, 2026-11).

Independently parses a sha256sum-format manifest and re-hashes every listed
file. ANY anomaly is a hard failure (exit 1):

  - manifest missing / unreadable
  - unparseable or malformed record (bad hash length, non-hex characters,
    missing separator, trailing junk)
  - empty manifest (zero entries)
  - fewer entries than the required minimum
  - duplicate paths
  - absolute paths, `..` traversal, or paths escaping the required prefix
  - listed file missing on disk
  - hash mismatch (including a single flipped byte)
  - unreadable file

This replaces the previous `sha256sum -c ... | grep -cv ': OK$' | grep -qx 0`
pipeline in scripts/audit_local.sh, which could report success when sha256sum
itself failed or its output was redirected away. No reliance on counting
"OK" strings: every entry is checked individually and every failure is
printed and counted.

Usage:
  verify_followup_manifest.py [--manifest PATH] [--repo ROOT]
                               [--require-prefix PREFIX] [--min-entries N]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

ENTRY = re.compile(r"^([0-9a-f]{64})[ \t]+(\S.*)$")


def fail(errors: list[str]) -> int:
    for e in errors:
        print(f"MANIFEST FAIL: {e}", file=sys.stderr)
    print(f"MANIFEST VERIFY: FAIL ({len(errors)} error(s))", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="followup/SHA256SUMS")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--require-prefix", default=None,
                    help="every listed path must start with this prefix (repo-relative)")
    ap.add_argument("--min-entries", type=int, default=1)
    a = ap.parse_args()

    manifest = a.manifest if os.path.isabs(a.manifest) else os.path.join(a.repo, a.manifest)
    errors: list[str] = []

    if not os.path.isfile(manifest):
        return fail([f"manifest not found: {a.manifest}"])
    try:
        raw_lines = open(manifest, encoding="utf-8", errors="strict").read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return fail([f"manifest unreadable: {e}"])

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for lineno, line in enumerate(raw_lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue  # header comments / blank lines are allowed as whole lines
        m = ENTRY.match(stripped)
        if not m:
            errors.append(f"line {lineno}: unparseable record: {stripped[:80]!r}")
            continue
        h, p = m.group(1), m.group(2).strip()
        # reject any embedded whitespace-ish path or backslash escape trickery
        if re.search(r"[\r\n\t]", p) or p != p.strip():
            errors.append(f"line {lineno}: suspicious path field: {p!r}")
            continue
        if os.path.isabs(p):
            errors.append(f"line {lineno}: absolute path not allowed: {p}")
            continue
        norm = os.path.normpath(p)
        if norm.startswith("..") or "/../" in f"/{norm}/":
            errors.append(f"line {lineno}: path escapes repository root: {p}")
            continue
        if a.require_prefix and not norm.startswith(a.require_prefix.rstrip("/") + "/"):
            errors.append(f"line {lineno}: path outside required prefix '{a.require_prefix}': {p}")
            continue
        if norm in seen:
            errors.append(f"line {lineno}: duplicate path: {norm}")
            continue
        seen.add(norm)
        entries.append((h, norm))

    if not entries and not errors:
        errors.append("manifest contains no entries (empty)")
    if len(entries) < a.min_entries:
        errors.append(f"manifest has {len(entries)} entries, required >= {a.min_entries}")
    if errors:
        return fail(errors)

    checked = 0
    for h, p in entries:
        fp = os.path.join(a.repo, p)
        if not os.path.isfile(fp):
            errors.append(f"missing file: {p}")
            continue
        try:
            actual = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        except OSError as e:
            errors.append(f"unreadable file {p}: {e}")
            continue
        checked += 1
        if actual != h:
            errors.append(f"HASH MISMATCH {p}: manifest={h[:16]}… actual={actual[:16]}…")

    if errors:
        return fail(errors)
    print(f"MANIFEST VERIFY: PASS — {checked}/{len(entries)} entries, every hash independently recomputed and matched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
