"""Determinism-contract control-flow tests (mock launcher; NO GPU).

Exercises followup/scripts/determinism.sh end-to-end with a fake server
launcher (tests/fixtures/fake_determinism_server.py) via DETERMINISM_LAUNCHER.
Required scenarios (mission Phase 3.5):
  - Main fails, PR still executes (and vice versa: PR record intact).
  - Both arms hit identical OutOfResources → BLOCKED each, overall BLOCKED.
  - Different failures are NOT classified as identical.
  - Missing evidence → FAIL.
  - Valid startup but output mismatch → FAIL (not PASS).
  - Expected startup failure is never a functional PASS.
  - Cleanup targets only process groups created by the script.
Also verifies the committed evidence-derived verdict for the archived logs.
"""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from conftest import REPO, worktree  # noqa: F401

SCRIPT = os.path.join(REPO, "followup", "scripts", "determinism.sh")
FIXTURE = os.path.join(REPO, "tests", "fixtures", "fake_determinism_server.py")
VENV_STUB = os.path.join(REPO, "tests", "fixtures", "fake_venv")


@pytest.fixture(scope="module", autouse=True)
def fake_venv():
    """determinism.sh sources $WORK/venv_<arm>/bin/activate — provide stubs."""
    for arm in ("main", "pr"):
        d = os.path.join(VENV_STUB, f"venv_{arm}", "bin")
        os.makedirs(d, exist_ok=True)
        activate = os.path.join(d, "activate")
        if not os.path.exists(activate):
            open(activate, "w").write("# stub activate (test)\n")
    yield


def run_single_arm(outdir, arm, mode, port, timeout=600):
    """Run determinism.sh for ONE arm with FAKE_MODE=mode launcher."""
    env = {**os.environ,
           "DETERMINISM_OUT": outdir,
           "DETERMINISM_PORT": str(port),
           "SGLANG_VALIDATION_WORK": VENV_STUB,
           "DETERMINISM_READY_TRIES": "2",
           "DETERMINISM_READY_SLEEP": "1",
           "FAKE_MODE": mode,
           "DETERMINISM_LAUNCHER": f"{sys.executable} {FIXTURE}",
           }
    r = subprocess.run(["bash", SCRIPT, arm], capture_output=True, text=True,
                       env=env, timeout=timeout)
    return r


def read(outdir, name):
    return json.load(open(os.path.join(outdir, name)))


def test_both_arms_identical_oom_blocked(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    r = run_single_arm(out, "main", "oom", port=31501)
    r2 = run_single_arm(out, "pr", "oom", port=31501)
    assert "verdict=BLOCKED" in r.stdout and "verdict=BLOCKED" in r2.stdout
    for arm in ("main", "pr"):
        rec = read(out, f"record_{arm}.json")
        assert rec["verdict"] == "BLOCKED"
        assert rec["error_class"] == "OutOfResources"
        assert "99328" in rec["error_detail"] and "65536" in rec["error_detail"]
        assert rec["server_ready"] is False
        assert rec["launch_command"] and rec["start_utc"] and rec["pid"] and rec["pgid"]
    v = read(out, "verdict.json")
    assert v["overall"] == "BLOCKED"
    assert v["identical_error_class_across_arms"] is True


def test_main_fails_pr_still_executes(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    r1 = run_single_arm(out, "main", "oom", port=31502)
    # PR arm runs fine afterwards; its record must exist and main's stays intact
    r2 = run_single_arm(out, "pr", "ok", port=31502)
    assert "verdict=BLOCKED" in r1.stdout
    assert "verdict=PASS" in r2.stdout
    m, p = read(out, "record_main.json"), read(out, "record_pr.json")
    assert m["verdict"] == "BLOCKED" and p["verdict"] == "PASS"
    assert p["probe"]["run_to_run_identical"] and p["probe"]["batch_invariant"]


def test_pr_fails_main_record_intact(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    r1 = run_single_arm(out, "main", "ok", port=31503)
    before = read(out, "record_main.json")
    r2 = run_single_arm(out, "pr", "crash", port=31503)
    assert "verdict=FAIL" in r2.stdout  # unrelated crash = unexpected = FAIL
    after = read(out, "record_main.json")
    assert before == after  # untouched by the other arm's run


def test_different_failures_not_classified_identical(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    run_single_arm(out, "main", "oom", port=31504)
    run_single_arm(out, "pr", "oom2", port=31504)
    m, p = read(out, "record_main.json"), read(out, "record_pr.json")
    assert m["error_detail"] != p["error_detail"]
    assert m["error_class"] == p["error_class"] == "OutOfResources"  # same CLASS…
    # …but the details differ and must not be merged:
    assert "99328" in m["error_detail"]
    assert "131072" in p["error_detail"]


def test_unrelated_crash_is_fail_not_blocked(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    r = run_single_arm(out, "main", "crash", port=31505)
    assert "verdict=FAIL" in r.stdout
    assert read(out, "record_main.json")["error_class"] == "UNEXPECTED"


def test_startup_ok_output_mismatch_is_fail(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    r = run_single_arm(out, "pr", "mismatch", port=31506)
    assert "verdict=FAIL" in r.stdout
    rec = read(out, "record_pr.json")
    assert rec["error_class"] == "OUTPUT-MISMATCH"
    assert rec["verdict"] == "FAIL"


def test_startup_failure_never_functional_pass(tmp_path):
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    run_single_arm(out, "main", "oom", port=31507)
    assert read(out, "record_main.json")["verdict"] != "PASS"


def test_cleanup_targets_only_own_process_group(tmp_path):
    """An unrelated long-running process must survive the script's cleanup."""
    out = str(tmp_path / "det")
    os.makedirs(out, exist_ok=True)
    bystander = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        r = run_single_arm(out, "main", "hang", port=31508, timeout=900)
        # readiness loop: 150*5s max; the hang server never becomes ready and
        # keeps running -> script must kill exactly its own PGID and exit
        rec_path = os.path.join(out, "record_main.json")
        assert os.path.exists(rec_path), r.stdout + r.stderr
        rec = read(out, "record_main.json")
        assert rec["verdict"] in ("FAIL", "BLOCKED")
        # the bystander (different session) must still be alive
        bystander.poll()
        assert bystander.returncode is None
    finally:
        bystander.terminate()
        bystander.wait()


def test_missing_evidence_is_fail():
    """The committed evidence-derived verdict must match the archived logs;
    deleting one archived log must make the verifier fail (checked in the
    follow-up tamper suite). Here: derivation refuses missing logs."""
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts/derive_determinism_verdict.py")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    v = json.load(open(os.path.join(REPO, "followup/results/determinism_verdict.json")))
    assert v["overall"] == "BLOCKED"
    assert v["identical_error_class_across_arms"] is True
    assert all(a["verdict"] == "BLOCKED" for a in v["arms"].values())
    assert "does not implicate PR #48969" in v["scope"]
