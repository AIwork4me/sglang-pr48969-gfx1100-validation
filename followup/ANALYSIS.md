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

## R3. Deterministic-serving mode — root-caused: cannot start on gfx1100

`--enable-deterministic-inference` was exercised on both arms (first time in
this campaign). Result: **the server dies during startup identically on both
arms** — the batch-invariant persistent Triton matmul kernel requires
**99,328 B of shared (LDS) memory, above gfx1100's 65,536 B hardware limit**:

```
triton.runtime.errors.OutOfResources: out of resource: shared memory,
Required: 99328, Hardware limit: 65536
```

Evidence: `evidence_determinism/server_{main,pr}.log`. This is an
architecture/stack limitation unrelated to the PR (identical failure on both
arms; the PR touches only the decode-attention launch config). LIMITATIONS.md
L5 is updated accordingly: deterministic-serving is **not available on gfx1100
at this stack revision** (previously listed as merely "not verified").

## What was intentionally not re-run

GSM8K (accuracy conclusions unchanged), the full A/B grid, and kernel
correctness (historical evidence stands; source trees untouched this round).
MLA/hd256/fp8 end-to-end serving remain blocked by model availability/VRAM
(co-tenant still present); Qwen3-8B still does not fit; Phi-4-mini network
unchanged. Scheduler-level profiling of the c=64 overhead gap (§4 of the
statistical reconciliation) remains open.

## Verdict impact

- Audit-round batch-1 caveat: **resolved upward** (stronger evidence, same
  direction). The upstream reply draft's caveat is updated accordingly.
- Deterministic-serving: from "not verified" to "root-caused unavailable on
  gfx1100 (LDS limit)" — a concrete, checkable fact for the maintainer.
- No previously published number changed.
