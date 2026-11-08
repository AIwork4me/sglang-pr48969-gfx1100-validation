# REVIEW_REQUEST — owner review before any upstream action

Dear Owner (AIwork4me),

The campaign evidence is complete and pushed, and an independent audit round
(2026-11) has reconciled every published number against the raw artifacts.
Nothing has been posted to the upstream SGLang project. Before replying to
@twoask (draft: `GITHUB_REPLY_DRAFT.md`), please review:

## 0a. PR #2 final owner review (2026-11-08)
- [ ] `followup/audit/FINAL_REPAIR_REPORT.md` — repair verdict (GO/MERGE-READY),
      P0/P1 ledger, recomputed performance table, determinism BLOCKED scoping.
- [ ] `followup/audit/BASELINE.md` — frozen GitHub state + determinism
      two-invocation provenance.
- [ ] Latest archived CPU audit (2026-11-08): historical Audit V2 **55/55 PASS**;
      Follow-up Audit **18/18 PASS**; **53 passed, 2 skipped** in pytest;
      SHA256 follow-up manifest **115/115 PASS**. These are archived results,
      not a claim of a new GPU run or a GitHub CI check (none configured).
- [ ] Fail-closed manifest regression tests (12), determinism mocks (9),
      and follow-up evidence tamper tests (12) are in the CPU-only suite.
- [ ] Original benchmark, accuracy, kernel and follow-up GPU raw files are
      byte-unchanged by the repair round; use `followup/audit/raw_evidence_freeze.digest`
      and the historical/separate repair manifests to validate.

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
- [ ] **Historical audit-round corrections (before the later GPU follow-up)**
      (listed in `audit/SHA256SUMS_AUDIT_ROUND`): the earlier unsupported
      batch-1 "two memory configurations" claim was withdrawn at that time
      (the original second-configuration measurement was c=16, not c=1);
      subsequently PR #2 collected genuine c=1 data at both configurations.
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
- [ ] Known unfavorable results retained: c=1 Qwen3-0.6B/16Q-8KV regression
      at **both** memory configurations (0.75+100000: 0.9842× historical,
      0.9828× repeat, pooled *within that configuration only* n=4/arm 0.9806×;
      0.30/auto: 0.9858× separately); c=2 1.0034× and c=4 0.9984× are
      near-neutral, not proven gains; first clearly positive measured point
      c=8 1.0475×. Also retain mixed-length ms/step ≤ 1.0, OOM'd
      sliding-window test, and B c=16 0.993×.
- [ ] Deterministic-serving startup is **BLOCKED on both arms** with the tested
      gfx1100 software stack: persistent matmul requires 99,328 B LDS against
      the runtime-reported 65,536 B limit; this is not a PASS and not shown
      to be caused by upstream PR #48969. Do not generalize to all ROCm stacks.

## 5. Final decision checklist before upstream reply
1. Verify PR #2 follow-up evidence and repair manifests first. Batch-1:
   the Qwen3-0.6B 16Q/8KV regression is consistently reproduced under
   **two** memory configurations; do not combine 0.30/auto and 0.75/pinned
   legs in one pooled estimate. The 0.75-only n=4/arm median ratio is 0.9806×.
2. Keep the metric layers separate: c=64 1.318× is **end-to-end output
   throughput**, while decode step is 1.053×; the mechanism behind the
   additional high-concurrency improvement was not isolated.
3. Characterize c=2 (1.0034×) and c=4 (0.9984×) as near-neutral; c=8
   (1.0475×) is the first clearly positive point in the tested grid. Serving
   concurrency is **not** the kernel's actual batch, so do not recommend a
   literal `if concurrency >= 8` condition in the upstream kernel.
4. Retain bounded correctness and accuracy conclusions: 17/17 archived
   bitwise kernel comparisons, all five paired GSM8K McNemar p ≥ 0.50,
   **not** formal equivalence; mark deterministic-serving **BLOCKED**, and
   disclose the co-tenant VRAM, environment workarounds and coverage gaps.
5. If PR #2 is merged, use immutable merged-main evidence links in the
   maintainer response. The reply remains an explicit **separate owner action**.

`GITHUB_REPLY_DRAFT.md` is a draft for @twoask, not an approved comment.
**Do not post to upstream as part of this validation-repository merge.**
