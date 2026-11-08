# FINAL CLOSURE REPORT — audit round 2026-11 (P0/P1 evidence & reproducibility closure)

Branch: `audit/p0-p1-evidence-closure` (from `main` @ `fe13f48e2e0d8b19bbd714b26e26ea02b1d90fd4`).
Scope: documentation, statistics, reproduction tooling, and audit tooling only.
**No new GPU benchmarks were run in this round.** All historical raw evidence is
byte-unchanged (verified: 666/676 sealed files identical, 10 tooling/config
files modified with documented reasons, 0 unexpected changes — §D).

## A. Executive Summary

**Completed**: baseline freeze and inventory; reproduction contract rebuilt
around four explicit tiers (T1 historical / T2 current-rerun / T3 CPU-only
analysis / T4 GPU-required); GSM8K per-run execution manifest reconciled
against metrics.json + server logs (including a real max_tokens discrepancy);
a new 55-check fail-closed evidence auditor (V2) that recomputes every
published number from raw artifacts; 22 CPU tamper-regression tests proving
the auditor fails when evidence is altered; independent accuracy/performance
recomputation tools; statistical reconciliation (paired McNemar, corrected
spread statements, corrected batch-1 claim, metric-layer attribution);
LIMITATIONS rewritten (memory constraint scope, shim classification,
kernel-vs-e2e coverage); claim-to-evidence matrix; security scan; closure
manifest; owner-ready upstream reply draft (NOT posted).

**Fixed**: 3 P0 classes (reproducibility gaps, GSM8K configuration
reconciliation, weak audit) and 4 P1 classes (statistics, batch-1 claim,
memory disclosure, cross-document consistency). Full ledger in §B.

**Not completed (by policy)**: any new GPU work — c=1 re-measurement under a
second memory configuration, MLA/hd256/fp8-KV end-to-end serving, Qwen3-8B /
Phi-4-mini / 14B / gpt-oss-20b, deterministic-serving verification. All listed
as optional GPU follow-ups in §E.

**Final verdict: GO FOR OWNER REVIEW / GO FOR UPSTREAM COMMENT** (gates G0–G12
all satisfied; see §F). This is explicitly NOT "all gfx1100 workloads
validated" — coverage bounds remain as disclosed in LIMITATIONS.md L5.

## B. P0/P1 Closure Ledger

| # | Problem (before) | Root cause | Fix (after) | Evidence | Tests | Status |
|---|---|---|---|---|---|---|
| P0-1 | REPRODUCE.md referenced uncommitted files (`work/run_final.sh`, `work/build_sglkernel.sh`, `work/venv_<arm>/python`, `sha256sum ...` placeholder) as if runnable; scripts hardcoded `/root/sglang-pr48969-validation` | historical campaign root + uncommitted `work/` dir; doc never reconciled to the repo | 4-tier reproduction contract; repo-root localization with `SGLANG_VALIDATION_*` overrides; path-reference verifier (fail-closed); gaps listed explicitly | REPRODUCE.md; scripts/verify_reproduction_paths.py; audit/BASELINE_INVENTORY.md §6 | tests/test_reproduction_contract.py (9 tests) | CLOSED |
| P0-2 | GSM8K script hardcoded `--max-tokens 2048` but archived A pairs ran 1024; eval_config listed a never-executed run and omitted `gsm8k_A_full_2048`; intermediate script versions unarchived | script edited mid-campaign; only final version committed; config drift vs evidence | max_tokens is an explicit required script parameter (fail-closed); per-run execution manifest built from metrics.json + server logs (incl. per-pair memfrac/max-total-tokens); config file reconciled | evidence/accuracy/EXECUTION_MANIFEST.md; configs/eval_config.yaml | V2 checks `acc_settings_perfield_symmetric`, `acc_maxtok_n_labels_consistent`, `acc_server_memconfig_symmetric_and_manifest` | CLOSED (historical script versions remain unarchived — documented gap, unrecoverable) |
| P0-3 | Auditor V1 weak: set-size settings check (`len(set(...))<=4`), pilot legs counted as measured ("64"), no recompute of medians/speedups/scores, trusted summary labels, "48 legs" in gates CSV | auditor trusted summaries; count drift between artifacts | Audit V2: 55 checks, everything recomputed from raw artifacts, per-field comparisons, ABBA completeness, warmup/pilot exclusion, launch-command equivalence, BLOCKED-retention; G9 corrected 48→60 | scripts/verify_evidence_v2.py; evidence/EVIDENCE_AUDIT_V2.{md,json} | tests/test_auditor_regression.py (12 tamper tests) | CLOSED |
| P1-1 | Run-spread claim "0.1–0.6% tput / 0.2–2% ms/step" understated tails (actual up to 3.0%/3.2%) | claim written from a subset of cells | corrected in FVR §3, LIMITATIONS L7, gates G10; auditor now parses the documented bound against the recomputed max | LIMITATIONS.md L7; evidence/STATISTICAL_RECONCILIATION.md §2 | V2 check `perf_runspread_claim_supported` | CLOSED |
| P1-2 | "batch-1 regression reproduced under two memory configurations" — not supported (c=1 ran at one config; the 0.30-vs-0.75 reproduction was at c=16) | conflation of the c=16 pilot with the c=1 cell | claim withdrawn and replaced with leg-consistent-at-one-config wording in FVR finding 2, GITHUB_REPLY_DRAFT, SR §3; c=16 reproduction still reported, scoped to c=16 | evidence/STATISTICAL_RECONCILIATION.md §3 | V2 doc checks | CLOSED |
| P1-3 | c=64 "1.318×" risked being read as kernel speedup (decode step is 1.053×) | e2e and kernel layers conflated in summary prose | layered attribution everywhere (README headline note, FVR finding 1, reply draft): step 1.053× / ITL 1.326× / e2e 1.318×; mechanism of extra gain marked not-isolated | evidence/STATISTICAL_RECONCILIATION.md §4 | recomputation + doc checks | CLOSED |
| P1-4 | GSM8K "within binomial σ" argument treated arms as independent | paired data available but unused | paired exact McNemar on id-joined per-question outcomes: all 5 pairs p ≥ 0.50; formal equivalence explicitly not claimed | evidence/STATISTICAL_RECONCILIATION.md §1; scripts/recompute_accuracy.py | V2 checks `acc_paired_*` | CLOSED |
| P1-5 | "All A/B ratios are unaffected [by co-tenant memory]" overclaimed; GB/GiB mixed; shims described as ratio-neutral | imprecise disclosure | L1 rewritten (symmetric control ≠ magnitude-invariance; units fixed 51.52 GB = 48 GiB); L2 shim table separates hot-path norm shim and bounds transferability | LIMITATIONS.md L1/L2; ENVIRONMENT.md | doc review + V2 | CLOSED |
| P1-6 | Doc/config/evidence inconsistencies (eval_config runs, G9 count, +0.31 pp rounding, `capture_*.json` glob, README contents) | incremental edits never cross-checked | cross-document reconciliation pass; claim-to-evidence matrix for every public number; V2 enforces doc↔recompute agreement continuously | audit/CLAIM_TO_EVIDENCE_MATRIX.md | V2 `doc_*` checks (6) | CLOSED |

## C. Numerical Reconciliation

Benchmark numbers: **no historical performance or accuracy value changed**.
Every headline value re-verified against raw artifacts (speedups, medians,
ms/step, ITL, TTFT, scores, truncation, kernel counts). Values corrected this
round were *statements about* the data, not the data:

| item | before | after | reason |
|---|---|---|---|
| A_full_2048 delta | +0.31 pp | **+0.30 pp** | true delta 0.3033 rounds to 0.30 |
| run-spread (throughput) | "0.1–0.6%" | **0.0–3.0%** (most cells ≤0.7%) | recomputed over all 15 cells (max A_long_4k_c8 PR 3.03%) |
| run-spread (ms/step) | "0.2–2%" | **0.03–3.2%** | recomputed (max A_c32 PR 3.18%) |
| G9 measured legs | "48" | **60 formal** (+4 pilot excluded) | 15 cells × 2 arms × 2 runs |
| batch-1 claim | "reproduced under two memory configurations" | **one memory configuration, 4 consistent legs** | c=1 cell ran only at 0.75+100k |
| GSM8K stats framing | "σ≈1.3pp, ≲0.6σ" | **paired exact McNemar p ≥ 0.50 (5/5)** | stronger, design-appropriate test |
| audit count | "22/22" | **22/22 historical (retained) + 55/55 V2 (recomputed)** | V2 has more, stricter checks |

Newly surfaced and documented (not errors in results): A_c4 bench r1 files
contain an appended abandoned memfrac-0.30 attempt (CSV verified to use the
final 0.75 document); GSM8K A pairs ran at memfrac 0.30/auto (B and A_full_2048
at 0.75/pinned) — arm-symmetric within every pair.

## D. Evidence Integrity

- Sealed manifest `evidence/checksums/SHA256SUMS` (676 entries, 2026-11-07):
  666 files byte-identical; 10 tooling/config files modified this round, every
  one listed with its reason in `scripts/verify_evidence_v2.py::REPAIRED_THIS_ROUND`
  and `audit/SHA256SUMS_AUDIT_ROUND`; **0 unexpected mismatches, 0 missing**.
- Raw benchmark JSONs, metrics.json, prediction JSONLs, kernel .pt/captures,
  spy log, server/runner logs, telemetry: untouched (git diff vs main under
  `evidence/` and raw results is empty).
- Historical `evidence/EVIDENCE_AUDIT.md` retained unchanged; V2 supersedes it
  and states the relationship explicitly.
- `sources.sha256` references lab-local tarballs not in the repo — recorded as
  a reproduction gap (BASELINE_INVENTORY §4), not a verification pass.
- Security scan (full repo): no credentials, keys, or tokens; the only
  credential-adjacent artifact is a **masked** gh token (`ghp_****`) in an
  archived environment log, plus non-secret account metadata.

## E. Remaining Limitations

**Must fix before upstream comment**: none known. (If the owner disagrees with
any corrected wording, that is a review decision, not an open defect.)

**Optional follow-up GPU validation** (would strengthen, not unblock):
1. c=1 (and c=2–4) re-measurement under a second memory configuration —
   directly tests the batch-1 caveat's robustness (the one open low-batch
   question).
2. A head_tiles=8 model with tighter measurement (n≥4/arm) to size the batch-1
   penalty more precisely.
3. MLA / head_dim-256 / fp8-KV end-to-end serving on unaffected configs.
4. Qwen3-8B serving once VRAM is free; Phi-4-mini (24/8 geometry) if the
   network allows; deterministic-serving verification.
5. Isolation of the high-concurrency non-decode-step overhead gain (scheduler
   profiling) — explains the 1.318× vs 1.053× layering.

**Out of scope**: re-running the historical campaign verbatim (T1 byte-exact
reproduction is impossible — uncommitted `work/` orchestrator and intermediate
script versions); validating other RDNA3 SKUs; upstream PR modification of any
kind.

## F. Recommended Next Step

**GO FOR OWNER REVIEW / GO FOR UPSTREAM COMMENT.**

The evidence package is now internally consistent, every published number is
independently recomputed from raw artifacts by a fail-closed auditor with
tamper regression tests, all reproduction gaps are explicit, and the corrected
claims (batch-1 scoping, spread ranges, metric-layer attribution, paired
statistics, memory/shim disclosure) are conservative and traceable. The owner
should review `REVIEW_REQUEST.md` (esp. §0 and §5), then may post
`GITHUB_REPLY_DRAFT.md` to @twoask as-is or amended. **No automated or
unauthorized posting; no upstream action from this audit round.**

Gate summary: G0 baseline captured ✓ · G1 raw evidence unchanged ✓ ·
G2 reproduction contract consistent ✓ · G3 GSM8K reconciled ✓ ·
G4 summaries recomputed ✓ · G5 Audit V2 independently passes (55/55) ✓ ·
G6 batch-1 claim corrected ✓ · G7 memory limitation disclosed ✓ ·
G8 statistics qualified ✓ · G9 cross-document consistency ✓ ·
G10 security + SHA256 ✓ · G11 reply draft review-ready ✓ ·
G12 draft PR prepared, no upstream action ✓

---

## Addendum — Round 2: owner-authorized GPU follow-up (2026-11-08, branch `gpu-followup/c1-memory-determinism`)

Scope: the optional GPU follow-ups listed in §E were executed on the same
W7900 host with the historical arm environments reused verbatim (gate state
re-verified before starting; co-tenant 33.21/51.52 GB unchanged; no GSM8K
re-run; no changes to any historical evidence). Raw artifacts + fail-closed
verifier: `followup/` + `scripts/verify_followup.py` (**11/11 PASS**),
integrated into `scripts/audit_local.sh` (**10/10 PASS** from a clean copy).

Results:

1. **Batch-1 caveat resolved upward**: the c=1 regression (−1.4…−1.9%) is now
   sign-consistent across 12/12 measured legs, fully separated at n=4/arm at
   0.75+100k (median 0.9806×), and **reproduced under a second memory
   configuration** (0.30/auto: 0.9858×) — the exact experiment the audit
   round had flagged as missing.
2. **c=2 measured (new point): neutral** (1.0034×) — crossover to consistent
   gains remains between c=4 and c=8.
3. **Deterministic-serving root-caused**: `--enable-deterministic-inference`
   cannot start on gfx1100 (batch-invariant persistent matmul requires
   99,328 B LDS > 65,536 B HW limit; identical on both arms) — upgraded in
   LIMITATIONS L5 from "not verified" to a concrete architecture limit.

Updated docs: STATISTICAL_RECONCILIATION §3/§6, FINAL_VALIDATION_REPORT
finding 2, LIMITATIONS L5, GITHUB_REPLY_DRAFT caveats/bottom line, README,
CLAIM_TO_EVIDENCE_MATRIX C11. No previously published number changed.
Verdict remains **GO FOR OWNER REVIEW / GO FOR UPSTREAM COMMENT**; the
reply draft's batch-1 caveat is now backed by two-configuration evidence.
