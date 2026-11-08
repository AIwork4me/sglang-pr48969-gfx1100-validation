# SGLang PR #48969 — independent gfx1100 (Radeon PRO W7900) validation

Independent A/B evidence for the grouped GQA decode-attention launch
optimization in https://github.com/sgl-project/sglang/pull/48969, measured on
AMD RDNA3.0 (gfx1100) at the exact pinned revisions requested by the PR author.

**Owner review in progress — this repository is the evidence package; nothing
here has been submitted to the upstream SGLang project.**

## Contents
- `FINAL_VALIDATION_REPORT.md` — read this first: results, findings, recommendation
- `GITHUB_REPLY_DRAFT.md` — maintainer-ready reply for @twoask (NOT posted)
- `REVIEW_REQUEST.md` — guided review checklist for the owner
- `REPRODUCE.md` / `ENVIRONMENT.md` / `LIMITATIONS.md`
- `audit/` — 2026-11 audit round: baseline inventory, claim-to-evidence matrix,
  closure report, closure manifest, local-audit log
- `patches/` — the temporary gfx1100 gate patch (+ the applied diff and the
  sgl-kernel gfx1100 wave32 build patch adapted from upstream's gfx1151 one)
- `configs/` — model manifest, benchmark matrix, eval config, environment manifest
- `results/` — machine-readable raw + summary CSVs (performance, accuracy, kernel
  correctness, regression gates)
- `evidence/` — raw logs, launch captures, source verification records, telemetry;
  `EVIDENCE_AUDIT_V2.md` (55-check independent audit, 2026-11 round),
  `STATISTICAL_RECONCILIATION.md`, `accuracy/EXECUTION_MANIFEST.md`
- `scripts/` — every script used, rerunnable; `audit_local.sh` = CPU-only audit entry
- `tests/` — auditor tamper-regression tests (pure CPU)
- `plots/` — generated from `results/`

## Headline (Model A: Qwen3-0.6B, 16 Q / 8 KV heads; ABBA ×2 per cell)

| concurrency | 1 | 4 | 8 | 16 | 32 | 64 |
|---|---|---|---|---|---|---|
| PR/Main output throughput | 0.984 | 1.00 | 1.047 | 1.105 | 1.166 | **1.318** |

These are end-to-end output-throughput ratios. The kernel-level decode step
gain is smaller (e.g. 1.053× at c=64); the difference at high concurrency comes
from reduced non-decode-step overheads whose mechanism is not isolated — see
evidence/STATISTICAL_RECONCILIATION.md §4. Audit round 2026-11: every number in
this README is recomputed from raw artifacts by `scripts/verify_evidence_v2.py`
(`bash scripts/audit_local.sh` reproduces the audit CPU-only from a clean
clone; report: evidence/EVIDENCE_AUDIT_V2.md, 55 checks).

Kernel outputs **bitwise identical** across arms (17/17 cases); GSM8K shows no
detectable systematic change (paired exact McNemar p ≥ 0.50 on all five pairs,
n=200/1319). Optimization provably active in live serving (672/672 launches
`num_warps=2`, CDNA hints removed); excluded configurations provably unchanged.
Batch-1 regression on the 16/8 geometry: −1.4…−1.9%, sign-consistent in 12/12
legs, reproduced under two memory configurations (2026-11-08 follow-up round —
`followup/ANALYSIS.md`, which also measures c=2 ≈ 1.00× and root-causes
deterministic-serving unavailability on gfx1100). See report finding 2 and
evidence/STATISTICAL_RECONCILIATION.md.

## Provenance
- Main: `0afb736d0aab96e3ab80b4c54a376213a1db67a6` — byte-verified against GitHub's tree API (12,039 files)
- PR: `3fdf6f7318364c1b09398aea4d947ed633ac9eca` — byte-verified (12,040 files)
- Local gate patch: `patches/pr48969-gfx1100-validation.patch` (PR arm only)
- Environment: ROCm 7.2.1 / torch 2.9.1+git rocm7.21 / Triton 3.6.0+rocm7.2.0 / sgl-eval 0.1.3

Everything is recomputable from `results/` + `evidence/`; see `REPRODUCE.md`.
