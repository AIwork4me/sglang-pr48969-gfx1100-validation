"""Follow-up tamper-regression tests (mission Phase 6).

Twelve negative scenarios, each following the strict pattern:
  1. prove the CLEAN fixture passes the real verifier (subprocess, exit 0)
  2. inject exactly one fault
  3. prove the verifier exits non-zero
  4. restore the fixture
  5. prove it passes again

Verifiers under test (real entrypoints, not internal calls):
  - scripts/verify_followup.py          (evidence auditor)
  - scripts/verify_followup_manifest.py (SHA256 manifest, scenario 1 & 11)
All tampering happens inside a disposable work-tree copy; the git repository's
own evidence is never modified.
"""
import json
import os
import shutil
import subprocess
import sys

from conftest import REPO, worktree  # noqa: F401

VF = os.path.join(REPO, "scripts", "verify_followup.py")
VM = os.path.join(REPO, "scripts", "verify_followup_manifest.py")


def run_verify(wt, script=VF):
    return subprocess.run([sys.executable, script, "--repo", wt]
                          if script == VM else [sys.executable, script],
                           capture_output=True, text=True, timeout=1200,
                           cwd=wt if script == VF else None)


def run_vf(wt):
    return subprocess.run([sys.executable, os.path.join(wt, "scripts/verify_followup.py")],
                          capture_output=True, text=True, timeout=1200)


def run_vm(wt):
    return subprocess.run([sys.executable, os.path.join(wt, "scripts/verify_followup_manifest.py"),
                           "--repo", wt, "--manifest", "followup/SHA256SUMS",
                           "--require-prefix", "followup/", "--min-entries", "100"],
                          capture_output=True, text=True, timeout=1200)


def clean_then_tamper(worktree, tamper, verifier=run_vf, expect_fragment=None):
    """Full pattern in one: clean PASS -> inject -> FAIL -> restore -> PASS.

    `tamper(wt)` must return {path: original_bytes} captured BEFORE it touches
    each file (None for files it creates; deletion = the pre-deletion bytes).
    """
    r0 = verifier(worktree)
    assert r0.returncode == 0, f"clean fixture must PASS: {r0.stdout[-400:]}{r0.stderr[-400:]}"
    try:
        backups = tamper(worktree)
        r1 = verifier(worktree)
        assert r1.returncode != 0, f"tampered fixture must FAIL, got 0: {r1.stdout[-400:]}"
        if expect_fragment:
            assert expect_fragment in r1.stdout + r1.stderr, \
                f"expected '{expect_fragment}' in output: {(r1.stdout + r1.stderr)[-600:]}"
    finally:
        for t, content in backups.items():
            if content is None:
                if os.path.isfile(t):
                    os.remove(t)
            else:
                open(t, "wb").write(content)
    r2 = verifier(worktree)
    assert r2.returncode == 0, f"restored fixture must PASS: {r2.stdout[-400:]}"


def wt_path(wt, *p):
    return os.path.join(wt, *p)


def edit_json(path, fn):
    d = json.load(open(path))
    fn(d)
    json.dump(d, open(path, "w"), indent=1)


# ---- 1. delete the follow-up manifest -------------------------------------
def test_01_delete_manifest(worktree):
    def tamper(wt):
        m = wt_path(wt, "followup/SHA256SUMS")
        orig = open(m, "rb").read()
        os.remove(m)
        return {m: orig}
    clean_then_tamper(worktree, tamper, verifier=run_vm, expect_fragment="not found")


# ---- 2. tamper one follow-up bench throughput (NaN) ------------------------
def test_02_bench_throughput_nan(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_performance/A_c1_rep/bench_main_r1.json")
        orig = open(p, "rb").read()
        edit_json(p, lambda d: d.__setitem__("output_throughput", float("nan")))
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f14_nonfinite_policy")


# ---- 3. delete an r2 bench json --------------------------------------------
def test_03_delete_r2_bench(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_performance/A_c2/bench_pr_r2.json")
        orig = open(p, "rb").read()
        os.remove(p)
        return {p: orig}
    clean_then_tamper(worktree, tamper)


# ---- 4. PR memfrac differs from Main ---------------------------------------
def test_04_pr_memfrac_asymmetric(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_performance/A_c2/server_pr_r1.log")
        orig = open(p, "rb").read()
        s = open(p).read().replace("mem_fraction_static': 0.75", "mem_fraction_static': 0.3")
        open(p, "w").write(s)
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f5_memory_config_per_cell")


# ---- 5. wrong concurrency ---------------------------------------------------
def test_05_wrong_concurrency(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_performance/A_c2/bench_main_r1.json")
        orig = open(p, "rb").read()
        edit_json(p, lambda d: (d.__setitem__("max_concurrency", 4),
                                d.__setitem__("completed", 4)))
        return {p: orig}
    clean_then_tamper(worktree, tamper)


# ---- 6. wrong completed count ----------------------------------------------
def test_06_wrong_completed(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_performance/A_c1_mem030/bench_pr_r2.json")
        orig = open(p, "rb").read()
        edit_json(p, lambda d: d.__setitem__("completed", 7))
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f2_bench_sane")


# ---- 7. delete a server log -------------------------------------------------
def test_07_delete_server_log(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_performance/A_c1_mem030/server_main_r2.log")
        orig = open(p, "rb").read()
        os.remove(p)
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="server log missing")


# ---- 8. LDS numbers altered in a determinism log ---------------------------
def test_08_lds_numbers_altered(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_determinism/server_main.log")
        orig = open(p, "rb").read()
        s = open(p).read().replace("99328", "123456")
        open(p, "w").write(s)
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f9_determinism_lds_failure_both_arms")


# ---- 9. Main/PR determinism error classes made inconsistent -----------------
def test_09_error_class_inconsistent(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/evidence_determinism/server_pr.log")
        orig = open(p, "rb").read()
        s = open(p).read().replace("OutOfResources", "SomeOtherFatalError") \
                 .replace("Required: 99328, Hardware limit: 65536", "allocation failed")
        open(p, "w").write(s)
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f9_determinism_lds_failure_both_arms")


# ---- 10. followup summary speedup altered ----------------------------------
def test_10_summary_speedup_altered(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/results/followup_summary.json")
        orig = open(p, "rb").read()
        edit_json(p, lambda d: d["A_c2"].__setitem__("tput_spd", 1.2))
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f3_summary_recomputed")


# ---- 11. raw file changed, old manifest kept --------------------------------
def test_11_raw_change_old_manifest(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/ANALYSIS.md")
        orig = open(p, "rb").read()
        open(p, "ab").write(b"\n# silent edit\n")
        return {p: orig}
    clean_then_tamper(worktree, tamper, verifier=run_vm, expect_fragment="HASH MISMATCH")


# ---- 12. BLOCKED flipped to PASS --------------------------------------------
def test_12_blocked_flipped_to_pass(worktree):
    def tamper(wt):
        p = wt_path(wt, "followup/results/determinism_verdict.json")
        orig = open(p, "rb").read()
        edit_json(p, lambda d: (d.__setitem__("overall", "PASS"),
                                d["arms"]["main"].__setitem__("verdict", "PASS"),
                                d["arms"]["pr"].__setitem__("verdict", "PASS")))
        return {p: orig}
    clean_then_tamper(worktree, tamper, expect_fragment="f11_determinism_verdict_blocked_scoped")
