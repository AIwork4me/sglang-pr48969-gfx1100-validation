# PR #2 REPAIR ROUND — BASELINE (frozen 2026-11-08, before any modification)

## Actual GitHub state (re-queried, not assumed)

- PR #2: OPEN / **Draft**, head `gpu-followup/c1-memory-determinism` @
  `6042bb7285c1db7f8ebdceb5270323ab3a0b390e` (no drift), base
  `audit/p0-p1-evidence-closure` (to be retargeted to `main`), mergeable
  MERGEABLE, `statusCheckRollup: []` (no CI configured on this repository —
  any "CI PASS" claim would be false).
- PR #1: **MERGED** into `main` at 2026-11-08T02:42:55Z (merge commit
  `652127cba73dc93ae3cfa9cfa561f9763a82c557`); `origin/main` advanced
  `fe13f48..652127c`; the audit branch is an ancestor of main (verified with
  `git merge-base --is-ancestor`), so retargeting PR #2 to main yields the
  identical 121-file diff with no conflicts.
- Local: branch `gpu-followup/c1-memory-determinism`, HEAD = `6042bb7`,
  working tree clean (no unpushed/uncommitted user changes to preserve).
- Upstream SGLang PR #48969: read-only; no comment posted from this repo.

## Raw-evidence immutability at baseline (this round's admission check)

- `followup/SHA256SUMS` (sealed at follow-up data creation): **0 mismatches**
  over 108 entries — all follow-up raw artifacts byte-intact.
- Historical seal `evidence/checksums/SHA256SUMS`: 676 entries →
  **666 unchanged + 10 documented tooling repairs + 0 unexpected**.
- Independent freeze for this round:
  `followup/audit/raw_evidence_freeze.digest` (99 files across
  `followup/evidence_performance|determinism|environment`), generated from the
  working tree at `6042bb7`. Any file in that digest that changes during this
  repair round is a defect (except none are expected to).

## Determinism evidence audit (facts, before rewriting the contract)

- `evidence_determinism/server_main.log`: window 2026-11-08 03:11:52→03:12:17Z,
  launched from `work/venv_main`; `server_args` shows
  `enable_deterministic_inference: True`, `mem_fraction_static: 0.75`,
  `max_total_tokens: 100000`, `attention_backend: 'triton'`;
  "Sampling backend is set to pytorch for deterministic inference" logged
  (flag took effect); crash =
  `triton.runtime.errors.OutOfResources: shared memory, Required: 99328,
  Hardware limit: 65536` from `batch_invariant_ops.py` persistent matmul.
- `evidence_determinism/server_pr.log`: 03:12:45→03:13:10Z, `work/venv_pr`,
  identical server_args and identical error class/location.
- Execution provenance (correcting the reproduction contract): the two logs
  come from **two invocations**, not one. `followup/scripts/determinism.sh`
  (committed at `6042bb7`) had `set -euo pipefail` + `exit 2` on main-arm
  startup failure, so its single execution stopped after main. The pr log was
  produced by a sed-derived variant looping over `pr` only — now archived
  verbatim as `followup/scripts/determinism_pr.historical.sh`; the derivation
  is provable: `diff determinism.sh determinism_pr.historical.sh` differs in
  exactly one line (`for ARM in main pr; do` → `for ARM in pr; do`).
- Classification going forward: per-arm verdict **BLOCKED (startup failure —
  resource limit)**, overall "**BLOCKED / startup failure confirmed on both
  arms**"; scoped to this stack (see FINAL_REPAIR_REPORT §D).

## Admission status

All admission checks pass; no user-local changes to preserve; repair round
may proceed under NO-NEW-GPU constraints (all work here is CPU-only:
tooling, tests, docs, manifests, PR metadata).
