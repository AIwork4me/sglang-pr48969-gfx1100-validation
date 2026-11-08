# GPU FOLLOW-UP ANALYSIS — round 2026-11-08

Owner-authorized follow-up to the 2026-11 audit round, executed on the same
W7900 host with the historical arm environments reused byte-for-byte (gate
patch re-verified present on the PR arm, absent on main before starting;
co-tenant memory situation unchanged: 33.21 GB of 51.52 GB held all round —
`evidence_environment/rocm_smi_mem_*.txt`). Invocations:
`scripts/run_followup.sh`. Fail-closed verifier: `scripts/verify_followup.py`
(**11/11 PASS**; re-extracts decode ms/step, recomputes every median/speedup,
and validates the per-cell memory configuration from the archived server args).

## R1. Batch-1 regression — now confirmed under two memory configurations

| cell (A=Qwen3-0.6B, c=1, 1024/256, rr=1) | config | main med tok/s | PR med tok/s | tput spd | ms/step spd |
|---|---|---|---|---|---|
| A_c1 (historical, 2026-11-07) | 0.75 + maxtok 100000 | 132.39 | 130.29 | 0.9842 | 0.9818 |
| **A_c1_rep (new)** | 0.75 + maxtok 100000 | 132.87 | 130.58 | 0.9828 | 0.9855 |
| **A_c1_mem030 (new)** | **0.30 + auto pool** | 132.33 | 130.45 | **0.9858** | **0.9834** |

Combined c=1 @0.75 estimate (historical + repeat, n=4/arm): median 132.87 vs
130.29 tok/s → **0.9806×**; the distributions are fully separated — **all four
PR legs are below all four main legs** (PR 129.8–131.3, main 131.8–132.9), and
likewise all four PR ms/step values exceed all four main values (median
ms/step spd 0.982×).

Conclusion: the batch-1 regression is **reproduced under both memory
configurations** and across two independent ABBA sessions (8/8 legs consistent
by sign at 0.75; 4/4 at 0.30/auto). The audit round's conservative wording
("one memory configuration; robustness not established") can now be upgraded to:
"a consistent −1.4…−1.9% c=1 regression for the 16/8 geometry, reproduced
under two memory configurations (0.30/auto and 0.75/pinned) and fully
separated across 8 legs at the primary configuration."

## R2. Crossover region: c=2 is neutral

A_c2 (new, 0.75+100000): tput spd **1.0034×**, ms/step spd 1.0026×
(main 240.7 vs PR 241.5 tok/s median). The measured curve is now
c=1: 0.981–0.986× · c=2: 1.003× · c=4: 0.998× · c=8: 1.047× — the crossover to
a consistent gain sits between c=4 and c=8, matching the report's wording.

## R3. Deterministic-serving mode — BLOCKED: startup failure confirmed on both arms

`--enable-deterministic-inference` was exercised on both arms (first time in
this campaign). Result: **the server dies during startup on both arms with the
identical error class** — the compiled batch-invariant persistent matmul
kernel requires **99,328 bytes of shared memory against a reported 65,536-byte
hardware limit**:

```
triton.runtime.errors.OutOfResources: out of resource: shared memory,
Required: 99328, Hardware limit: 65536
```

Evidence & classification:
- Logs: `evidence_determinism/server_{main,pr}.log` (window 03:11:52–03:12:17Z
  main / 03:12:45–03:13:10Z pr; identical server_args incl.
  `enable_deterministic_inference: True`, `mem_fraction_static 0.75`,
  `max_total_tokens 100000`, triton backend; both arms log "Sampling backend
  is set to pytorch for deterministic inference" before the crash, so the flag
  demonstrably took effect).
- Provenance (repair-round correction): the two logs came from **two
  invocations** — the experiment-round script stopped after main's failure
  (`set -e` + `exit 2`), and the pr log was produced by a sed-derived
  single-arm variant, archived verbatim as `scripts/determinism_pr.historical.sh`
  (one-line diff against the experiment-round script; see
  `followup/audit/BASELINE.md`).
- Machine-readable verdict: `results/determinism_verdict.json` — per-arm
  **BLOCKED** (resource-limit startup failure), overall
  "**BLOCKED / startup failure confirmed on both arms**",
  `identical_error_class_across_arms: true`.

Scope bound: with the tested SGLang/PyTorch/Triton/ROCm stack on this gfx1100
host, deterministic-serving startup fails in a batch-invariant persistent
matmul as above. This does **not** assert that deterministic inference is
unavailable on gfx1100 under other stacks, does **not** implicate PR #48969
(identical failure on both arms; the failing path `batch_invariant_ops.py` is
outside the PR's decode-attention change), and does **not** imply anything
about AMD GPUs' general deterministic-computing capability. The repaired
per-arm runner is `scripts/determinism.sh` (one arm failing no longer prevents
the other; verdicts PASS/BLOCKED/FAIL/NOT_RUN); it was **not** re-executed on
the GPU in the repair round — its control flow is covered by mock tests
(`tests/test_determinism_flow.py`).

## What was intentionally not re-run

GSM8K (accuracy conclusions unchanged), the full A/B grid, and kernel
correctness (historical evidence stands; source trees untouched this round).
MLA/hd256/fp8 end-to-end serving remain blocked by model availability/VRAM
(co-tenant still present); Qwen3-8B still does not fit; Phi-4-mini network
unchanged. Scheduler-level profiling of the c=64 overhead gap (§4 of the
statistical reconciliation) remains open.

## R4. Statistical interpretation guardrails (repair round)

- The 0.75-configuration legs (historical `A_c1` + `A_c1_rep`) and the
  0.30/auto legs (`A_c1_mem030`) are **never pooled**: the combined n=4/arm
  estimate uses 0.75 legs only; the 0.30 result stands alone (0.9858×) as the
  second-configuration reproduction.
- Labeling: c=2 is **near-neutral** (1.0034×, |Δ|<0.5%); c=4 at 0.998× is
  **not a claimed gain** (within run spread); c=8 at 1.047× is the **first
  clearly positive** point. Serving concurrency is **not** the kernel's
  batch: the grouped decode kernel sees the running/padded batch
  (cuda-graph buckets 1,2,4,8,…) times head_tiles (=8 here), so any upstream
  gate reasoning must use the kernel's own `batch * head_tiles` view — this
  repo explicitly does **not** propose a gate like `if concurrency >= 8`;
  upstream gate design is a separate task (see
  `results/followup_summary_v2.json` → interpretation).

## Verdict impact

- Audit-round batch-1 caveat: **resolved upward** (stronger evidence, same
  direction). The upstream reply draft's caveat is updated accordingly.
- Deterministic-serving: from "not verified" to **BLOCKED — startup failure
  confirmed on both arms, scoped to the tested stack** (LDS 99,328 vs 65,536
  bytes) — a concrete, checkable fact for the maintainer, with explicit
  non-implication of PR #48969.
- No previously published number changed.
