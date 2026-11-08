# STATISTICAL RECONCILIATION — audit round 2026-11

All numbers in this file are recomputed from the raw artifacts (per-question
prediction files, metrics.json, bench JSONs, server logs) by
`scripts/verify_evidence_v2.py`, `scripts/recompute_accuracy.py`, and
`scripts/recompute_performance.py`. Nothing here relies on the summary CSVs.

## 1. GSM8K — paired analysis (replaces the earlier binomial-σ-only argument)

The previous wording ("deltas within ~0.6σ of binomial noise") treated the two
arms as independent samples. The paired design permits a stronger, more
appropriate test. Question IDs align 1:1 across arms within every run pair
(joined on the unique `gsm8k-N` id; records are stored in completion order, so
the join is by id, not sequence).

Exact two-sided McNemar test (binomial on the discordant pairs):

| pair | n | Main correct | PR correct | Main-only correct (b) | PR-only correct (c) | exact p |
|---|---|---|---|---|---|---|
| A diag (1024) | 200 | 109 | 110 | 17 | 18 | 1.000 |
| A full (1024) | 1319 | 743 | 733 | 96 | 86 | 0.505 |
| A full 2048 | 1319 | 908 | 912 | 85 | 89 | 0.820 |
| B diag (2048) | 200 | 171 | 170 | 4 | 3 | 1.000 |
| B full (2048) | 1319 | 1139 | 1142 | 14 | 17 | 0.720 |

Conclusions supported by this analysis:

- No pair shows a statistically detectable accuracy difference (all exact
  paired p ≥ 0.50). The correct claim is: **"no systematic accuracy change is
  detectable at the paired-test level (all exact McNemar p ≥ 0.50)"** — which
  is *not* a proof of formal equivalence; the tests are under-powered for
  sub-0.5 pp effects at n=1319.
- The B full pair is highly concordant (only 31/1319 discordant) as expected
  for a 3B model with low truncation; the A pairs have 171–182 discordant
  questions, reflecting the 0.6B model's noisier generation (and ~51% or ~25%
  truncation). Truncation rates are arm-symmetric within every pair.
- The two A full pairs differ from each other in *both* max_tokens (1024 vs
  2048) and server memory configuration (memfrac 0.30/auto vs 0.75/pinned
  100000 — see `evidence/accuracy/EXECUTION_MANIFEST.md`); each pair is a
  self-consistent A/B experiment and the two must not be pooled.

## 2. Performance — corrected spread statement and repeat structure

Every cell has exactly 2 measured runs per arm (ABBA: main→pr→pr→main),
warmup-separated; warmup artifacts are excluded from every statistic here.

Run-to-run spreads inside cells, recomputed over all 15 formal cells
(earlier docs understated the tails; corrected in FINAL_VALIDATION_REPORT §3
and LIMITATIONS.md L7):

- throughput: 0.0%–3.0% (largest: A_long_4k_c8 PR 3.0%, B_long_8k_c8 main 1.2%,
  A_c16 main 1.0%, A_c1 main 0.8%, B_mixed_c16 PR 0.9%; most cells ≤0.7%)
- decode ms/step medians: 0.03%–3.2% (largest: A_c32 PR 3.2%, A_c16 main 2.1%,
  A_c64 PR 2.1%)

Implications stated honestly:

- The c≥8 throughput speedups on model A (1.047→1.318) exceed the within-cell
  spreads by a wide margin and were reproduced in both ABBA runs of each cell.
- Effects of ~1–2% (B c=16 0.993, B c=32 1.014, mixed cells ~1.02) are of the
  same order as the spreads in some cells; they should be read as small and
  directionally consistent, not as precisely measured magnitudes. No
  confidence intervals are reported because n=2 per arm does not support a
  meaningful interval; none were fabricated.

## 3. Batch-1 regression — corrected claim

What the evidence shows (A_c1, the only c=1 cell, single memory configuration
memfrac 0.75 + max-total-tokens 100000):

| leg | main r1 | main r2 | pr r1 | pr r2 |
|---|---|---|---|---|
| output tok/s | 131.83 | 132.94 | 130.26 | 130.32 |
| decode ms/step | 7.42 | 7.40 | 7.55 | 7.55 |

- Both PR legs are below both main legs (consistent sign across all 4 legs of
  the ABBA cycle): throughput −1.6%, ms/step +1.8%, median ITL −2.0%.
- The main-arm run-to-run spread at c=1 is 0.8% — about half the effect size;
  the PR-arm spread is 0.05%. The consistency across legs supports the
  regression being real *in this environment*, but n=2/arm at one memory
  configuration does not establish robustness across memory configurations or
  machines.

**Corrected wording** (replacing "reproduced under two memory configurations"):
"A small batch-1 regression was observed consistently across the four archived
ABBA legs at one memory configuration; additional testing would be needed to
establish its robustness across memory configurations and other environments."

The earlier claim conflated two facts: the c=1 cell itself ran at only one
memory configuration, while the two-memory-configuration reproduction
(pilot `_pilot4x_A_c16` at memfrac 0.30 vs formal `A_c16` at 0.75+100k) was
performed at c=16, where it reproduced the medians to 4 significant figures.
FINAL_VALIDATION_REPORT finding 2 and GITHUB_REPLY_DRAFT have been corrected
accordingly (the c=16 memory-config reproduction is still reported, but as a
c=16 result).

## 4. Metric layers at high concurrency — do not attribute e2e gains to the kernel alone

At c=64 (model A), recomputed from the raw artifacts:

| metric layer | Main | PR | PR gain | source |
|---|---|---|---|---|
| server decode step time (author's method, steady windows, queue-req 0) | 9.93 ms/step | 9.43 ms/step | **1.053×** | server logs |
| client median ITL (includes inter-step gaps) | 31.95 ms | 24.10 ms | **1.326×** | bench JSONs |
| client median TPOT | 35.02 ms | 26.06 ms | 1.344× | bench JSONs |
| end-to-end output throughput (64×(1024in+256out)) | 1712.0 tok/s | 2255.7 tok/s | **1.318×** | bench JSONs |

Supporting facts recomputed from the c=64 logs: identical completed counts
(64/64), identical total output tokens (16384), identical running-req pattern
(ramp 8→64), identical prefill-batch counts (23), wall duration 9.6 s (main)
vs 7.3 s (PR).

Interpretation (bounded by the evidence):

- The pure decode *step* (the part the PR's launch change directly targets) is
  only ~5% faster; 240 steady decode steps account for roughly 2.4 s of the
  ~9.6 s main-arm run. The 31.8% end-to-end gain therefore mostly comes from
  **outside the sampled steady decode steps** — i.e., shorter/less frequent
  non-decode intervals (scheduling gaps, ramp/stall behavior) under load.
- The client-side ITL gain (1.326×) matches the end-to-end gain (1.318×),
  confirming that the benefit reaches the client; the decode-window metric is
  simply a narrower lens.
- The same layering pattern holds at c=32 (e2e 1.166×, ITL 1.197×, step
  1.043×) and, weaker, at c=16 (1.105 / 1.114 / 1.072); at c=8 all three
  layers agree (≈1.05×). The kernel-level mechanism explains the c=8 number;
  the larger high-concurrency e2e numbers include load-dependent scheduling
  effects whose mechanism is **not established by the available evidence** and
  remains an open observation, not a claimed root cause.

Correct public phrasing: "up to +32% end-to-end output throughput at
concurrency 64, with +5% decode step time; the additional gain at high
concurrency comes from reduced non-decode-step overheads, whose mechanism we
have not isolated." The 31.8% must never be quoted as a kernel-only speedup.

## 5. Direction consistency with the PR author's environment

Model B's small gains (c≥32 ≈ +1.4–2.1%) match the direction of the author's
gfx1151 result (1.08–1.11×) on a different hardware/software generation;
magnitudes do not transfer (LIMITATIONS.md L3). This is a directional
observation only.
