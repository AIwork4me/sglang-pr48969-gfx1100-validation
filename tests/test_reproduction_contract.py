"""Reproduction-contract tests (Phase 1, pure CPU)."""
import os
import subprocess
import sys

from conftest import REPO


def test_all_scripts_have_syntax_ok():
    import glob
    for f in glob.glob(os.path.join(REPO, "scripts", "*.sh")):
        r = subprocess.run(["bash", "-n", f], capture_output=True, text=True)
        assert r.returncode == 0, f"{f}: {r.stderr}"


def test_all_python_scripts_compile():
    import glob
    import py_compile
    for f in glob.glob(os.path.join(REPO, "scripts", "*.py")):
        py_compile.compile(f, doraise=True)


def test_reproduce_md_declares_four_tiers():
    txt = open(os.path.join(REPO, "REPRODUCE.md")).read()
    for marker in ("T1 Historical exact execution", "T2 Current supported reproduction",
                   "T3 Analysis-only reproduction", "T4 GPU validation required"):
        assert marker in txt, marker
    # the known gap items are named, not hidden
    assert "work/run_final.sh" in txt
    assert "byte-identity" in txt
    # no unfinished placeholder COMMANDS (prose mentions of the historical
    # placeholder are fine)
    assert "sha256sum ... >" not in txt
    # venv python path typo fixed
    assert "work/venv_<arm>/python " not in txt.replace("bin/python", "X")


def test_gsm8k_script_requires_explicit_max_tokens(worktree):
    r = subprocess.run(
        ["bash", os.path.join(worktree, "scripts/run_gsm8k_ab.sh"),
         "A", "0.75", "contract_probe", "200", "100000"],
        capture_output=True, text=True, env={**os.environ,
                                             "SGLANG_VALIDATION_ROOT": worktree},
        timeout=60)
    assert r.returncode == 64, (r.returncode, r.stdout, r.stderr)
    assert "eval_max_tokens" in r.stderr


def test_gsm8k_script_rejects_unknown_model(worktree):
    r = subprocess.run(
        ["bash", os.path.join(worktree, "scripts/run_gsm8k_ab.sh"),
         "Z", "0.75", "contract_probe2", "200", "100000", "1024"],
        capture_output=True, text=True, env={**os.environ,
                                             "SGLANG_VALIDATION_ROOT": worktree},
        timeout=60)
    assert r.returncode != 0
    assert "unknown model key" in r.stdout + r.stderr


def test_run_serving_ab_unknown_model_fails(worktree):
    r = subprocess.run(
        ["bash", os.path.join(worktree, "scripts/run_serving_ab.sh"),
         "Z", "16", "1024", "256", "1", "0.75", "contract_probe3"],
        capture_output=True, text=True, env={**os.environ,
                                             "SGLANG_VALIDATION_ROOT": worktree},
        timeout=120)
    assert r.returncode != 0
    assert "unknown model key" in r.stdout + r.stderr


def test_gsm8k_script_no_swallowed_exit_codes():
    src = open(os.path.join(REPO, "scripts/run_gsm8k_ab.sh")).read()
    assert "|| echo" not in src, "fail-open '|| echo' pattern must not exist"
    assert "rc=$RC" in src or "rc=$?" in src


def test_run_serving_ab_no_swallowed_exit_codes():
    src = open(os.path.join(REPO, "scripts/run_serving_ab.sh")).read()
    for line in src.splitlines():
        code = line.split("#")[0]
        assert "|| echo" not in code.replace('|| echo ""', ''), \
            f"fail-open pattern: {line.strip()}"


def test_no_hardcoded_historical_camp_root_in_scripts():
    import glob
    for f in glob.glob(os.path.join(REPO, "scripts", "*")):
        if not os.path.isfile(f):
            continue
        src = open(f, errors="replace").read()
        for line in src.splitlines():
            code = line.split("#")[0]
            assert "/root/sglang-pr48969-validation" not in code, \
                f"{f}: code still references the historical root: {line.strip()}"


def test_verify_reproduction_paths_passes_on_repo():
    r = subprocess.run([sys.executable,
                        os.path.join(REPO, "scripts/verify_reproduction_paths.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
