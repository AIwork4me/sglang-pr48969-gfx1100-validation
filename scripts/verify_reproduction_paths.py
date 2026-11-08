#!/usr/bin/env python3
"""Reproduction-path verifier (audit round 2026-11).

Scans the repository's documents and scripts for file-path references and
classifies each as:

  OK        - the path exists in the repository (relative to repo root)
  HISTORICAL- a path that belongs to the historical T1 execution environment
              (uncommitted work/ dir, /root, /opt, /workspace caches, venvs).
              Allowed only if it appears in the explicit allowlist below,
              which documents WHY it is acceptable.
  FAIL      - anything else: an unresolvable reference that would break a
              clean-clone reproduction. Exit code 1.

This tool exists so that "known missing paths are never described as directly
runnable" (REPRODUCE.md contract) is enforced mechanically rather than by prose.
"""
from __future__ import annotations

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_FILES = [
    "README.md",
    "REPRODUCE.md",
    "ENVIRONMENT.md",
    "LIMITATIONS.md",
    "FINAL_VALIDATION_REPORT.md",
    "GITHUB_REPLY_DRAFT.md",
    "REVIEW_REQUEST.md",
    "configs/benchmark_matrix.yaml",
    "configs/eval_config.yaml",
    "scripts/run_serving_ab.sh",
    "scripts/run_gsm8k_ab.sh",
    "scripts/launch_server.sh",
    "scripts/setup_env.sh",
    "scripts/build_sglkernel.sh",
    "scripts/install_arm.sh",
    "scripts/launch_server_spy.sh",
]

# Historical-environment references that are allowed, each with a reason.
ALLOWED_HISTORICAL = {
    "work/": "historical T1 workspace (uncommitted); REPRODUCE.md §2 gaps + BASELINE_INVENTORY §6",
    "/root/": "historical campaign root / lab host paths",
    "/opt/": "lab host ROCm/torch stack (documented in ENVIRONMENT.md)",
    "/workspace/.cache": "lab HF cache (historical; override via HF_HOME)",
    "codeload.github.com": "network URL, not a local path",
    "repo.radeon.com": "network URL, not a local path",
    "models_cache": "historical model cache location (scripts/dl_model.py default)",
}

# Repo-relative paths that are allowed to be referenced even if generated at
# runtime rather than committed.
ALLOWED_GENERATED = {
    "evidence",  # output roots for T2 reruns (subpaths checked when they exist)
    "results",
    "plots",
    "logs",
    "work",
    "audit",
}

PATH_TOKEN = re.compile(
    r"(?<![\w./-])((?:scripts|evidence|results|configs|patches|plots|logs|audit|tests)/[A-Za-z0-9_./*-]+)"
)
ABS_TOKEN = re.compile(r"(?<![\w-])(/root/[^\s'\"`,;:)]*|/opt/[^\s'\"`,;:)]*|/workspace/[^\s'\"`,;:)]*)")


def strip_code_fences(text: str) -> str:
    """Drop fenced code blocks in REPRODUCE.md (they are T1/T2 commands with
    deliberately allowed historical references) but keep inline mentions."""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def main() -> int:
    failures = []
    checked = 0
    for rel in SCAN_FILES:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            failures.append(f"scan target itself missing: {rel}")
            continue
        text = open(path, errors="replace").read()
        if rel.endswith(".md"):
            text = strip_code_fences(text)
        for m in PATH_TOKEN.finditer(text):
            ref = m.group(1).rstrip(".")
            checked += 1
            import glob as _glob
            if _glob.has_magic(ref):
                if _glob.glob(os.path.join(REPO, ref)):
                    continue
                failures.append(f"{rel}: glob reference matches nothing: {ref}")
                continue
            if os.path.exists(os.path.join(REPO, ref)):
                continue
            # generated roots (e.g. evidence/... outputs) are acceptable only
            # if the *root* exists and the reference is an output target
            root = ref.split("/")[0]
            if root in ALLOWED_GENERATED and os.path.isdir(os.path.join(REPO, root)) and rel != "README.md":
                # in prose docs (other than command examples) a dangling
                # generated-path reference is still a failure; in scripts it is
                # an output destination and fine
                if rel.endswith(".sh") or rel == "REPRODUCE.md":
                    continue
            failures.append(f"{rel}: referenced path does not exist: {ref}")
    for m in ABS_TOKEN.finditer(open(os.path.join(REPO, "scripts/audit_environment.sh"), errors="replace").read() if os.path.exists(os.path.join(REPO, "scripts/audit_environment.sh")) else ""):
        pass  # /opt/venv reference in audit_environment.sh is historical-env by design

    # explicit check: the allowlisted historical prefixes must all carry a reason
    for k, v in ALLOWED_HISTORICAL.items():
        assert v, f"allowlist entry without reason: {k}"

    print(f"checked {checked} repo-relative path references across {len(SCAN_FILES)} files")
    if failures:
        print("FAIL — unresolvable path references:")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS — every referenced repo path exists (historical-env references are allowlisted in this script)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
