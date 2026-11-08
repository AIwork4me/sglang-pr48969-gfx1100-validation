# FINAL REPAIR REPORT — PR #2 repair round (2026-11-08, branch `gpu-followup/c1-memory-determinism`)

All numbers in §C were recomputed from the raw artifacts during this round by
`scripts/verify_followup.py` (18 checks), `scripts/generate_followup_analysis.py`
(per-leg division recompute), and `scripts/recompute_performance.py` — not
copied from earlier reports. No GPU work was executed in this repair round
(the archived follow-up GPU evidence is unchanged and remains authoritative).

## A. Executive Verdict

- **GO FOR OWNER REVIEW / MERGE-READY.**
- PR #2 may be merged by the owner after review: base is `main`, tree is
  mergeable, all P0 defects are closed with fail-closed tooling and negative
  tests, all raw evidence is byte-unchanged.
- `GITHUB_REPLY_DRAFT.md` remains suitable for the upstream comment **after
  owner review** (still DO NOT POST — owner action only).

## B. P0/P1 Closure Ledger

| # | Issue | Root cause | Actual fix | Changed files | Test evidence | Status |
|---|---|---|---|---|---|---|
| P0-1 | follow-up manifest check could pass when `sha256sum` itself failed or output was redirected (`grep -cv ': OK$' \| grep -qx 0` pipeline) | pipeline counted OK-strings, ignored exit codes | new `scripts/verify_followup_manifest.py`: independent per-entry parse (64-hex, path safety, prefix scope, duplicates, traversal) + per-file re-hash; any anomaly exits 1; wired into `audit_local.sh` with `--min-entries` floor; historical sealed-manifest loop additionally requires >0 entries | scripts/verify_followup_manifest.py (new), scripts/audit_local.sh | tests/test_followup_manifest.py — 12/12 PASS incl. real-entrypoint propagation (audit_local exits non-zero on missing manifest and on a one-byte tamper) | CLOSED |
| P0-2 | PR #2 base pointed at `audit/p0-p1-evidence-closure` while PR #1 was already merged to main | PR #1 merged (652127c) after PR #2 was opened | base retargeted to `main` via REST PATCH (gh pr edit --base was a no-op through the GraphQL path); re-verified: MERGEABLE, Draft, identical 121-file diff, audit branch is ancestor of main | (PR metadata only) | `gh pr view 2` → baseRefName=main, mergeable=MERGEABLE, isDraft=true | CLOSED |
| P1-3 | determinism script: single-run `set -e` meant one arm's failure prevented the other; archived logs actually came from two invocations (undocumented); classification absent | experiment-round script design | `followup/scripts/determinism.sh` rewritten: independent `run_arm main`/`run_arm pr`, per-arm structured records (launch cmd, timestamps, PID/PGID, exit code, readiness, error class, verdict, evidence path), verdicts PASS/BLOCKED/FAIL/NOT_RUN, cleanup limited to its own process group; NOT executed on GPU this round (mock-tested); provenance of the two archived logs documented and the derived single-arm variant archived verbatim (`determinism_pr.historical.sh`, one-line diff) | followup/scripts/determinism.sh, followup/scripts/determinism_pr.historical.sh (new), scripts/derive_determinism_verdict.py (new), followup/results/determinism_verdict.json (new) | tests/test_determinism_flow.py — 9/9 PASS (both-arms-fail → BLOCKED; main-fails/pr-runs; different failures not merged; unrelated crash = FAIL; output mismatch = FAIL; startup failure never PASS; bystander process survives cleanup) | CLOSED |
| P1-4 | follow-up auditor checked only per-cell r1 server config; no per-leg field verification; no non-finite handling; sealed CSV carried absolute `/root/followup` paths | initial auditor depth | `verify_followup.py` extended 11 → 18 checks: f12 verifies EVERY leg (12/12) × (model, backend, context, memfrac, maxtok, conc, lengths, launch cmd, server log, telemetry) + runner params + no-failure markers; f13 throughput division recompute per leg; f14 non-finite policy (computed metrics must be finite; unused `request_rate=Infinity` documented); f15 normalized CSV (repo-relative, resolvable, row-identical, sealed original untouched); f16 summary_v2 recompute (spreads, combined-c1, no-pooling method, concurrency≠kernel-batch note); f4a missing server log = clean FAIL | scripts/verify_followup.py, scripts/generate_followup_analysis.py (new), followup/results/performance_followup_raw_normalized.csv (new), followup/results/followup_summary_v2.json (new) | tests/test_followup_tamper.py — 12/12 PASS (clean→inject→FAIL→restore→PASS for every scenario) | CLOSED |
| P1-5 | determinism claim wording risked over-generalization ("verified unavailable on gfx1100") | imprecise scoping | all public docs now use the scoped statement: with the tested SGLang/PyTorch/Triton/ROCm stack on this gfx1100 host, startup fails in a batch-invariant persistent matmul (99,328 B vs 65,536 B); BLOCKED classification; explicitly NOT attributed to PR #48969 (identical both arms; failing path outside the decode-attention change); no claim about other stacks or AMD determinism in general | LIMITATIONS L5, followup/ANALYSIS.md R3/R4, STATISTICAL_RECONCILIATION §6, GITHUB_REPLY_DRAFT, README, FINAL_VALIDATION_REPORT, CLAIM_TO_EVIDENCE_MATRIX C11 | verify_followup f9/f11 enforce log↔verdict consistency incl. BLOCKED-not-PASS | CLOSED |
| P1-6 | statistical interpretation guardrails needed codifying | wording risk | ANALYSIS R4 + summary_v2 interpretation block: 0.30 legs never pooled with 0.75 legs; c=2 near-neutral; c=4 not a claimed gain; c=8 first clearly positive point; serving concurrency ≠ kernel batch (cuda-graph padded batch × head_tiles); no `if concurrency >= 8` gate proposal — upstream gate design is a separate task | followup/ANALYSIS.md, followup/results/followup_summary_v2.json | verify_followup f16 enforces the no-pooling method string and the concurrency-vs-batch note | CLOSED |

## C. Performance Verification (recomputed this round from raw artifacts)

| Cell | Expected | Recomputed (this round) | Match |
|---|---:|---:|---|
| A_c1 historical (0.75+100k) | 0.9842× | 0.9842× (median 132.386 vs 130.291 tok/s; ms/step 0.9818×) | ✓ |
| A_c1_rep (0.75+100k, 2nd sample) | 0.9828× | 0.9828× (132.873 vs 130.582; ms/step 0.9855×) | ✓ |
| A_c1_mem030 (0.30/auto) | 0.9858× | 0.9858× (132.333 vs 130.451; ms/step 0.9834×) | ✓ |
| A_c1 combined @0.75 (n=4/arm) | 0.9806× | 0.9806× (132.873 vs 130.291; legs fully separated: PR 129.8–131.3 < main 131.8–132.9; 0.30 legs never pooled) | ✓ |
| A_c2 (0.75+100k) | 1.0034× | 1.0034× (240.680 vs 241.497; ms/step 1.0026×) — near-neutral | ✓ |
| A_c8 historical | 1.0475× | 1.0475× — first clearly positive point (c=4 at 0.9984× is not a claimed gain) | ✓ |

Per-leg bases: `output_throughput == total_output_tokens/duration` verified for
12/12 legs (f13); decode ms/step re-extracted from all 12 server logs (f4);
median ITL/TTFT are recorder aggregates (per-request series not archived —
documented limitation).

## D. Deterministic-Serving Findings

- **Actual error** (both arms): `triton.runtime.errors.OutOfResources: shared
  memory, Required: 99328, Hardware limit: 65536`, raised from
  `sglang/srt/batch_invariant_ops/batch_invariant_ops.py` persistent matmul
  during server startup with `--enable-deterministic-inference` (the flag
  demonstrably took effect: "Sampling backend is set to pytorch for
  deterministic inference" precedes the crash; server_args recorded True).
- **Both-arms evidence**: `followup/evidence_determinism/server_main.log`
  (03:11:52–03:12:17Z, venv_main) and `server_pr.log` (03:12:45–03:13:10Z,
  venv_pr); identical server_args (0.75/100000/triton) and identical error
  class/location. Produced by two invocations (documented; derived variant
  archived verbatim).
- **Scope**: "With this tested SGLang, PyTorch, Triton and ROCm stack on
  gfx1100, deterministic-serving startup fails in a batch-invariant persistent
  matmul because the compiled kernel requires 99,328 bytes of shared memory
  against a reported 65,536-byte limit." No claims beyond that scope.
- **Classification**: per-arm **BLOCKED** (resource-limit startup failure);
  overall **"BLOCKED / startup failure confirmed on both arms"** —
  `followup/results/determinism_verdict.json` (derived from the archived logs
  by `scripts/derive_determinism_verdict.py`, same rules as the repaired
  runner).
- **Causality with PR #48969**: none established; both arms fail identically
  and the failing path is outside the PR's decode-attention change. No
  implication for AMD GPUs' general deterministic-computing capability.

## E. Security & Integrity

- Historical raw files modified: **0** (sealed manifest: 666 unchanged + 10
  documented round-1 repairs + 0 unexpected; `git diff` vs `6042bb7` touches
  no raw evidence).
- Follow-up raw files modified: **0** (`followup/audit/raw_evidence_freeze.digest`
  — 99 files — re-verified this round; only tooling/docs/results-derivations
  changed).
- SHA256 results: original experiment manifest archived
  (`followup/audit/SHA256SUMS_EXPERIMENT_ORIG`, 108 entries); regenerated
  working seal `followup/SHA256SUMS` (verified fail-closed); repair-round
  manifest `followup/audit/SHA256SUMS_REPAIR_ROUND` covers everything this
  round changed/added.
- Tamper regression tests: 12 manifest scenarios (12/12) + 12 follow-up
  evidence scenarios (12/12) + 9 determinism control-flow mocks (9/9).
- Security scan: no credentials/tokens/keys in the round's diff; the archived
  gh-auth snapshot contains only an already-masked token (`ghp_****`) plus
  non-secret account metadata; internal host paths (/root, /opt) appear only
  as historical provenance, already disclosed.

## F. Remaining Gaps

- **Blocking defects**: none.
- **Optional GPU validation** (do not block merge): deterministic-serving on a
  stack where the batch-invariant matmul fits gfx1100's LDS (e.g. smaller
  block config or newer Triton); MLA/hd256/fp8-KV end-to-end serving;
  Qwen3-8B / Phi-4-mini / 14B / gpt-oss-20b; c=64 non-decode-overhead
  profiling; per-request latency archival for future ITL recomputation.
- **Upstream design questions** (separate task, no action here): whether the
  low-batch guard should use the kernel's `batch × head_tiles` view more
  strictly (e.g. batch ≥ 2 or a CU-count-scaled threshold).

## G. Final GitHub State

- Base: `main` @ `652127c` (contains merged PR #1); Head: this branch
  (final SHA in the repair-round manifest header / PR page).
- Status: **Draft, OPEN, MERGEABLE**; diff = 121 files (109 under `followup/`
  + 12 doc/tool updates), no unexpected files; no CI configured on this
  repository (no CI claim made).
- Review-ready URL: https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation/pull/2
