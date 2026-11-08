"""Auditor regression tests (Phase 3.4, pure CPU): every documented tamper class
must flip the V2 audit to FAIL — the auditor must never propagate a PASS from
stale labels, and BLOCKED experiments must never become PASS."""
import json
import os
import shutil
import sys

import pytest

from conftest import run_audit, rewrite_json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def test_pristine_audit_passes(pristine):
    failed, exc, ok = run_audit(pristine)
    assert exc is None, f"auditor crashed on pristine tree: {exc}"
    assert ok, f"pristine tree must PASS, failed checks: {failed}"


def test_tamper_raw_bench_value_fails(worktree):
    p = os.path.join(worktree, "evidence/performance/A_c1/bench_main_r1.json")
    rewrite_json(p, lambda d: d.__setitem__("output_throughput", 999.0))
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert exc is None
    assert any(f in failed for f in
               ("perf_csv_tput_matches_benchjson", "perf_summary_recomputed_matches"))


def test_delete_bench_file_fails(worktree):
    os.remove(os.path.join(worktree, "evidence/performance/A_c1/bench_main_r1.json"))
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert exc is None, "missing bench file must be a clean FAIL, not a crash"
    assert "perf_bench_files_exist" in failed


def test_main_pr_max_tokens_mismatch_fails(worktree):
    p = os.path.join(
        worktree,
        "evidence/accuracy/gsm8k_A_full/run_pr/sgl_eval_gsm8k_20261107-135731/metrics.json")
    rewrite_json(p, lambda d: d["gen"].__setitem__("max_tokens", 2048))
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "acc_settings_perfield_symmetric" in failed
    assert "acc_maxtok_n_labels_consistent" in failed


def test_missing_abba_run_fails(worktree):
    csvp = os.path.join(worktree, "results/performance_raw.csv")
    lines = open(csvp).readlines()
    kept = [l for l in lines if not l.startswith("A_c1,pr,2,")]
    assert len(kept) == len(lines) - 1
    open(csvp, "w").writelines(kept)
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert any(f in failed for f in ("perf_abba_completeness", "perf_rowcount_formal_vs_pilot"))


def test_wrong_speedup_in_summary_fails(worktree):
    p = os.path.join(worktree, "results/performance_summary.csv")
    s = open(p).read().replace(
        "1.3175359959641053", "1.45")
    open(p, "w").write(s)
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "perf_summary_recomputed_matches" in failed


def test_kernel_bitwise_flipped_fails(worktree):
    p = os.path.join(worktree, "evidence/kernel/cross_arm_compare.json")
    rows = json.load(open(p))
    rows[0]["bitwise_equal"] = False
    json.dump(rows, open(p, "w"), indent=1)
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "kernel_bitwise_recount" in failed


def test_kernel_case_removed_fails(worktree):
    p = os.path.join(worktree, "evidence/kernel/kernel_results.json")
    rows = json.load(open(p))
    json.dump(rows[:16], open(p, "w"), indent=1)
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "kernel_case_count_recount" in failed


def test_stale_doc_path_fails(worktree):
    p = os.path.join(worktree, "README.md")
    s = open(p).read().replace("## Contents",
                               "## Contents\n\nSee `scripts/never_committed_helper.sh` for details.")
    open(p, "w").write(s)
    import subprocess
    r = subprocess.run([sys.executable,
                        os.path.join(worktree, "scripts/verify_reproduction_paths.py")],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "scripts/never_committed_helper.sh" in r.stdout


def test_blocked_gate_flipped_to_pass_fails(worktree):
    p = os.path.join(worktree, "results/regression_gates.csv")
    s = open(p).read().replace("Model C (Qwen3-8B) serving,BLOCKED",
                               "Model C (Qwen3-8B) serving,PASS")
    open(p, "w").write(s)
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "doc_gates_blocked_rows_retained" in failed


def test_seal_tamper_fails(worktree):
    # raw evidence tamper that ONLY the seal check catches (content not used in
    # recomputation): append a byte to an environment log
    p = os.path.join(worktree, "evidence/environment/free_h_20261107T070543Z.txt")
    with open(p, "a") as f:
        f.write("\n")
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "seal_raw_evidence_unchanged" in failed


def test_readme_speedup_tamper_fails(worktree):
    p = os.path.join(worktree, "README.md")
    s = open(p).read().replace("| 0.984 | 1.00 | 1.047 | 1.105 | 1.166 | **1.318** |",
                               "| 0.984 | 1.00 | 1.047 | 1.105 | 1.166 | **1.418** |")
    open(p, "w").write(s)
    failed, exc, ok = run_audit(worktree)
    assert not ok
    assert "doc_readme_headline_matches_recompute" in failed
