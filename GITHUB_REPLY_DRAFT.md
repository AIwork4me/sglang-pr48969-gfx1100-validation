# GITHUB_REPLY_DRAFT — **DO NOT POST until Owner review** (AIwork4me)

> Independently measured on gfx1100 as requested. Evidence, logs, and scripts:
> https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation

Thanks @twoask — here are independent numbers from a Radeon PRO W7900
(gfx1100, RDNA3.0, 96 CU, discrete 48 GB).

## Setup
- **Arms**: main `0afb736d` vs PR `3fdf6f7` (byte-verified against GitHub's tree API).
- **Gate**: extended `_is_gfx115` locally on the PR arm only so exactly `gfx1100`
  is additionally accepted ([6-line patch](patches/pr48969-gfx1100-validation.patch));
  gfx115x behavior untouched, no other change, main arm pristine.
- **Stack**: ROCm 7.2.1, torch 2.9.1+git rocm7.21, Triton 3.6.0+rocm7.2.0 (AMD
  stable wheel), sgl-kernel built from each arm's tree for gfx1100 with your
  gfx1151 wave32 patch adapted. Environment replicated from
  `docker/rocm-gfx1151.Dockerfile` (no nested containers available); two
  arm-symmetric shims were needed (old host aiter/vllm norm APIs) — details in
  ENVIRONMENT.md/LIMITATIONS.md.
- **Serving**: `SGLANG_DISABLE_LEAN_ATTENTION=1`, `--attention-backend triton`,
  `--context-length 10240`, `--mem-fraction-static 0.75`, your exact
  `benchmark.serving` command, ABBA (main→PR→PR→main), warmup-separated,
  2 measured runs per arm per cell. ms/step extracted with your method
  (`Decode batch`, `#queue-req: 0`, first line of each segment dropped, median).
  Note: a co-tenant process held 33.3/51.5 GB VRAM all day, so `--max-total-tokens`
  was pinned identically on both arms to keep the KV pool workload-adequate.

## Gate activation proof
Qualifying GQA shapes on the PR arm compile with **num_warps=2 and no CDNA
hints**; tiny grids (batch×head_tiles<8), head_dim 256 and fp8-KV keep the old
config; main is hints+4warps everywhere. A one-off instrumented server recorded
672/672 live stage-1 launches at num_warps=2 (measured runs uninstrumented).

## Steady-state ms/step (your methodology) and throughput — Qwen3-0.6B (16/8, 128)

| c | ms/step main r1,r2 → PR r1,r2 | ratio | output tok/s (PR/Main) |
|---|---|---|---|
| 1 | 7.42, 7.40 → 7.55, 7.55 | **0.98** | 0.984 |
| 4 | 8.56, 8.54 → 8.52, 8.56 | 1.00 | 0.998 |
| 8 | 9.78, 9.71 → 9.23, 9.26 | 1.06 | 1.047 |
| 16 | 10.14, 9.93 → 9.38, 9.34 | 1.07 | 1.105 |
| 32 | 9.93, 9.99 → 9.40, 9.71 | 1.04 | 1.166 |
| 64 | 9.92, 9.94 → 9.33, 9.53 | 1.05 | **1.318** |
| 8k in, c=8 | 19.21, 19.18 → 17.92, 17.91 | 1.07 | 1.072 |

Mixed lengths (2k in, rr 0.25): c16 1.019×, c32 1.015× output tok/s (ms/step
median ~1.0; ITL +1.8/+3.1%).

Qwen2.5-3B-Instruct (16/**2**, 128 — head_tiles=2, so the tiny-grid guard keeps
batch<4 on the old config): c16 0.993×, c32 1.014×, c64 1.021×; 8k-in c8
1.018×; mixed c16 0.988×. Same direction as your gfx1151 numbers for this
model, but smaller — as expected on a 96-CU dGPU where attention is a smaller
fraction of the step.

## Correctness / accuracy
- 17-case kernel sweep (d64/128/256, bf16/fp16, GQA 32/8→7/1, batch 1–64,
  ragged to 8k, fp8-e4m3 KV): all finite, both arms ≈1 ULP of an fp32 reference,
  and **bitwise identical between arms (17/17)** — the launch change doesn't
  reorder accumulation on gfx1100 either.
- GSM8K (sgl-eval 0.1.3, greedy, identical settings): Qwen3-0.6B 1319q:
  56.33%→55.57% @1024 max_tok, 68.84%→69.14% @2048 (σ≈1.3pp; deltas straddle
  zero). Qwen2.5-3B: 86.35%→86.58%. No systematic change.
- Your test file passes 6/6 on the PR arm (absent on main, as expected); MLA
  geometry/forced-splits suites identical on both arms; one
  `test_triton_attention_kernels` case OOMs identically on both arms only
  because of the co-tenant memory (needs a single 8.28 GiB alloc).

## Caveats
- **Batch-1 on 16/8 models**: head_tiles=8 means batch=1 already clears your
  `batch*head_tiles >= 8` guard, and on gfx1100 that cell measures a consistent
  −1.6…−2% (throughput and ms/step, 4 runs, reproduced under two memory
  configs). If RDNA3 is added, a stricter low-batch guard (e.g. batch ≥ 2, or a
  threshold scaled by CU count) might be worth considering — on gfx1100 the
  crossover is between c=4 and c=8 for this geometry.
- Not covered end-to-end: MLA serving, head_dim-256 models, Qwen3-8B (VRAM
  co-tenant), Phi-4-mini / 14B / gpt-oss-20b (network/VRAM), Lean (explicitly
  disabled per your protocol).

## Bottom line
On gfx1100 the change is **correctness-neutral (bitwise at kernel level, GSM8K
within noise)** and **net-positive from c≈8 up** on the 16/8 geometry
(+5% → +32% output tok/s by c=64; +5–7% at 4k/8k context), with a small,
reproducible batch-1 cost for models whose head_tiles ≥ 8. Based on this
sample, widening to RDNA3.0 looks safe with that one caveat.

Happy to run further geometries (e.g. Phi-4-mini 24/8, an 8B once the card has
its full memory back) if useful.
