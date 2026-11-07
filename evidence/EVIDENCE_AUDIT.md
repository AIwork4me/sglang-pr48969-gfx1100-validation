# Evidence Audit (Phase 10)

Generated: 2026-11-07T17:56:22.032942

**Overall: PASS** (22/22 checks)

| check | status | detail |
|---|---|---|
| pr_qualifying_2warps_nohints | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 2, 'num_stages': 1} |
| pr_tiny_grid_b1_h16_kv2_d128_bf16_unchanged | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 4, 'num_stages': 1, 'waves_per_eu': 1, 'matrix_instr_nonkdim': 16, 'kpack': 2} |
| pr_tiny_grid_b3_h16_kv2_d128_bf16_unchanged | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 4, 'num_stages': 1, 'waves_per_eu': 1, 'matrix_instr_nonkdim': 16, 'kpack': 2} |
| pr_hd256_b4_h16_kv8_d256_bf16_unchanged | PASS | {'kernel': '_fwd_grouped_kernel_stage1', 'num_warps': 4, 'num_stages': 1, 'waves_per_eu': 1, 'matrix_instr_nonkdim': 16, 'kpack': 2} |
| main_qualifying_b16_h16_kv8_d128_bf16_hints4warps | PASS |  |
| main_boundary_b1_h16_kv8_d128_bf16_hints4warps | PASS |  |
| main_tiny_grid_b1_h16_kv2_d128_bf16_hints4warps | PASS |  |
| main_tiny_grid_b3_h16_kv2_d128_bf16_hints4warps | PASS |  |
| main_hd256_b4_h16_kv8_d256_bf16_hints4warps | PASS |  |
| kernel_17cases_bitwise_equal | PASS | 17 rows |
| kernel_reference_all_finite_ok | PASS |  |
| serving_spy_all_2warps | PASS | 672 launches |
| source_verified_main | PASS | 12039 files |
| source_verified_pr | PASS | 12040 files |
| main_only_documented_deltas | PASS | ['python/pyproject.toml', 'python/sglang/kernels/aot/include/utils.h', 'python/sglang/kernels/aot/pyproject.toml', 'python/sglang/kernels/aot/setup_rocm.py'] |
| pr_deltas_plus_gate_patch | PASS | ['python/pyproject.toml', 'python/sglang/kernels/aot/include/utils.h', 'python/sglang/kernels/aot/pyproject.toml', 'python/sglang/kernels/aot/setup_rocm.py', 'python/sglang/kernels/ops/attention/decode_attention.py'] |
| accuracy_metrics_exist | PASS | 10 metric files |
| perf_rows_have_bench_files | PASS | [] |
| decode_series_medians_present | PASS | [] |
| perf_min_rows | PASS | 64 measured rows |
| gate_patch_exists | PASS |  |
| arch_gates_all_pass | PASS |  |
