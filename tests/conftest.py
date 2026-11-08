"""Shared fixtures: a pristine session copy of the repo + per-test work trees."""
import importlib.util
import os
import shutil
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def pristine(tmp_path_factory):
    dst = tmp_path_factory.mktemp("pristine")
    for item in sorted(os.listdir(REPO)):
        if item in (".git", "__pycache__", ".pytest_cache"):
            continue
        src = os.path.join(REPO, item)
        out = os.path.join(str(dst), item)
        if os.path.isdir(src):
            shutil.copytree(src, out, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(src, out)
    return str(dst)


@pytest.fixture
def worktree(pristine, tmp_path):
    dst = tmp_path / "wt"
    shutil.copytree(pristine, str(dst), symlinks=True)
    return str(dst)


def load_auditor(repo):
    spec = importlib.util.spec_from_file_location(
        "verify_evidence_v2", os.path.join(repo, "scripts", "verify_evidence_v2.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_audit(repo):
    """Run the V2 auditor on a work tree. Returns (failed_ids, exception).

    The auditor is fail-closed: any unexpected exception counts as a failure
    (it must never crash into a false PASS), and we return it instead of
    raising so tamper tests can assert 'did not pass' either way.
    """
    mod = load_auditor(repo)
    try:
        audit = mod.run_audit(repo)
        failed = [c["id"] for c in audit.checks if c["status"] == "FAIL"]
        overall_pass = not failed
        return failed, None, overall_pass
    except Exception as e:  # noqa: BLE001
        return [], e, False


def rewrite_json(path, fn):
    import json
    d = json.load(open(path))
    fn(d)
    json.dump(d, open(path, "w"), indent=1)
