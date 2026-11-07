# FINAL VALIDATION REPORT — SGLang PR #48969 on gfx1100

Independent A/B validation for @twoask's request
(https://github.com/sgl-project/sglang/pull/48969#issuecomment-6703266031).

- **Hardware**: AMD Radeon PRO W7900 48GB (gfx1100, RDNA3.0, 96 CU, wave32)
- **Arms**: Main `0afb736d0aab96e3ab80b4c54a376213a1db67a6` vs PR `3fdf6f7318364c1b09398aea4d947ed633ac9eca`
  (single-commit diff vs parent `025b8806`; full branch = 2 commits; merge-base = Main; verified via GitHub trees API)
- **PR arm carries one local, temporary patch** (`patches/pr48969-gfx1100-validation.patch`):
  the `_is_gfx115` gate additionally accepts exactly `gfx1100`. No other change;
  gfx115x behavior untouched; Main arm untouched.
- **Stack**: ROCm 7.2.1 (HIP 7.2.53), torch 2.9.1+gitff65f5b (rocm7.21), Triton
  3.6.0+rocm7.2.0.gitba5c1517, sgl_kernel built from each arm's tree for gfx1100
  (official wave32 patch), sgl-eval 0.1.3. Both arms identical (ENVIRONMENT.md).
- **Serving**: `SGLANG_DISABLE_LEAN_ATTENTION=1`, `--attention-backend triton`,
  `--context-length 10240`, `--mem-fraction-static 0.75`, ABBA ordering
  (main→pr→pr→main), warmup-separated, 2 measured runs per arm per cell,
  `python -m sglang.benchmark.serving --dataset-name random --random-input-len 1024
  --random-output-len 256 --random-range-ratio 1 --num-prompts C --max-concurrency C --seed 1`.

## 1. Was the optimization actually active on gfx1100? (yes — proven)

Triton compile-option capture on real launches (`evidence/kernel/capture_*.json`):

| shape | Main | PR+patch |
|---|---|---|
| b16 h16/kv8 d128 bf16 (qualifies) | num_warps=4 + waves_per_eu=1/matrix_instr_nonkdim=16/kpack=2 | **num_warps=2, hints removed** |
| b1 h16/kv8 (batch×head_tiles=8 boundary) | hints + 4 warps | **2 warps, hints removed** |
| b1/b3 h16/kv2 (tiny grid <8) | hints + 4 | hints + 4 (unchanged) |
| b4 h16/kv8 **d256** | hints + 4 | hints + 4 (unchanged) |

A one-off instrumented server (separate process; measurements ran uninstrumented)
recorded **672/672 consecutive stage-1 launches with num_warps=2 and no hints**
during live serving on the PR arm.

## 2. Kernel correctness

- 17-case sweep (d64/128/256 × bf16/fp16 × GQA 32/8, 16/8, 16/2, 16/4, MHA 8/8,
  7/1 × batch 1–64 × ragged contexts to 8192 × fp8-e4m3 KV): all finite, both arms
  within normal bf16/fp16 rounding of an fp32 reference (max abs err 1.2e-3 / 1.3e-4).
- **17/17 bitwise identical between arms** (exact fp32 capture) — the launch
  change does not reorder accumulation on gfx1100, matching the PR's gfx1151 claim.
- Registered suites at the tested revisions: PR's `test_gfx115_decode_launch` 6/6
  PASS (file absent on Main — PR-added); MLA geometry/forced-splits identical on
  both arms; `test_triton_attention_kernels`: 13 PASS + 2 gfx950-only SKIPs +
  1 OOM (`test_extend_attention_sliding_window`, needs 8.28 GiB free — co-tenant
  constraint; fails identically on both arms). Details: `evidence/kernel/kernel_correctness.md`.

## 3. Serving performance (Model A = Qwen3-0.6B, 16 Q / 8 KV heads, head_tiles=8)

Median of 2 runs/arm after warmup; ABBA. `spd` = PR/Main throughput; `ms/step`
speedup = Main/PR from `Decode batch` lines with `#queue-req: 0` (author's method).

| load | throughput main→pr | spd | ms/step main→pr | spd | median ITL spd |
|---|---|---|---|---|---|
| c=1 | 132.4→130.3 tok/s | **0.984** | 7.41→7.55 | **0.982** | 0.980 |
| c=4 | 455.9→455.2 | 0.998 | 8.55→8.54 | 1.002 | 1.001 |
| c=8 | 805→843 | 1.047 | 9.75→9.25 | 1.054 | 1.052 |
| c=16 | 1200→1326 | **1.105** | 10.04→9.36 | 1.072 | 1.114 |
| c=32 | 1635→1907 | **1.166** | 9.96→9.56 | 1.043 | 1.197 |
| c=64 | 1712→2256 | **1.318** | 9.93→9.43 | 1.053 | 1.326 |
| 8k in, c=8 | 404→433 | 1.072 | 19.2→17.9 | 1.072 | 1.070 |
| 4k in, c=8 | 556→582 | 1.047 | 14.0→13.2 | 1.065 | 1.067 |
| mixed (rr .25) c=16 | 934→952 | 1.019 | 9.44→9.62 | 0.981 | 1.018 |
| mixed c=32 | 1107→1124 | 1.015 | 9.48→9.58 | 0.990 | 1.031 |

Run-to-run spread inside cells: 0.1–0.6% (throughput), 0.2–2% (ms/step) — far
below the observed deltas at c≥8.

## 4. Serving performance (Model B = Qwen2.5-3B-Instruct, 16 Q / **2 KV** heads → head_tiles=2; gate needs batch≥4)

| load | throughput spd | ms/step spd | median ITL spd |
|---|---|---|---|
| c=16 | 0.993 | 0.999 | 0.993 |
| c=32 | **1.014** | 1.013 | 1.020 |
| c=64 | **1.021** | 1.014 | 1.035 |
| 8k in, c=8 | 1.018 | 1.018 | 1.019 |
| mixed c=16 | 0.988 | 0.995 | 0.986 |

B's step time is dominated by non-attention memory traffic (2 KV heads → tiny
attention fraction); gains are small but reproducible at c≥32. Direction matches
the author's gfx1151 result for this model (1.08–1.11x there; smaller here on a
96-CU dGPU with 864 GB/s).

## 5. GSM8K (sgl-eval 0.1.3, greedy, identical settings both arms)

| run | n | max_tok | Main | PR | Δ (PR−Main) |
|---|---|---|---|---|---|
| A diagnostic | 200 | 1024 | 54.50% | 55.00% | +0.50 pp |
| A full | 1319 | 1024 | 56.33% | 55.57% | −0.76 pp |
| A full (second pair) | 1319 | 2048 | 68.84% | 69.14% | +0.31 pp |
| B diagnostic | 200 | 2048 | 85.50% | 85.00% | −0.50 pp |
| B full | 1319 | 2048 | 86.35% | 86.58% | +0.23 pp |

Binomial σ at these p, n=1319 ≈ 1.3–1.4 pp: every delta ≲0.6σ. Model A has two
independent full pairs at different max_tokens (both arms symmetric within each
pair); the deltas straddle zero (−0.76 / +0.31 pp). Kernel-level bitwise
equality does not imply identical generations (batching/GEMM tiling vary
run-to-run); the paired design bounds natural variability.

## 6. Findings & recommendation

1. **gfx1100 does benefit**, monotonically with concurrency for the 16/8 model:
   +5% → +32% output throughput from c=8 to c=64; decode ms/step (pure decode
   steps) +4–7%; median ITL up to +33% at c=64. Long-context (4k/8k) gains 5–7%.
2. **A real but small regression exists at c=1** for a geometry that *qualifies*
   at batch 1 (16 Q/8 KV → head_tiles=8, so batch=1 hits the boundary):
   −1.6–2.0% throughput/step latency, consistent across 4 measured runs (ABBA×2)
   and reproduced under two memory configurations. The `batch*head_tiles < 8`
   guard does not protect a 16/8 model at batch 1..? — specifically, any model
   with head_tiles ≥ 8 qualifies even at batch 1. If gating to RDNA3 is widened,
   consider whether `batch * head_tiles < 8` should become a stricter
   memory-boundness guard (e.g. also require batch ≥ 2, or scale the threshold
   with CU count) — at minimum this trade-off should be stated.
3. **Excluded configurations verified intact**: tiny grids (16/2 model at low
   batch — B c=16 measured 1.00x), head_dim 256, fp8-KV, MLA, non-gfx1100 arch
   predicates: all keep the original launch config (captures + 22 gate checks).
4. **No correctness or accuracy regression** detectable at kernel level (bitwise)
   or served level (GSM8K within noise both models).
5. **Not validated here**: MLA end-to-end serving, head_dim-256 models end-to-end,
   Qwen3-8B (VRAM co-tenant), Phi-4-mini / 14B / gpt-oss-20b (network/VRAM),
   deterministic-serving mode. See LIMITATIONS.md.

**Bottom line**: on the evidence collected, extending the gate to gfx1100 (RDNA3.0)
is **safe for correctness** and **net-positive for throughput at c≥8** on the
tested geometry, with a small batch-1 cost for high-head-tile models; a reviewer
may want to weigh #2 before widening unconditionally.

## 7. Campaign gate status

PASS (all mandatory tests completed; evidence internally consistent). Technical
acceptance is a separate judgement: see Finding 2. Full gate table:
`results/regression_gates.csv`; audit: `evidence/EVIDENCE_AUDIT.md`.
