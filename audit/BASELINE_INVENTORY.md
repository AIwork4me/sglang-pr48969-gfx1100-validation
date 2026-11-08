# BASELINE INVENTORY — frozen before any modification (Phase 0)

Audit round: P0/P1 evidence & reproducibility closure (CPU-only; no new GPU runs).
Purpose: capture the exact state of the repository before this round's repairs so
that every subsequent change is diffable against this baseline.

## 1. Git identity

- Remote: `https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation.git`
- Baseline branch: `main`
- Baseline HEAD SHA: `fe13f48e2e0d8b19bbd714b26e26ea02b1d90fd4`
  (single commit `SGLang PR #48969 independent gfx1100 (W7900) validation evidence`,
  author AIwork4me, 2026-11-07T17:57:42+00:00)
- Working tree: clean at audit start.
- Repair branch created from baseline: `audit/p0-p1-evidence-closure`.

## 2. Pre-modification SHA256 of key files

| file | sha256 (baseline) |
|---|---|
| README.md | 92cbaf88fce5b85bf963f0f48a96b4553fc8d0e3b66ce677d312fae296779e6e |
| FINAL_VALIDATION_REPORT.md | ff848f38c6519acf3ab72c77f8943ad0388b155065095be5edc69501cd600420 |
| GITHUB_REPLY_DRAFT.md | 6e49ff39a21d18e7beb7530864907a58ce665dbf72eae91f15b818523d58bf98 |
| REPRODUCE.md | 60ce0f32b479295f324100cd3ab8f26dcf0c19feb0f7e0a72e21fbfb9d61a4d3 |
| ENVIRONMENT.md | e48d53df1cc129c3fa57ccd85d94079783f8db28a30fb87fb9da1c425976965c |
| LIMITATIONS.md | 62769a2d1c8b7c720cd44add8bd81cfb76ed55c54dc293f557b36f65c704bcfd |
| REVIEW_REQUEST.md | 506d1807c93815fe524cea04ce0c3da89efa42f2cd852a5bb9d19bb778fea37b |
| configs/benchmark_matrix.yaml | af08f1c0ceae70ec56c99f112d09c2310d9691a465a71c859fab2f71085fe871 |
| configs/eval_config.yaml | 9d6a4155a936e556dbd0e2cde439d38b22be18d3acc4a3fb8db35af34946a7ec |
| configs/environment_manifest.json | 7df25da654d56b32c58b55f94ef868948105fe92212befdc101bd44c6f6b3613 |
| configs/kernel_cases.json | cd7627d35ae3d9abaa1459a3848db51aaee9fbf7d15049765a6c0b11559f21de |
| configs/model_manifest.json | d098df16b9d8515f31a58f1be377d6a91a4a9e43c463ef16772cf2326a9c9888 |
| configs/rocm_flat_deps.txt | 62aef9ba5148c4a2a9e923009c0d93c3b86de66d0c73bbdb0880432f0c804e44 |
| results/performance_raw.csv | 3f2dffa815a11fed02b72a4eae876f31e474fc3140b5f986c72eb8f00b238ed6 |
| results/performance_summary.csv | d9a958a956f0277304fafbb2f9922513a1f892659c811c3d22bfc5959659ede1 |
| results/accuracy_summary.csv | 56c6f70b230d58943295056645d3e2ace76cfc5bdd70c5c8ba87899e9a5398dc |
| results/regression_gates.csv | 1d781df90588fedcd701f5f39ac5b045b99791f78ad8608314feb678c49798ca |
| results/kernel_correctness.csv | 95b3216348e9d3be25b58de086dc7ced0a9bb00552db879324f72428cbd90641 |
| evidence/EVIDENCE_AUDIT.md | a8d98b06408823cadaf023e4ba74d9960767be26c6aa8fc70010e11023a72f71 |
| evidence/checksums/SHA256SUMS | ebf793beedaca9813606f4787a91347fd9ad210f4fc6472234ea49084268d257 |
| evidence/checksums/sources.sha256 | 624107be9f3a83fdd8fb61bcbab67eecb1cc003005589565a9b5e66a51798641 |
| scripts/verify_evidence.py | cd6fbbcb20ebe8cf68035342e9e1a3a9d76d9aeca69199e413e8524555f3d7b4 |
| scripts/run_gsm8k_ab.sh | 685f7a9dcfdc7c54fc3f85dfb494d1001222468402925042b1bf716e6f31539b |
| scripts/run_serving_ab.sh | 0708aebac4a26a555c91bd8a2ea06694a910c708c67bbdc2cb41f82060c3dfe3 |
| scripts/collect_metrics.py | a2200500663070f6aa404b7ee8febd5b450771f76b4e78c8f453569f293293c3 |
| scripts/analyze.py | e3748b662ae386a74d06aa6f2aa448bac658c777268fd6641118709d7c4c0741 |
| scripts/launch_server.sh | b7f11e1f3625c96fab2ac02dd1ce41c623ca21e6f711a97efc6c9552f92537d4 |
| scripts/setup_env.sh | d0e18e075df168e9d94d2bed20b00e17629a348156132561bb33ef37de7784e7 |
| scripts/build_sglkernel.sh | e77fa8fa5acd525a94d8b358d15c3e83d8387906f5bbfd524356496db7b8ecb8 |
| patches/pr48969-gfx1100-validation.patch | 200533a8aac0f6aaf79decea375daed5c246e51be4a967c059653153f8acefd0 |
| patches/sgl-kernel-gfx1100.sh | ff24e5ac361ba767a193e6e4fda73f4e50e1aa9a2345aec5b79d6a7f302b8181 |

## 3. Verification of the sealed manifest `evidence/checksums/SHA256SUMS`

- Entries: 676. `sha256sum -c` result: **676/676 OK, 0 FAILED** (verified 2026-11-08).
- Manifest coverage: 676 of 685 repository files. Files present in the repo but
  **not covered** by the sealed manifest (9): `.gitignore`, `README.md`,
  `FINAL_VALIDATION_REPORT.md`, `GITHUB_REPLY_DRAFT.md`, `LIMITATIONS.md`,
  `REPRODUCE.md`, `REVIEW_REQUEST.md`, `ENVIRONMENT.md`,
  `evidence/checksums/SHA256SUMS` itself (a manifest cannot contain itself).
  These were finalized after the evidence manifest was sealed; they are
  top-level documents, not raw evidence. This round's closure manifest
  (`audit/SHA256SUMS_AUDIT_ROUND`) covers the new/modified files of this round.
- Manifest entries pointing to paths that do **not exist in the repository**:
  none. (All 676 paths exist and hash-verify.)

## 4. `evidence/checksums/sources.sha256` (historical environment files)

Five entries reference the historical campaign workspace
`work/dl/*` (sglang tarballs ×3, parent tarball, Triton wheel):
`a8a7ed94… work/dl/sgl_amd_mono.tar.gz`, `9dea843d… work/dl/main.tar.gz`,
`06dfbc84… work/dl/pr.tar.gz`, `26ee0311… work/dl/pr_parent.tar.gz`,
`bf471aa7… work/dl/triton36.whl`.
These files are **not committed to the repository** (too large / lab-local);
the entries are retained as historical provenance records. They cannot be
re-verified from a clean clone — recorded as a **reproduction gap**, not a
verification pass (see REPRODUCE.md §Historical vs current).

## 5. Raw evidence inventory (counts, formats)

### Performance (serving A/B)
- 16 run cells under `evidence/performance/`: 15 formal cells
  (A_c1, A_c4, A_c8, A_c16, A_c32, A_c64, A_long_4k_c8, A_long_8k_c8,
  A_mixed_c16, A_mixed_c32, B_c16, B_c32, B_c64, B_long_8k_c8, B_mixed_c16)
  plus 1 pilot cell `_pilot4x_A_c16` (memfrac 0.30, num_prompts 4×conc).
- Per formal cell: 4 measured bench JSONs + 4 warmup bench JSONs + client logs,
  2 archived server logs per arm per run, runner.log, telemetry CSVs ×4.
- `results/performance_raw.csv`: 64 rows = 60 formal measured legs
  (15 cells × 2 arms × 2 runs) + 4 pilot legs.
  **Baseline discrepancy:** `evidence/EVIDENCE_AUDIT.md` check `perf_min_rows`
  counted "64 measured rows" including the 4 pilot legs, and
  `results/regression_gates.csv` G9 says "all 48 measured bench legs" —
  neither matches the actual 60 formal / 64 total. Repaired in this round
  (G9 note regenerated via recomputation; pilot rows now excluded by the V2
  auditor's formal-row count and labeled as pilot in summaries).
- `evidence/performance/A_c4/bench_main_r1.json` and `bench_pr_r1.json` each
  contain **two appended JSON documents** (an abandoned memfrac-0.30 attempt at
  15:07–15:11 UTC, then the final memfrac-0.75 leg at 15:20–15:22 UTC).
  `scripts/collect_metrics.py` takes the last document; the CSV rows were
  verified to equal the last (final-0.75) documents. Retained as-is (raw
  evidence is immutable); documented in EXECUTION_MANIFEST and Audit V2.

### Accuracy (GSM8K)
- 5 run pairs × 2 arms = 10 `metrics.json` + 10 `output-rs0.jsonl`:
  gsm8k_A_diag (n=200, max_tokens 1024), gsm8k_A_full (1319, 1024),
  gsm8k_A_full_2048 (1319, 2048), gsm8k_B_diag (200, 2048),
  gsm8k_B_full (1319, 2048). Plus per-pair runner/server/sgl-eval logs.
- `configs/eval_config.yaml` lists a run `gsm8k_A_full_repeat_main` that does
  **not exist** in evidence and omits `gsm8k_A_full_2048`, which does exist —
  config drift against raw evidence (repaired this round).

### Kernel
- 17-case sweep: `kernel_results.json` + `results/kernel_correctness.csv`
  (17/17 `cross_arm_bitwise_equal=true`), reference rows
  (`ref_main/reference_rows.json`, `ref_pr/reference_rows.json`, both 17 rows,
  all ok+finite), per-case `.pt` outputs (17 × 2 arms).
- Launch captures `capture_main.json` / `capture_pr.json` (5 shape keys each),
  `launch_capture_summary.json`, serving spy `logs/server/spy_pr.jsonl`
  (672 launches, all num_warps=2, no CDNA hints).

### Source integrity
- `verify_main.json` / `verify_pr.json`: verified=true (12,039 / 12,040 files).
- `arm_tree_deltas.json`: main diffs = 4 documented build files; pr adds only
  `decode_attention.py` (the gate patch).
- PR metadata: `pr_diff_files.json` (2 files), `pr_body.txt`,
  `pr_commit_files_with_patch.jsonl`, archived copies of the touched sources.

## 6. Paths referenced by documents but not present in the repository

Historical campaign root was `/root/sglang-pr48969-validation` with an
uncommitted `work/` directory. References that cannot be resolved from a clean
clone (verified by `scripts/verify_reproduction_paths.py` added this round):

| Reference | Found in | Status |
|---|---|---|
| `work/run_final.sh` | REPRODUCE.md §4 | **not committed; not reconstructible** → documented reproduction gap (the full grid is reconstructible from per-cell runner.log command lines) |
| `work/build_sglkernel.sh` | REPRODUCE.md §1 | equivalent committed copy `scripts/build_sglkernel.sh`; byte-identity with the executed file **unprovable** (work/ not committed) |
| `work/aiter_compat_shim.py`, `work/norm_compat.py` | REPRODUCE.md §1 | equivalent committed copies `scripts/aiter_compat_shim.py`, `scripts/norm_compat.py`; byte-identity unprovable |
| `work/launch_server.sh` | run_serving_ab.sh / run_gsm8k_ab.sh (`$CAMP/work/launch_server.sh`) | equivalent committed copy `scripts/launch_server.sh`; corroborated by archived server launch_command lines; byte-identity unprovable |
| `work/venv_<arm>`, `work/venv_eval` | REPRODUCE.md, run scripts | historical venvs (not committable); recreate via `scripts/setup_env.sh` |
| `work/venv_<arm>/python` | REPRODUCE.md §3 | wrong path even historically — venv python is `work/venv_<arm>/bin/python` (typo fixed this round) |
| `sha256sum ... > evidence/checksums/SHA256SUMS` | REPRODUCE.md §6 | unfinished placeholder command (fixed this round) |
| `CAMP=/root/sglang-pr48969-validation` | all run scripts | hardcoded historical absolute path (fixed: repo-root relative, see §7) |
| `gsm8k_A_full_repeat_main` | configs/eval_config.yaml runs list | run never executed; entry removed / corrected this round |

## 7. Historical evidence vs current working tree — differences

- No raw evidence file has been modified since the manifest seal (676/676 OK).
- Only top-level documents (README, reports, REPRODUCE, etc.) and this round's
  new audit/ files differ from the sealed set — those were never part of the
  sealed evidence manifest (§3).
- This round explicitly does NOT touch: any file under `evidence/` raw data
  (bench JSON, metrics.json, jsonl, kernel .pt, captures, spy log), the sealed
  `evidence/checksums/SHA256SUMS`, `results/*.csv` raw/summary values, or
  `patches/`. Audit V2 outputs go to new files
  (`evidence/EVIDENCE_AUDIT_V2.md` / `.json` are *reports about* evidence,
  generated artifacts, clearly separated from the sealed raw evidence and from
  the historical `EVIDENCE_AUDIT.md`, which is retained unchanged as a
  historical artifact).

## 8. Baseline audit status (as found)

- Historical `scripts/verify_evidence.py`: 22/22 PASS (report
  `evidence/EVIDENCE_AUDIT.md`, 2026-11-07T17:56:22). Independently re-run at
  baseline: reproduces 22/22. Weaknesses identified for V2 (this round):
  1. `accuracy_*_symmetric_settings` used `len(set(map(str,g))) <= 4` — cannot
     prove per-field Main/PR equality (e.g. a Main max_tokens of 1024 vs PR 2048
     paired with a compensating swap of another field could pass in principle;
     and missing-vs-null is not distinguished).
  2. `perf_min_rows >= 40` counted pilot rows as measured rows.
  3. No recompute of medians/speedups from raw bench JSONs (trusted CSVs).
  4. No ABBA-completeness check per cell; no completed==num_prompts check;
     no warmup exclusion check; no per-arm run-count check.
  5. No accuracy score/truncation recompute from metrics.json (trusted CSV).
  6. No decode-ms/step re-extraction from server logs (trusted stored series).
  7. Trusts `arch_gates.json` `overall_pass` flag without recounting sub-gates.
  8. No exit-status / BLOCKED propagation contract.

**Gate P0 status: BASELINE CAPTURED BEFORE MODIFICATIONS — PASS.**
