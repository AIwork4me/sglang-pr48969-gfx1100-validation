"""P0 manifest-verification regression tests (PR #2 repair round).

Every documented tamper class must produce a NON-ZERO exit from the REAL
verifier (`scripts/verify_followup_manifest.py`, executed as a subprocess —
not an internal function call). Two representative cases are additionally run
through the real audit entry (`scripts/audit_local.sh`) inside a work tree to
prove failure propagation at the entry-point level.

Scenario matrix (mission Phase 1.3):
  1. manifest missing                      6. stderr/stdout redirected away
  2. manifest empty (no entries)           7. duplicate paths / illegal paths
  3. illegal hash (bad hex/length)         8. `../` traversal entry
  4. referenced file missing               9. verifier executed with a
  5. one byte flipped in a listed file        corrupt repo root (anomaly)
 10. clean manifest passes
"""
import os
import shutil
import subprocess
import sys

from conftest import REPO, worktree  # noqa: F401

VERIFIER = os.path.join(REPO, "scripts", "verify_followup_manifest.py")
ARGS = ["--manifest", "followup/SHA256SUMS", "--require-prefix", "followup/", "--min-entries", "108"]


def run_verifier(wt: str, extra_env=None):
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run([sys.executable, VERIFIER, "--repo", wt, *ARGS],
                          capture_output=True, text=True, env=env, timeout=120)


def backup(wt):
    src = os.path.join(wt, "followup/SHA256SUMS")
    bak = src + ".bak"
    shutil.copy2(src, bak)
    return bak


def restore(wt, bak):
    shutil.move(bak, os.path.join(wt, "followup/SHA256SUMS"))


def manifest_lines(wt):
    return open(os.path.join(wt, "followup/SHA256SUMS")).read().splitlines()


def write_manifest(wt, lines):
    open(os.path.join(wt, "followup/SHA256SUMS"), "w").write("\n".join(lines) + "\n")


def manifest_entries(wt):
    return [l for l in manifest_lines(wt)
            if not l.startswith("#") and l.strip() and len(l.split(None, 1)) == 2
            and len(l.split(None, 1)[0]) == 64]


def first_entry_line(wt):
    return manifest_entries(wt)[0]


def test_10_clean_manifest_passes(worktree):  # noqa: F811
    r = run_verifier(worktree)
    assert r.returncode == 0, r.stdout + r.stderr


def test_01_manifest_missing_fails(worktree):  # noqa: F811
    os.remove(os.path.join(worktree, "followup/SHA256SUMS"))
    r = run_verifier(worktree)
    assert r.returncode != 0 and "not found" in r.stderr


def test_02_manifest_empty_fails(worktree):  # noqa: F811
    bak = backup(worktree)
    try:
        write_manifest(worktree, ["# only comments", ""])
        r = run_verifier(worktree)
        assert r.returncode != 0 and "no entries" in r.stderr
    finally:
        restore(worktree, bak)


def test_03_illegal_hash_fails(worktree):  # noqa: F811
    bak = backup(worktree)
    try:
        lines = manifest_lines(worktree)
        for i, l in enumerate(lines):
            if not l.startswith("#") and l.strip():
                lines[i] = "zz" + l[2:]  # non-hex characters in the digest
                break
        write_manifest(worktree, lines)
        r = run_verifier(worktree)
        assert r.returncode != 0 and "unparseable" in r.stderr
    finally:
        restore(worktree, bak)


def test_04_missing_referenced_file_fails(worktree):  # noqa: F811
    target = None
    for l in manifest_entries(worktree):
        if "bench_main_r1.json" in l:
            target = l.split(None, 1)[1].strip()
            break
    assert target
    os.remove(os.path.join(worktree, target))
    r = run_verifier(worktree)
    assert r.returncode != 0 and "missing file" in r.stderr
    # restore from pristine repo for the next users of the fixture
    shutil.copy2(os.path.join(REPO, target), os.path.join(worktree, target))


def test_05_one_byte_flipped_fails(worktree):  # noqa: F811
    target = None
    for l in manifest_entries(worktree):
        if l.split(None, 1)[1].strip().endswith("ANALYSIS.md"):
            target = l.split(None, 1)[1].strip()
            break
    assert target
    fp = os.path.join(worktree, target)
    orig = open(fp, "rb").read()
    try:
        open(fp, "ab").write(b" ")  # one byte appended
        r = run_verifier(worktree)
        assert r.returncode != 0 and "HASH MISMATCH" in r.stderr
    finally:
        open(fp, "wb").write(orig)


def test_06_output_redirection_cannot_mask_failure(worktree):  # noqa: F811
    """stderr+stdout redirected to /dev/null — exit code must still be 1."""
    target = None
    for l in manifest_entries(worktree):
        if l.split(None, 1)[1].strip().endswith("ANALYSIS.md"):
            target = l.split(None, 1)[1].strip()
            break
    fp = os.path.join(worktree, target)
    orig = open(fp, "rb").read()
    try:
        open(fp, "ab").write(b"x")
        r = subprocess.run(
            f"{sys.executable} {VERIFIER} --repo {worktree} "
            f"{' '.join(ARGS)} >/dev/null 2>&1",
            shell=True, timeout=120)
        assert r.returncode != 0
    finally:
        open(fp, "wb").write(orig)


def test_07_duplicate_path_fails(worktree):  # noqa: F811
    bak = backup(worktree)
    try:
        lines = manifest_lines(worktree)
        entry = first_entry_line(worktree)
        lines.append(entry)  # exact duplicate record
        write_manifest(worktree, lines)
        r = run_verifier(worktree)
        assert r.returncode != 0 and "duplicate" in r.stderr
    finally:
        restore(worktree, bak)


def test_08_path_traversal_fails(worktree):  # noqa: F811
    bak = backup(worktree)
    try:
        real = first_entry_line(worktree)
        h = real.split(None, 1)[0]
        # traversal that would resolve inside the repo if naively normalized
        lines = manifest_lines(worktree)
        lines.append(f"{h}  followup/../followup/ANALYSIS.md")
        # and one that escapes entirely
        lines.append(f"{h}  ../evidence/EVIDENCE_AUDIT_V2.md")
        write_manifest(worktree, lines)
        r = run_verifier(worktree)
        assert r.returncode != 0 and ("escape" in r.stderr or "prefix" in r.stderr or "duplicate" in r.stderr)
    finally:
        restore(worktree, bak)


def test_09_verifier_anomaly_is_failure(worktree):  # noqa: F811
    """Repo root pointing at a corrupt tree (manifest unreadable binary)."""
    bad = os.path.join(worktree, "badroot", "followup")
    os.makedirs(bad, exist_ok=True)
    open(os.path.join(bad, "SHA256SUMS"), "wb").write(b"\xff\xfe\x00garbage")
    r = subprocess.run(
        [sys.executable, VERIFIER, "--repo", worktree + "/badroot",
         "--manifest", "followup/SHA256SUMS"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode != 0


NESTED = os.environ.get("SGLANG_AUDIT_LOCAL_NESTED") == "1"


def test_entrypoint_propagation_missing_manifest(worktree):  # noqa: F811
    """The real audit entry must FAIL (non-zero) when the manifest is gone."""
    import pytest
    if NESTED:
        pytest.skip("nested audit_local invocation (recursion guard)")
    os.remove(os.path.join(worktree, "followup/SHA256SUMS"))
    r = subprocess.run(["bash", os.path.join(worktree, "scripts/audit_local.sh")],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "SGLANG_AUDIT_LOCAL_NESTED": "1"})
    assert r.returncode != 0
    assert "FAIL" in r.stdout
    # restore for other tests
    shutil.copy2(os.path.join(REPO, "followup/SHA256SUMS"),
                 os.path.join(worktree, "followup/SHA256SUMS"))


def test_entrypoint_propagation_hash_tamper(worktree):  # noqa: F811
    """The real audit entry must FAIL when a sealed follow-up file is altered."""
    import pytest
    if NESTED:
        pytest.skip("nested audit_local invocation (recursion guard)")
    fp = os.path.join(worktree, "followup/ANALYSIS.md")
    orig = open(fp, "rb").read()
    try:
        open(fp, "ab").write(b"\ntamper\n")
        r = subprocess.run(["bash", os.path.join(worktree, "scripts/audit_local.sh")],
                           capture_output=True, text=True, timeout=1800)
        assert r.returncode != 0
        assert "FAIL (1) — followup manifest" in r.stdout
        # the detailed reason is written to the audit log
        log = open(os.path.join(worktree, "audit/audit_local.log"), errors="replace").read()
        assert "HASH MISMATCH" in log
    finally:
        open(fp, "wb").write(orig)
