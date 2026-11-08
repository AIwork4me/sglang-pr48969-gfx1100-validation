# REVIEW_REQUEST — owner review before any upstream action

Dear Owner (AIwork4me),

The campaign evidence is complete and pushed, and an independent audit round
(2026-11) has reconciled every published number against the raw artifacts.
Nothing has been posted to the upstream SGLang project. Before replying to
@twoask (draft: `GITHUB_REPLY_DRAFT.md`), please review:

## 0. Audit-round summary (new in 2026-11)
- [ ] `audit/BASELINE_INVENTORY.md` — pre-modification baseline (git SHA,
      per-file hashes, 676/676 sealed-manifest verification).
- [ ] `evidence/EVIDENCE_AUDIT_V2.md` / `.json` — 55-check fail-closed audit,
      all values recomputed from raw evidence (the historical 22-check
      `EVIDENCE_AUDIT.md` is retained unchanged as an artifact).
- [ ] `audit/CLAIM_TO_EVIDENCE_MATRIX.md` — every public claim → evidence →
      recomputed value → status.
- [ ] `evidence/STATISTICAL_RECONCILIATION.md` — paired McNemar GSM8K analysis,
      corrected run-spread statement, batch-1 correction, c=64 metric layering.
- [ ] `evidence/accuracy/EXECUTION_MANIFEST.md` — per-run GSM8K ground truth
      (incl. the max_tokens script gap and per-pair memory configs).
- [ ] Corrections made this round (all listed in `audit/SHA256SUMS_AUDIT_ROUND`):
      batch-1 "two memory configurations" claim withdrawn (was c=16, not c=1);
      run-spread statement corrected (0.0–3.0%, not 0.1–0.6%); G9 gate leg
      count corrected 48→60; GSM8K max_tokens parameterized (fail-closed);
      A_full_2048 delta rounding +0.31→+0.30 pp; memory/workaround disclosure
      strengthened (LIMITATIONS L1/L2).

## 1. Trust anchors (30 min)
- [ ] Source identity: `evidence/source/verify_main.json` and `verify_pr.json`
      both say `verified: true` (recounted in Audit V2 against the tree JSONs:
      12,039 / 12,040 blobs).
- [ ] Main-arm integrity: `evidence/source/arm_tree_deltas.json` — Main differs
      from its pinned commit in exactly 4 build files (pyproject swap ×2 +
      sgl-kernel wave32 patch ×2), all replicated from upstream's own
      `docker/rocm-gfx1151.Dockerfile` procedure; `decode_attention.py` and all
      other runtime sources pristine; PR adds only the gate patch (verified
      against the archived source copies + applied.diff).
- [ ] The gate patch is what it claims: `patches/pr48969-gfx1100-validation.applied.diff`
      (6 added lines, nothing else).

## 2. The candidate really ran the new config (10 min)
- [ ] `evidence/kernel/capture_pr.json` vs `capture_main.json` (qualifying and
      boundary shapes: 2 warps + no hints vs 4 warps + hints; excluded shapes
      byte-identical across arms — recount checks in Audit V2).
- [ ] `logs/server/spy_pr.jsonl` — 672/672 serving launches with num_warps=2,
      measured runs uninstrumented (server command lines archived per leg and
      verified equivalent to the committed launcher by Audit V2).

## 3. Numbers (45 min)
- [ ] `results/performance_raw.csv` ↔ `results/performance_summary.csv`:
      every median/speedup recomputed from the bench JSONs (Audit V2 +
      `scripts/recompute_performance.py` re-extract decode ms/step from all 64
      server logs).
- [ ] GSM8K: scores recomputed from metrics.json AND the per-question files;
      paired McNemar p-values in `evidence/STATISTICAL_RECONCILIATION.md` §1.
- [ ] Reproduce the whole audit yourself, CPU-only, from a clean clone:
      `bash scripts/audit_local.sh` (expected: all PASS; details in
      `audit/audit_local.log`).

## 4. Honesty checks (15 min)
- [ ] `results/regression_gates.csv` — BLOCKED/NOT_RUN rows visible and
      retained (Audit V2 fails if any is flipped to PASS).
- [ ] `LIMITATIONS.md` — L1 (co-tenant memory; symmetric control, magnitude
      effect not excluded), L2 (norm shim is on the hot path), L5 (kernel vs
      e2e coverage separated), L7 (corrected spread ranges).
- [ ] Known unfavorable results retained: batch-1 regression (0.982–0.984,
      correctly scoped to one memory configuration), mixed-length ms/step ≤ 1.0,
      the OOM'd sliding-window test, B c=16 0.993.

## 5. Decision points for your reply
1. Batch-1 caveat wording (finding 2 + draft "Caveats"): report as
   leg-consistent at one memory configuration — agree?
2. Attribution wording: c=64 = 1.318× end-to-end vs 1.053× decode step; the
   high-concurrency extra gain is not attributed to the kernel alone — agree?
3. Recommendation wording: "correctness-neutral (kernel bitwise, GSM8K paired
   p≥0.50), net-positive e2e from c≈8 on the 16/8 geometry, low-batch guard
   question open" — agree?
4. Any configuration you want re-measured before replying (e.g. c=1 under a
   second memory configuration — flagged as optional GPU follow-up)?

After your review, `GITHUB_REPLY_DRAFT.md` can be posted verbatim or amended.
**It must not be posted by an automated process — owner action only.**
