# CLAIM-TO-EVIDENCE MATRIX — cross-document reconciliation (audit round 2026-11)

Every publicly stated conclusion mapped to its raw evidence, the independently
recomputed value, and the verification method. "Recalc" values come from
`scripts/verify_evidence_v2.py` / `recompute_performance.py` /
`recompute_accuracy.py` (executed via `bash scripts/audit_local.sh`), not from
the summary CSVs. Status: VERIFIED = independently recomputed; DISCLOSED =
honest limitation documented; UNVERIFIED = cannot be supported by archived
evidence (none remain after this round's corrections).

## C1. Provenance / source identity

| Claim | Evidence path | Recalculated value | Verification | Status | Limitation |
|---|---|---|---|---|---|
| Main = `0afb736d…67a6`, byte-verified | evidence/source/verify_main.json + tree_main.json | tree blob recount 12,039 == recorded; verified=true; deltas = 4 build files only | V2 `src_main_verified`, `src_main_filecount_recount`, `src_main_deltas_limited` | VERIFIED | tree JSONs fetched from GitHub API at campaign time (trusted then, archived) |
| PR = `3fdf6f73…9eca`, byte-verified | evidence/source/verify_pr.json + tree_pr.json | recount 12,040; PR deltas = 4 build files + decode_attention.py (gate patch) only | V2 `src_pr_*`, `src_pr_deltas_plus_gate`, `src_shared_env_patches_identical` | VERIFIED | same as above |
| Local gate patch is 6 added lines, gfx115x untouched | patches/pr48969-gfx1100-validation.{patch,applied.diff}; evidence/source/decode_attention_pr.py | applied.diff adds exactly 6 lines; PR archive contains gate fn; main archive has none; patch context applies to PR copy | V2 `src_gate_patch_shape`, `src_gate_patch_archived_consistency` | VERIFIED | |
| PR commit touches only decode_attention.py + its test | evidence/source/pr_diff_files.json | exactly those 2 files | V2 `src_pr_commit_scope` | VERIFIED | |

## C2. Gate activation (the optimization really ran)

| Claim | Evidence path | Recalculated | Verification | Status | Limitation |
|---|---|---|---|---|---|
| Qualifying shapes (b16 h16/kv8 d128; boundary b1 h16/kv8) compile num_warps=2, no CDNA hints on PR arm | evidence/kernel/capture_pr.json | confirmed per shape | V2 `capture_pr_qualifying/boundary_2warps_nohints` | VERIFIED | |
| Excluded shapes (tiny grids, hd256) unchanged | capture_pr.json vs capture_main.json | excluded configs byte-identical across arms | V2 `capture_pr_*_unchanged`, `capture_excluded_identical_across_arms` | VERIFIED | |
| Main arm always hints+4warps | evidence/kernel/capture_main.json | 5/5 shapes | V2 `capture_main_all_hints_4warps` | VERIFIED | |
| 672/672 live serving launches num_warps=2 (instrumented server, not during measured runs) | logs/server/spy_pr.jsonl; evidence/performance/*/server_*.log | 672 records, all 2warps/no hints | V2 `serving_spy_all_2warps_recount`; L6 instrumentation disclosure | VERIFIED | spy covers one session, PR arm only (by design) |

## C3. Kernel correctness

| Claim | Evidence | Recalculated | Verification | Status | Limitation |
|---|---|---|---|---|---|
| 17/17 cases bitwise identical across arms | evidence/kernel/{kernel_results.json, cross_arm_compare.json, ref_*/}; results/kernel_correctness.csv | 17 rows, all bitwise_equal && max_abs==0; names consistent across 4 files; 34 .pt artifacts exist; all finite & within fp tolerance of fp32 reference | V2 `kernel_*` (7 checks) | VERIFIED | synthetic shapes, not a served model |
| Registered suites: PR test 6/6; MLA identical; triton 13 PASS + 2 SKIP + 1 OOM both arms | evidence/kernel/test_*.log | (logged outputs; OOM identical on both arms) | retained as logged; OOM disclosed in L5/G9 | DISCLOSED | sliding-window case not actually validated (OOM) |

## C4. Performance — model A (Qwen3-0.6B)

Headline e2e output-throughput ratios (PR/Main, median of 2 runs/arm, ABBA),
recomputed from bench JSONs; doc sources: README, FINAL_VALIDATION_REPORT §3,
GITHUB_REPLY_DRAFT:

| cell | published | recomputed | matches docs (rounded) | Status |
|---|---|---|---|---|
| c=1 | 0.984 | 0.98418 | README/FVR/draft | VERIFIED |
| c=4 | 1.00 | 0.99842 | README (2dp) | VERIFIED |
| c=8 | 1.047 | 1.04750 | all | VERIFIED |
| c=16 | 1.105 | 1.10467 | all | VERIFIED |
| c=32 | 1.166 | 1.16650 | all | VERIFIED |
| c=64 | 1.318 | 1.31754 | all | VERIFIED |
| 8k c=8 | 1.072 | 1.07178 | FVR/draft | VERIFIED |
| 4k c=8 | 1.047 | 1.04681 | FVR | VERIFIED |
| mixed c=16 | 1.019 | 1.01934 | FVR | VERIFIED |
| mixed c=32 | 1.015 | 1.01473 | FVR | VERIFIED |

Supporting layers at c=64 (STATISTICAL_RECONCILIATION §4): decode step 1.053×,
client ITL 1.326×, e2e 1.318×; identical work confirmed (64/64 completed,
16,384 tokens, same running-req ramp, 23 prefill batches, 9.6 s vs 7.3 s).
Audit checks: `perf_*` (13 checks incl. ABBA completeness, per-arm parameter
symmetry, completed==prompts, medians/speedups recompute, decode re-extraction
for all 64 legs, launch-command equivalence with the committed launcher).

## C5. Performance — model B (Qwen2.5-3B): c16 0.993 / c32 1.014 / c64 1.021 / 8k 1.018 / mixed 0.988

Recomputed 0.99342 / 1.01402 / 1.02142 / 1.01841 / 0.98849 — all match FVR §4
(V2 `doc_final_report_table_matches_recompute`). Caveat recorded: the ~1–2%
magnitudes are near the within-cell spread in some cells (SR §2). Status:
VERIFIED (numbers), DISCLOSED (precision caveat).

## C6. Batch-1 regression (corrected in this round)

| Claim (corrected) | Evidence | Recalculated | Status |
|---|---|---|---|
| −1.6% e2e throughput / +1.8% ms/step at c=1, consistent sign across all 4 ABBA legs, **one** memory configuration | evidence/performance/A_c1/* | main 131.83/132.94 vs pr 130.26/130.32 tok/s; ms/step 7.42/7.40 vs 7.55/7.55 | VERIFIED |
| "Reproduced under two memory configurations" — **withdrawn**: the two-memory-config reproduction was at c=16 (pilot `_pilot4x_A_c16` @0.30 vs `A_c16` @0.75+100k, medians equal to 4 sig figs) | runner.log first lines of both cells + bench JSONs | pilot 1161.7/1269.9 vs formal 1200.0/1325.7 (different request counts 4×, documented as reproduction of *medians*, not identical workload) | CORRECTED — old claim UNVERIFIED, replacement VERIFIED |

## C7. GSM8K

| Claim | Evidence | Recalculated | Status |
|---|---|---|---|
| 5 pairs, per-pair symmetric settings (temp 0, top_p 0.95, seed 0, threads 64, n, max_tokens) | metrics.json ×10 | per-field equality; max_tokens 1024/1024/2048/2048/2048 per pair — no 1024/2048 confusion | VERIFIED |
| Scores as published (A 56.33→55.57, 68.84→69.14; B 85.50→85.00 diag, 86.35→86.58) | metrics.json + per-question recompute | exact match incl. per-question sum (743/733, 908/912, 1139/1142 …) | VERIFIED |
| "No detectable systematic accuracy change" | output-rs0.jsonl ×10 | exact McNemar p = 1.000/0.505/0.820/1.000/0.720 | VERIFIED (claim strengthened from σ-argument to paired test; formal equivalence NOT claimed) |

## C8. Environment & constraints

| Claim | Evidence | Status |
|---|---|---|
| ROCm 7.2.1 / torch 2.9.1+gitff65f5b / Triton 3.6.0+rocm7.2.0 / sgl-eval 0.1.3 / Python 3.12 | configs/environment_manifest.json + evidence/environment/* | VERIFIED (recorded); matches ENVIRONMENT.md |
| Co-tenant holds 33.26 GB of 51.52 GB (48 GiB) for whole campaign; symmetric control; magnitude-invariance NOT excluded | evidence/environment/rocm_smi_mem_*.txt; LIMITATIONS L1 (rewritten this round) | DISCLOSED |
| Arm-symmetric workarounds (norm shim on hot path, aiter shim unused, gfx1100 sgl-kernel build) | scripts/{norm_compat,aiter_compat_shim}.py; patches/sgl-kernel-gfx1100.sh; LIMITATIONS L2 (rewritten) | DISCLOSED |
| Coverage gaps: Qwen3-8B BLOCKED, Phi-4-mini BLOCKED, 14B/gpt-oss NOT_RUN, MLA e2e NOT_RUN, hd256 e2e NOT_RUN, sliding-window OOM, deterministic not verified | results/regression_gates.csv + LIMITATIONS L5 | DISCLOSED (BLOCKED/NOT_RUN never flipped — enforced by V2 `doc_gates_blocked_rows_retained`) |

## C9. Audit & counts

| Claim | Evidence | Recalculated | Status |
|---|---|---|---|
| Historical audit 22/22 PASS | evidence/EVIDENCE_AUDIT.md (retained, historical) | reproduced at baseline (22 checks) | VERIFIED as historical record |
| Audit V2 (this round) 55/55 PASS | evidence/EVIDENCE_AUDIT_V2.{md,json} | generated by independent recomputation, fail-closed, with 11 tamper regression tests (tests/) | VERIFIED |
| 60 formal measured bench legs (+4 pilot, excluded) | results/performance_raw.csv | 60 = 15 cells × 2 arms × 2 runs; gates G9 corrected from the stale "48" | VERIFIED |

## C10. Reproducibility

| Claim | Evidence | Status |
|---|---|---|
| CPU-only audit from clean clone | scripts/audit_local.sh + REPRODUCE.md §7 | VERIFIED (executed in Phase 8 of this round) |
| T1 gaps stated (uncommitted work/*; unarchived intermediate GSM8K script versions; multi-doc A_c4 bench files) | audit/BASELINE_INVENTORY.md §4/§6; evidence/accuracy/EXECUTION_MANIFEST.md | DISCLOSED |
| No new GPU runs in the audit round | git log of the audit branch (doc/tool/test-only diff) | VERIFIED |

## C11. GPU follow-up round 2026-11-08 (owner-authorized; `followup/`)

| Claim | Evidence path | Recalculated value | Verification | Status |
|---|---|---|---|---|
| c=1 regression reproduced under a second memory configuration (0.30/auto) | followup/evidence_performance/A_c1_mem030/ | tput spd 0.9858×, ms/step spd 0.9834× | verify_followup.py f5/f6 (config read from server args; medians recomputed) | VERIFIED |
| c=1 at 0.75, n=4/arm combined: full leg separation | historical A_c1 + followup A_c1_rep | median 0.9806×; all 4 PR legs < all 4 main legs; same for ms/step | f7 | VERIFIED |
| c=2 neutral (crossover point) | followup/evidence_performance/A_c2/ | tput spd 1.0034×, ms/step 1.0026× | f8 | VERIFIED |
| deterministic-serving cannot start on gfx1100 (LDS 99,328 B > 65,536 B limit), both arms identical | followup/evidence_determinism/server_{main,pr}.log | OutOfResources on both arms | f9 | VERIFIED |
| same GPU + co-tenant unchanged during follow-up | followup/evidence_environment/rocm_smi_mem_*.txt | 33.21 GB / 51.52 GB held | f10 | VERIFIED |
| gate patch state on arms re-verified before follow-up | followup runner logs; pre-round check (`_is_gfx115=True` PR, absent main) | — | run_followup.sh header | VERIFIED |
