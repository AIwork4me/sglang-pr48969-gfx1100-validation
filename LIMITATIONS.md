# LIMITATIONS

Read together with FINAL_VALIDATION_REPORT.md. Items here bound the strength of
the campaign's conclusions; none invalidates the A/B comparison itself.

## L1. Co-tenant GPU memory (environmental)
A host-level process outside this container holds 33.26 GB of 51.5 GB VRAM for
the entire campaign (0% compute utilization, idle power). Consequences:
- `--mem-fraction-static 0.75` (the mandated setting) **is** used on both arms,
  but SGLang's KV-pool budget formula (`free_after_weights − free_before ×
  (1−frac)`) shrinks the pool when little memory is free. An explicit
  `--max-total-tokens` (A: 100000, B: 260000 — sufficient for 64 × 1280-token
  requests plus headroom) was added on **both arms identically** to keep the
  pool workload-adequate.
- Model C (Qwen3-8B, 16.4 GB bf16 weights) does not fit alongside the co-tenant:
  BLOCKED for serving benchmarks. (Downloaded, manifest recorded; kernel-level
  geometry coverage for 32/8 heads is provided by the synthetic kernel sweep.)
- The registered test `test_extend_attention_sliding_window` needs one 8.28 GiB
  allocation and OOMs on both arms identically.
- Absolute throughputs are lower than a memory-unconstrained W7900 would show
  (smaller KV pool, fewer admitted requests at very high concurrency in the
  c=64 mixed-length case). All A/B ratios are unaffected: both arms see the
  same memory, same fraction, same pool size, same scheduler settings.

## L2. Environment deltas from the official gfx1151 docker recipe
Replicated on-host (no nested containers available) with three documented,
arm-symmetric workarounds (details in ENVIRONMENT.md):
- aiter import shim (5 quark-mxfp4 symbols; raise-on-use; path unused here);
- out-style Triton RMSNorm ops overriding the two vllm._custom_ops names
  (host vllm API too old; AOT ROCm sgl_kernel has no norm ops). Both arms use
  the identical implementation, so A/B ratios are unaffected, but absolute
  numbers are not bit-comparable to a full-official-recipe environment;
- sgl_kernel built from tree with the official gfx1151 wave32 patch adapted to
  gfx1100 (arch-gate lift + WARP_SIZE=32 pin).

## L3. Software-generation gap vs the PR author
Author: ROCm 7.13 / torch 2.10 / Triton 3.6 on gfx1151 (8060S iGPU, unified memory).
This campaign: ROCm 7.2.1 host runtime / torch 2.9.1 / Triton 3.6.0+rocm7.2 on a
discrete gfx1100 (96 CU, 864 GB/s). Different hardware class and ROCm generation:
magnitude of speedups is not expected to transfer, and does not (see report).
The official AMD-supported stable combination for this sglang generation on
RDNA3.5 is "ROCm 7.2.x + torch 2.9.1" (docker/rocm-gfx1151.Dockerfile), which we
match; no newer ROCm was installable in this lab.

## L4. GSM8K harness specifics
- sgl-eval 0.1.3, gsm8k single-shot chat, thinking=false (tool default),
  temperature 0, top_p 0.95, seed 0, 64 threads.
- The dataset was sourced from openai/gsm8k on HuggingFace and transformed with
  sgl-eval's own vendored NeMo-Skills prepare.py logic because
  raw.githubusercontent.com is unreachable through the lab egress proxy. The
  content is the same 1319-question test split; sha256 recorded.
- Model A runs used max_tokens 1024 (both arms; ~51% truncation — the 0.6B
  model rambles); models B used 2048. Truncation rate is symmetric across arms;
  scores are comparable within a model, not across models.
- With greedy decoding and ~0.56 accuracy, 1319-question binomial σ ≈ 1.4 pp:
  single-run deltas within ±1.4 pp are not statistically meaningful.

## L5. Coverage not achieved
- No MLA model end-to-end serve (DeepSeek-V2-Lite unavailable for download in
  time; MLA covered at kernel/unit level: hints provably retained).
- head_dim 256 served model: covered at kernel level (hints retained); no
  end-to-end model with d=256 was run.
- fp8-KV served: covered at kernel level (hints retained) + numerics case.
- gpt-oss-20b / Qwen3-14B / Phi-4-mini: not run (memory/network/time; see
  FINAL_VALIDATION_REPORT "not validated" section).
- Deterministic-serving mode not enabled (RDNA startup limitation noted in the
  mission); kernel-level batch-invariance is covered by the 17-case bitwise
  sweep and PR's own tests instead.

## L6. Instrumentation
The serving-context gate proof used a Triton-JIT spy wrapper in a dedicated
one-off server process. No instrumentation ran during any measured benchmark
(the regular launcher was used; verified by the saved server command lines in
evidence/performance/*/server_*.log).

## L7. Reproducibility of runs
Run-to-run agreement inside an ABBA cycle is ≈0.1–0.6% for throughput and
≈0.2–2% for decode ms/step medians (see performance_raw.csv; each cell has 2
runs per arm). A c=16 re-run under a different memory configuration (0.30 auto
pool vs 0.75+100k explicit) reproduced medians to 4 significant figures.
