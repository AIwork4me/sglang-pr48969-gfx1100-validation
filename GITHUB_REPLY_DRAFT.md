# GITHUB_REPLY_DRAFT — **DO NOT POST until Owner review** (AIwork4me)

> Independently measured on gfx1100 as requested. Evidence, logs, scripts, and
> a fail-closed independent audit (55 checks, all recomputed from raw
> artifacts): https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation

Thanks @twoask — independent numbers from a Radeon PRO W7900 (gfx1100, RDNA3.0,
96 CU, discrete 48 GiB).

## Setup
- **Arms**: main `0afb736d` vs PR `3fdf6f7` (byte-verified against GitHub's
  tree API: 12,039 / 12,040 files).
- **Gate**: extended `_is_gfx115` locally on the PR arm only so exactly
  `gfx1100` is additionally accepted
  ([6-line patch](patches/pr48969-gfx1100-validation.patch)); gfx115x behavior
  untouched, main arm pristine (tree deltas archived per arm).
- **Stack**: ROCm 7.2.1, torch 2.9.1+git rocm7.21, Triton 3.6.0+rocm7.2.0 (AMD
  stable wheel), sgl-kernel built from each arm's tree for gfx1100 with your
  gfx1151 wave32 patch adapted. Environment replicates
  `docker/rocm-gfx1151.Dockerfile` on-host (no nested containers in this lab).
  Two arm-symmetric shims were required (old host aiter import surface; an
  out-style Triton RMSNorm replacing an outdated vllm fallback API — the norm
  shim is on the hot path and identical on both arms, so the A/B is internally
  fair but absolute numbers are environment-specific; details in
  ENVIRONMENT.md/LIMITATIONS.md).
- **Serving**: `SGLANG_DISABLE_LEAN_ATTENTION=1`, `--attention-backend triton`,
  `--context-length 10240`, `--mem-fraction-static 0.75`, your exact
  `benchmark.serving` command, ABBA (main→PR→PR→main), warmup-separated,
  2 measured runs per arm per cell. ms/step extracted with your method
  (`Decode batch`, `#queue-req: 0`, first line of each segment dropped, median).
  Disclosure: a co-tenant process held 33.26 GB of the card's 48 GiB for the
  whole window, so `--max-total-tokens` was pinned identically on both arms;
  the constraint was controlled symmetrically, but its effect on the *magnitude*
  of the ratios is not fully excluded (LIMITATIONS.md L1).

## Gate activation proof
Qualifying GQA shapes on the PR arm compile with **num_warps=2 and no CDNA
hints**; tiny grids (batch×head_tiles<8), head_dim 256 and fp8-KV keep the old
config (byte-identical to main); main is hints+4warps everywhere. A one-off
instrumented server recorded 672/672 live stage-1 launches at num_warps=2
(measured runs uninstrumented — server command lines archived per leg).

## Results — Qwen3-0.6B (16 Q / 8 KV, d128)

| c | ms/step main r1,r2 → PR r1,r2 | step ratio | e2e output tok/s (PR/Main) | client median ITL |
|---|---|---|---|---|
| 1 | 7.42, 7.40 → 7.55, 7.55 | **0.98** | **0.984** | 0.980 |
| 4 | 8.56, 8.54 → 8.52, 8.56 | 1.00 | 0.998 | 1.001 |
| 8 | 9.78, 9.71 → 9.23, 9.26 | 1.05 | 1.047 | 1.052 |
| 16 | 10.14, 9.93 → 9.38, 9.34 | 1.07 | 1.105 | 1.114 |
| 32 | 9.93, 9.99 → 9.40, 9.71 | 1.04 | 1.166 | 1.197 |
| 64 | 9.92, 9.94 → 9.33, 9.53 | 1.05 | **1.318** | 1.326 |
| 8k in, c=8 | 19.21, 19.18 → 17.92, 17.91 | 1.07 | 1.072 | 1.070 |

4k-in c=8: 1.047 e2e. Mixed lengths (2k in, rr 0.25): c16 1.019×, c32 1.015×
e2e (ms/step ≈0.98–0.99; ITL +1.8/+3.1%).

To be precise about attribution: at c=64 the **end-to-end** gain (1.318×) is
much larger than the pure decode-step gain (1.053×); both arms did identical
work (64/64 requests, same token counts, same running-req pattern), and the
client-side ITL gain (1.326×) matches the e2e gain — so most of the
high-concurrency benefit comes from reduced non-decode-step overheads under
load, not from the kernel step time alone; the mechanism of that extra gain is
not isolated by this evidence (details:
evidence/STATISTICAL_RECONCILIATION.md §4).

Qwen2.5-3B-Instruct (16/**2** — head_tiles=2, tiny-grid guard keeps batch<4 on
the old config): c16 0.993×, c32 1.014×, c64 1.021× e2e; 8k-in c8 1.018×;
mixed c16 0.988×. Same direction as your gfx1151 numbers for this model but
smaller, as expected on a 96-CU dGPU where attention is a smaller fraction of
the step; these ~1–2% magnitudes are close to run-to-run spread in some cells,
so read them as small-and-directional rather than precise.

## Correctness / accuracy
- 17-case kernel sweep (d64/128/256, bf16/fp16, GQA 32/8→7/1, batch 1–64,
  ragged to 8k, fp8-e4m3 KV): all finite, both arms within normal
  bf16/fp16 rounding of an fp32 reference, and **bitwise identical between
  arms (17/17)** — the launch change doesn't reorder accumulation on gfx1100.
- GSM8K (sgl-eval 0.1.3, greedy, arm-symmetric settings per pair):
  Qwen3-0.6B 1319q: 56.33→55.57% @1024 max_tok; 68.84→69.14% @2048.
  Qwen2.5-3B 1319q: 86.35→86.58% @2048. Paired per-question analysis
  (exact McNemar on id-joined outcomes): all five pairs p ≥ 0.50 — no
  detectable systematic change. We are not claiming formal equivalence, only
  that no change is detectable at n=1319.
- Your test file passes 6/6 on the PR arm (absent on main, as expected); MLA
  geometry/forced-splits suites identical on both arms; one
  `test_triton_attention_kernels` case OOMs identically on both arms only
  because of the co-tenant memory (needs a single 8.28 GiB alloc) — i.e. that
  case is not actually validated here.

## Caveats
- **Batch-1 on 16/8-geometry models**: head_tiles=8 means batch=1 already
  clears your `batch*head_tiles >= 8` guard, and that cell measures −1.4…−1.9%
  e2e / +1.5–1.8% ms/step. We re-measured it in a follow-up round: it is
  sign-consistent in 12/12 legs, fully separated at n=4/arm at 0.75+100k
  (median 0.981×), and **reproduced under a second memory configuration**
  (memfrac 0.30/auto pool: 0.986×); c=2 measures neutral (1.003×). If RDNA3 is
  added, a stricter low-batch guard (e.g. batch ≥ 2, or a threshold scaled by
  CU count) might be worth considering; on this card the crossover is between
  c=4 and c=8 for this geometry.
- `--enable-deterministic-inference` cannot start on gfx1100 with this stack
  (batch-invariant persistent matmul needs 99,328 B shared memory vs the
  64 KiB hardware limit; identical on both arms) — flagging in case RDNA3
  support for that mode ever matters for this gate.
- Not covered end-to-end: MLA serving, head_dim-256 models, fp8-KV serving,
  sliding-window (OOM'd under the co-tenant), Qwen3-8B (VRAM co-tenant),
  Phi-4-mini / 14B / gpt-oss-20b (network/VRAM/mxfp4), Lean (explicitly
  disabled per your protocol).
- This is one gfx1100 SKU (W7900, ROCm 7.2.1, torch 2.9.1) with local
  environment workarounds; we do not generalize it to every RDNA3 SKU or
  software combination.

## Bottom line — what this evidence supports
On gfx1100 the change is **correctness-neutral at the kernel level (17/17
bitwise)** and **accuracy-neutral within paired-test resolution on GSM8K**, and
it is **net-positive from c≈8 up** on the 16/8 geometry (+5% e2e at c=8 rising
to +32% at c=64, of which the decode step itself accounts for ~+5%),
with a small, leg-consistent batch-1 cost for models whose head_tiles ≥ 8.

So: the evidence does support **considering** a gfx1100 gate extension — it is
correctness-clean and throughput-positive from low-mid concurrency upward on
this card — with one open design question: whether the low-batch guard
(`batch * head_tiles < 8`) should be tightened (e.g. `batch >= 2` or a
CU-count-scaled threshold) so high-head-tile models don't pay a ~1.5–2%
single-request penalty (now measured at two memory configurations). If it
helps, we can run further geometries (e.g. Phi-4-mini 24/8, an 8B once the
card has its full memory back).

*(Draft prepared for owner review — not posted to the PR. All numbers above are
recomputed from the archived raw artifacts by the repository's independent
audit, `evidence/EVIDENCE_AUDIT_V2.md.)*
