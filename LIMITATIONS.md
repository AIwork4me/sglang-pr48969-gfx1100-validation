# LIMITATIONS

Read together with FINAL_VALIDATION_REPORT.md. Items here bound the strength of
the campaign's conclusions; none invalidates the A/B comparison itself.

## L1. Co-tenant GPU memory (environmental)
A host-level process outside this container holds 33.26 GB (decimal GB;
≈31.0 GiB) of the W7900's 51.52 GB / 48 GiB VRAM for the entire campaign (0%
compute utilization, idle power). Consequences:
- `--mem-fraction-static 0.75` (the mandated setting) **is** used on both arms,
  but SGLang's KV-pool budget formula (`free_after_weights − free_before ×
  (1−frac)`) shrinks the pool when little memory is free. An explicit
  `--max-total-tokens` (A: 100000, B: 260000 — sufficient for 64 × 1280-token
  requests plus headroom) was added on **both arms identically** to keep the
  pool workload-adequate. (The GSM8K A_diag/A_full pairs predate this pin and
  ran at memfrac 0.30 with an auto pool — arm-symmetric within each pair; see
  evidence/accuracy/EXECUTION_MANIFEST.md.)
- Model C (Qwen3-8B, 16.4 GB bf16 weights) does not fit alongside the co-tenant:
  BLOCKED for serving benchmarks. (Downloaded, manifest recorded; kernel-level
  geometry coverage for 32/8 heads is provided by the synthetic kernel sweep.)
- The registered test `test_extend_attention_sliding_window` needs one 8.28 GiB
  allocation and OOMs on both arms identically.
- Absolute throughputs are lower than a memory-unconstrained W7900 would show
  (smaller KV pool, fewer admitted requests at very high concurrency in the
  c=64 mixed-length case).
- **Scope of the A/B control**: both arms saw the same memory, same fraction,
  same pool size, same scheduler settings, so the comparison is *controlled
  symmetrically*. However, symmetric control does not prove the *magnitude* of
  the reported ratios is invariant to the constraint: a memory-constrained
  scheduler can behave differently (admission, retraction) than an
  unconstrained one, and the effect of the constraint on the observed speedup
  magnitude has not been excluded. The single data point bearing on this —
  the c=16 pilot at memfrac 0.30 reproducing the 0.75+100k formal medians to 4
  significant figures — covers one cell only.

## L2. Environment deltas from the official gfx1151 docker recipe
Replicated on-host (no nested containers available) with three documented,
arm-symmetric workarounds (details in ENVIRONMENT.md). Classification:

| change | class | applies to | cross-machine comparability |
|---|---|---|---|
| pyproject swap + flat ROCm deps (`python/pyproject_other.toml`, `configs/rocm_flat_deps.txt`) | official Dockerfile step | both arms identically | matches upstream recipe; absolute numbers comparable to that recipe generation |
| sgl-kernel built from each arm's tree with `patches/sgl-kernel-gfx1100.sh` (gfx1151 wave32 patch adapted: arch-gate lift + WARP_SIZE=32 pin) | local build workaround, official-patch-derived | both arms identically | gfx1100 AOT build is not an officially shipped target; absolute numbers are specific to this build |
| `aiter_compat_shim.py` (5 quark-mxfp4 symbols; raise-on-use; path unused here) | local import shim | both arms identically | replaces upstream's full-aiter install; unused paths only — no measured workload touches it |
| `norm_compat.py` (out-style Triton RMSNorm overriding two `vllm._custom_ops` names) | local **functional** shim — this code RUNS in every serving step | both arms identically (bit-identical module) | absolute latencies are NOT bit-comparable to a full-official-recipe environment; the A/B ratios remain internally valid because both arms execute the identical norm implementation, but the *magnitude* of speedups could in principle differ under the official norm provider |

Honest bound: "arm-symmetric" guarantees internal A/B fairness, not that the
ratio is independent of the workaround. The norm shim is the only workaround
on the hot path; swapping in the official aiter/sgl-kernel norm provider could
shift absolute step times and, in principle, the measured ratio. Results
should be read as valid for *this* environment; cross-environment transfer of
magnitudes is not claimed.

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
- max_tokens per run (from metrics.json, enforced by Audit V2): A pairs 1024
  (A_diag, A_full) and 2048 (A_full_2048); B pairs 2048. Truncation is
  arm-symmetric within every pair (A ~51% at 1024, ~25% at 2048, B ≤0.3%);
  scores are comparable within a pair, never across models or across
  max_tokens settings.
- Statistical treatment (audit round 2026-11): paired exact McNemar on
  question-id-joined outcomes gives p ≥ 0.50 for all five pairs — no detectable
  systematic change; this is not a formal equivalence proof. See
  evidence/STATISTICAL_RECONCILIATION.md §1.

## L5. Coverage not achieved (kernel/unit-level vs end-to-end serving)
Kernel/unit-level coverage achieved: 17-case synthetic sweep (d64/128/256 ×
bf16/fp16 × GQA ratios to MHA × batch 1–64 × ragged 8k × fp8-KV, bitwise equal
across arms), launch-capture proof on excluded shapes, MLA gate-function and
geometry tests, PR's own `test_gfx115_decode_launch` (6/6, PR arm only),
arch-predicate unit checks (simulated, not physical GPUs).

End-to-end serving coverage NOT achieved (all listed honestly):
- MLA serving: NOT_RUN (no MLA model downloadable in the window; covered at
  kernel/unit level: hints provably retained).
- head_dim-256 models serving: NOT_RUN (kernel-level only).
- fp8-KV serving: NOT_RUN (kernel-level numerics only).
- Qwen3-8B serving: BLOCKED (co-tenant VRAM; see L1).
- Phi-4-mini: BLOCKED (egress proxy 503/525 for this repo).
- Qwen3-14B / gpt-oss-20b: NOT_RUN (VRAM / unverified MXFP4 path on gfx1100).
- Sliding-window attention: covered only by a registered test that OOMs
  identically on both arms under the co-tenant constraint — i.e. **not
  actually validated**.
- Deterministic-serving mode: **BLOCKED — startup failure confirmed on both
  arms** (follow-up round 2026-11-08). With the tested SGLang, PyTorch, Triton
  and ROCm stack on this gfx1100 host, `--enable-deterministic-inference`
  fails during startup because the compiled batch-invariant persistent matmul
  kernel requires 99,328 bytes of shared memory against a reported 65,536-byte
  limit (`followup/evidence_determinism/`, verdict:
  `followup/results/determinism_verdict.json`). This statement is scoped to
  the tested stack: it does not claim deterministic inference is impossible on
  gfx1100 with other stacks, does not implicate PR #48969 (identical failure
  on both arms; the failing path `batch_invariant_ops.py` is outside the PR's
  decode-attention change), and does not imply AMD GPUs lack deterministic
  computing in general. Kernel-level batch-invariance is instead covered by
  the 17-case bitwise sweep and the PR's own tests.

These bounds mean the campaign validates the launch change for dense bf16/fp16
GQA decode serving on two model geometries, not the whole serving feature
matrix of the affected kernel.

## L6. Instrumentation
The serving-context gate proof used a Triton-JIT spy wrapper in a dedicated
one-off server process. No instrumentation ran during any measured benchmark
(the regular launcher was used; verified by the saved server command lines in
evidence/performance/*/server_*.log).

## L7. Reproducibility of runs
Run-to-run agreement inside an ABBA cycle (recomputed in audit round 2026-11
from all 15 formal cells): throughput spreads 0.0–3.0% and decode ms/step
medians 0.03–3.2% (per `performance_raw.csv`; each cell has 2 runs per arm).
Most cells are ≤0.7% (throughput); the largest are A_long_4k_c8 PR 3.0%,
A_c32 PR ms/step 3.2%, B_long_8k_c8 main 1.2%, A_c16 main 1.0%, A_c1 main
0.8%. The earlier blanket "0.1–0.6% / 0.2–2%" wording understated the tails
and has been corrected. Consequences: the c≥8 throughput speedups (+4.7% …
+31.8%) exceed the spreads, but single-cell deltas of a few percent (e.g. the
mixed-length cells, B c=16/c=32) are of the same order as the spread and
should not be over-interpreted. A c=16 re-run under a different memory
configuration (0.30 auto pool vs 0.75+100k explicit) reproduced medians to 4
significant figures (pilot `_pilot4x_A_c16`, formal `A_c16`); note this
reproduction is at c=16, not at c=1.
