# Evidence Audit V2 (independent recomputation)

- Auditor version: `evidence-audit-v2.1.0`
- Generated (UTC): 2026-11-08T03:18:56.379594+00:00
- Git SHA: `a18e383e1229d6d415e01483b72b324a2b6bc463`
- Sealed-manifest digest (sha256 of evidence/checksums/SHA256SUMS): `ebf793beedaca9813606f4787a91347fd9ad210f4fc6472234ea49084268d257`

**Overall: PASS** — 55 PASS / 0 FAIL / 0 BLOCKED of 55 checks

Relationship to the historical audit: `evidence/EVIDENCE_AUDIT.md` (22 checks, 2026-11-07) is retained unchanged as a historical artifact. This V2 report is an independent, stricter recomputation performed in the 2026-11 audit round; where the two disagree, V2 governs.

| # | id | category | status | detail | evidence |
|---|---|---|---|---|---|
| 1 | src_main_verified | source | PASS | recorded verified=True | evidence/source/verify_main.json |
| 2 | src_main_filecount_recount | source | PASS | tree blob recount=12039, recorded expected_files=12039 | evidence/source/tree_main.json |
| 3 | src_pr_verified | source | PASS | recorded verified=True | evidence/source/verify_pr.json |
| 4 | src_pr_filecount_recount | source | PASS | tree blob recount=12040, recorded expected_files=12040 | evidence/source/tree_pr.json |
| 5 | src_main_deltas_limited | source | PASS | main deltas=['python/pyproject.toml', 'python/sglang/kernels/aot/include/utils.h', 'python/sglang/kernels/aot/pyproject.toml', 'python/sglang/kernels/aot/setup_rocm.py'] | evidence/source/arm_tree_deltas.json |
| 6 | src_pr_deltas_plus_gate | source | PASS | pr deltas=['python/pyproject.toml', 'python/sglang/kernels/aot/include/utils.h', 'python/sglang/kernels/aot/pyproject.toml', 'python/sglang/kernels/aot/setup_rocm.py', 'python/sglang/kernels/ops/attention/decode_attention.py'] | evidence/source/arm_tree_deltas.json |
| 7 | src_shared_env_patches_identical | source | PASS | both arms carry exactly the same 4 build/env files; PR adds only the gate file | evidence/source/arm_tree_deltas.json |
| 8 | src_gate_patch_archived_consistency | source | PASS | PR archive has the gate fn/import; main archive has none; local patch context lines all present in the PR copy | evidence/source/decode_attention_{main,pr}.py + patches/*.applied.diff |
| 9 | src_pr_commit_scope | source | PASS | PR commit touches ['python/sglang/kernels/ops/attention/decode_attention.py', 'test/registered/unit/layers/attention/test_gfx115_decode_launch.py'] | evidence/source/pr_diff_files.json |
| 10 | src_gate_patch_shape | source | PASS | applied.diff adds 6 lines | patches/pr48969-gfx1100-validation.applied.diff |
| 11 | kernel_case_count_recount | kernel | PASS | 17 cases | evidence/kernel/kernel_results.json |
| 12 | kernel_all_ok_finite | kernel | PASS | 17/17 ok+finite | evidence/kernel/kernel_results.json |
| 13 | kernel_bitwise_recount | kernel | PASS | 17/17 bitwise_equal with cross_arm_max_abs==0 | evidence/kernel/cross_arm_compare.json |
| 14 | kernel_names_crossfile_consistent | kernel | PASS | 17 shared names | kernel_results vs cross_arm_compare |
| 15 | kernel_reference_rows_ok | kernel | PASS | 17+17 reference rows, all ok+finite, names match | evidence/kernel/ref_*/reference_rows.json |
| 16 | kernel_pt_artifacts_exist | kernel | PASS | 17 cases x 2 arms | evidence/kernel/ref_*/**.pt |
| 17 | kernel_csv_matches_json | kernel | PASS | 17 csv rows all bitwise True | results/kernel_correctness.csv |
| 18 | capture_pr_qualifying_2warps_nohints | kernel | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 2, 'num_stages': 1} | evidence/kernel/capture_pr.json |
| 19 | capture_pr_boundary_2warps_nohints | kernel | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 2, 'num_stages': 1} | evidence/kernel/capture_pr.json |
| 20 | capture_pr_tiny_grid_b1_h16_kv2_d128_bf16_unchanged | kernel | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 4, 'num_stages': 1, 'waves_per_eu': 1, 'matrix_instr_nonkdim': 16, 'kpack': 2} | evidence/kernel/capture_pr.json |
| 21 | capture_pr_tiny_grid_b3_h16_kv2_d128_bf16_unchanged | kernel | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 4, 'num_stages': 1, 'waves_per_eu': 1, 'matrix_instr_nonkdim': 16, 'kpack': 2} | evidence/kernel/capture_pr.json |
| 22 | capture_pr_hd256_b4_h16_kv8_d256_bf16_unchanged | kernel | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 4, 'num_stages': 1, 'waves_per_eu': 1, 'matrix_instr_nonkdim': 16, 'kpack': 2} | evidence/kernel/capture_pr.json |
| 23 | capture_main_all_hints_4warps | kernel | PASS | 5 shapes all 4warps+hints | evidence/kernel/capture_main.json |
| 24 | capture_excluded_identical_across_arms | kernel | PASS | excluded shapes byte-identical config main vs pr | capture_{main,pr}.json |
| 25 | serving_spy_all_2warps_recount | kernel | PASS | 672 launches, all num_warps=2 no hints | logs/server/spy_pr.jsonl |
| 26 | arch_gates_recount | kernel | PASS | 22/22 sub-gates ok, recorded overall_pass=True | evidence/regression/arch_gates.json |
| 27 | perf_rowcount_formal_vs_pilot | performance | PASS | 60 formal + 4 pilot = 64 rows | results/performance_raw.csv |
| 28 | perf_bench_files_exist | performance | PASS | missing=[] | evidence/performance/**/bench_*.json |
| 29 | perf_no_warmup_in_measured_set | performance | PASS | no warmup artifacts in measured rows | results/performance_raw.csv |
| 30 | perf_completed_equals_prompts | performance | PASS | bad=[] | bench JSONs vs performance_raw.csv |
| 31 | perf_params_match_csv | performance | PASS | bad=[] | bench JSONs vs performance_raw.csv |
| 32 | perf_csv_tput_matches_benchjson | performance | PASS | bad=[] | bench JSONs vs performance_raw.csv |
| 33 | perf_multidoc_bench_files_documented | performance | PASS | multidoc files=[('evidence/performance/A_c4/bench_main_r1.json', 2), ('evidence/performance/A_c4/bench_pr_r1.json', 2)] (A_c4 r1: abandoned 0.30 attempt + final 0.75 leg; CSV verified equal to the LAST doc) | evidence/performance/A_c4/*.json |
| 34 | perf_abba_completeness | performance | PASS | all 16 cells have main r1/r2 + pr r1/r2; bad=[] | evidence/performance/*/ |
| 35 | perf_arm_parameters_symmetric | performance | PASS | per-cell Main/PR bench parameters identical; issues=[] | bench JSONs (recomputed) |
| 36 | perf_launch_command_matches_committed_launcher | performance | PASS | all 64 legs' server launch_command == template generated by scripts/launch_server.sh; issues=[] | bench JSON server_info.launch_command vs scripts/launch_server.sh |
| 37 | perf_summary_recomputed_matches | performance | PASS | 15 formal + 1 pilot summary rows recomputed from bench JSONs; issues=[] | results/performance_summary.csv vs bench JSONs |
| 38 | perf_decode_ms_reextracted | performance | PASS | 64/64 legs re-extracted from server logs (author methodology); issues=[] | server_*_r*.log vs decode_ms_per_run.json + performance_raw.csv |
| 39 | perf_runspread_claim_supported | performance | PASS | recomputed throughput spreads 0.00–3.03%; documented range=0.0–3.0% (LIMITATIONS L7 corrected in this round) | bench JSONs + LIMITATIONS.md L7 |
| 40 | acc_metrics_count | accuracy | PASS | 10/10 metrics.json (5 pairs x 2 arms) | evidence/accuracy/**/metrics.json |
| 41 | acc_settings_perfield_symmetric | accuracy | PASS | per-field Main/PR equality for temperature/max_tokens/seed/top_p/num_examples/num_threads; issues=[] | metrics.json (recomputed) |
| 42 | acc_maxtok_n_labels_consistent | accuracy | PASS | A=1024(1024-runs), A_full_2048=2048, B=2048; diag n=200, full n=1319; bad=[] | metrics.json (recomputed) |
| 43 | acc_summary_matches_metrics | accuracy | PASS | 10 rows cross-checked; issues=[] | results/accuracy_summary.csv |
| 44 | acc_deltas_recomputed | accuracy | PASS | PR−Main deltas (pp): [('gsm8k_A_diag', 0.5), ('gsm8k_A_full', -0.758), ('gsm8k_A_full_2048', 0.303), ('gsm8k_B_diag', -0.5), ('gsm8k_B_full', 0.227)]; all |Δ| ≤ 1.5 pp (within ~1σ binomial at n=1319) | metrics.json (recomputed) |
| 45 | acc_server_memconfig_symmetric_and_manifest | accuracy | PASS | per-pair server memfrac/max-total-tokens from server logs; issues=[] | evidence/accuracy/*/server_*.log vs configs/eval_config.yaml |
| 46 | acc_paired_ids_aligned | accuracy | PASS | per-question ids align 1:1 for all 5 pairs; issues=[] | output-rs0.jsonl (recomputed) |
| 47 | acc_paired_counts_recomputed | accuracy | PASS | {"gsm8k_A_diag": {"both_correct": 92, "both_wrong": 73, "discordant": 35, "n": 200}, "gsm8k_A_full": {"both_correct": 647, "both_wrong": 490, "discordant": 182, "n": 1319}, "gsm8k_A_full_2048": {"both_correct": 823, "both_wrong": 322, "discordant": 174, "n": 1319}, "gsm8k_B_diag": {"both_correct": 167, "both_wrong": 26, "discordant": 7, "n": 200}, "gsm8k_B_full": {"both_correct": 1125, "both_wrong": 163, "discordant": 31, "n": 1319}} | output-rs0.jsonl (recomputed) |
| 48 | doc_readme_headline_matches_recompute | documents | PASS | issues=[] | README.md vs bench JSON recompute |
| 49 | doc_final_report_table_matches_recompute | documents | PASS | A (10 rows) + B (5 rows) x 3 ratios checked; issues=[] | FINAL_VALIDATION_REPORT.md §3/§4 vs bench JSON recompute |
| 50 | doc_final_report_gsm8k_matches_metrics | documents | PASS | issues=[] | FINAL_VALIDATION_REPORT.md §5 vs metrics.json |
| 51 | doc_reply_draft_numbers_match_recompute | documents | PASS | issues=[] | GITHUB_REPLY_DRAFT.md vs recompute |
| 52 | doc_gates_blocked_rows_retained | documents | PASS | BLOCKED/NOT_RUN rows must never be flipped to PASS; issues=[] | results/regression_gates.csv |
| 53 | doc_gates_measured_legs_count | documents | PASS | G9 evidence string must state the recomputed 60 formal measured legs (60 = 15 cells x 2 arms x 2 runs; the 4 _pilot4x legs are excluded) | results/regression_gates.csv |
| 54 | seal_raw_evidence_unchanged | integrity | PASS | 676 entries; unexpected mismatches=[]; missing=[]; 10 tooling/config files repaired this round (documented) | evidence/checksums/SHA256SUMS |
| 55 | seal_no_undocumented_changes | integrity | PASS | every mismatching path must be in the documented repaired list | audit/SHA256SUMS_AUDIT_ROUND |
