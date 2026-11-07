# Kernel Correctness — Phase 2 (gfx1100, Triton 3.6.0+rocm7.2.0)

Arms: Main 0afb736 vs PR 3fdf6f7 + local gfx1100 gate patch.
All tensors deterministic per case (SHA256-derived seeds); identical inputs on both arms.

## 1. Launch-configuration proof (real GPU launches, Triton compile options captured)

| shape (qualifies?) | Main | PR + gfx1100 patch |
|---|---|---|
| b16, h16/kv8, d128, bf16 (yes) | 4 warps + waves_per_eu=1, matrix_instr_nonkdim=16, kpack=2 | **2 warps, hints absent** |
| b1, h16/kv8, d128 (boundary: batch*head_tiles=8) | 4 warps + hints | **2 warps, hints absent** |
| b1, h16/kv2, d128 (tiny grid: 1*2=2 < 8) | 4 warps + hints | 4 warps + hints (unchanged) |
| b3, h16/kv2, d128 (6 < 8) | 4 warps + hints | 4 warps + hints (unchanged) |
| b4, h16/kv8, d256 (head_dim 256) | 4 warps + hints | 4 warps + hints (unchanged) |

Serving-context proof: a one-off instrumented server (Triton JIT run spy; no
measured-run contamination) recorded **672 consecutive
`_fwd_grouped_kernel_stage1` launches, every one `num_warps=2, num_stages=1`,
no CDNA hints** during warmup + generation on the PR arm.

Gate-function unit checks: 15/15 PASS (incl. boundary batch*head_tiles==8
qualifies, 7<8 keeps hints; MLA/fp8-KV/fp32/uint8/head_dim>128 keep hints).

## 2. Numerical correctness vs fp32 torch reference (17 cases)

head_dim {64,128,256} x dtype {bf16,fp16} x GQA {32/8, 16/8, 16/2, 16/4, 8/8
(MHA), 7/1} x batch {1..64} x context {1..8192, ragged} x fp8-e4m3 KV.

- Both arms: all outputs finite, max abs error 4e-4 .. 1.2e-3 (bf16) /
  4e-5 .. 1.3e-4 (fp16) — expected rounding magnitude vs an fp32 reference.
- Identical error envelope on both arms (same numerics quality).

## 3. Cross-arm bitwise equality

All **17/17 cases bitwise identical** between Main and PR outputs (exact fp32
preservation; no lossy casts). The launch-config change does not alter this
kernel's accumulation order on gfx1100 — consistent with the PR's own
gfx1151/Triton 3.6 finding, and now also verified under Triton 3.6.0+rocm7.2.

Distinctions kept separate (per campaign rules):
1. **Kernel correctness** (this file): outputs correct vs reference on each arm.
2. **Numerical closeness**: error magnitudes equal on both arms.
3. **Bitwise equality**: 17/17 identical across arms at kernel level.
4. **Served-model correctness**: GSM8K, see results/accuracy_summary.csv — a
   separate claim; kernel-level equality does not by itself prove identical
   generations (batching, GEMM tiling and scheduling still vary run-to-run).

## 4. Registered test suites at the tested revisions

| suite | Main | PR |
|---|---|---|
| test_gfx115_decode_launch.py (PR-added file) | n/a (file absent) | 6/6 PASS |
| test_mla_decode_geometry.py | 16 PASS (subset rerun) | 16 PASS |
| test_mla_decode_forced_splits.py | 4 SKIP (gfx95-only tuning) | 4 SKIP (same) |
| test_triton_attention_kernels.py | 13 PASS, 2 SKIP (gfx950/triton3.7), 1 FAIL (OOM: needs 8.28 GiB, host co-tenant leaves ~5) | identical outcome |
| test_norm.py (AOT) | n/a (norm ops not in ROCm AOT subset) | — |

The single failing test (`test_extend_attention_sliding_window`) fails
**identically on both arms** with `torch.OutOfMemoryError` under the co-tenant
memory constraint — an environment limitation, not a regression (see
LIMITATIONS.md).

Raw artifacts: evidence/kernel/*.{json,log}, evidence/source/decode_attention_*.py,
scripts/kernel_ab.py, configs/kernel_cases.json.
