#!/usr/bin/env python3
"""Verify an extracted sglang source tree is byte-identical to a pinned GitHub commit.

Uses the trusted GitHub git/trees API JSON (recursive) and recomputes the git blob
SHA-1 (sha1("blob <len>\\0" + content)) for every file on disk. Any mismatch,
missing, or extra file fails the check.

Usage: verify_source.py <tree_json> <src_dir> [--write <out_json>]
"""
import hashlib
import json
import os
import sys


def git_blob_sha1(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def main() -> int:
    tree_json, src_dir = sys.argv[1], sys.argv[2]
    out_path = None
    if "--write" in sys.argv:
        out_path = sys.argv[sys.argv.index("--write") + 1]
    tree = json.load(open(tree_json))
    assert not tree.get("truncated"), "recursive tree JSON is truncated; cannot verify"
    expected = {e["path"]: e["sha"] for e in tree["tree"] if e["type"] == "blob"}
    symlinks = {e["path"] for e in tree["tree"] if e.get("mode") == "120000"}
    actual = {}
    for root, _dirs, files in os.walk(src_dir, followlinks=False):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, src_dir)
            if os.path.islink(p):
                # git stores a symlink as a blob containing the target path
                actual[rel] = git_blob_sha1(os.readlink(p).encode())
            else:
                actual[rel] = git_blob_sha1(open(p, "rb").read())
    # os.walk classifies symlinks that resolve to directories as dirs; hash
    # their target strings explicitly so git's view of the tree is covered.
    for rel in symlinks:
        p = os.path.join(src_dir, rel)
        if os.path.islink(p):
            actual[rel] = git_blob_sha1(os.readlink(p).encode())
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatched = sorted(p for p in set(expected) & set(actual) if expected[p] != actual[p])
    report = {
        "tree_sha": tree.get("sha"),
        "src_dir": src_dir,
        "expected_files": len(expected),
        "found_files": len(actual),
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "verified": not missing and not extra and not mismatched,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if out_path:
        open(out_path, "w").write(text + "\n")
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
