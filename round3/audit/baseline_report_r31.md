# Round 3.1 — Phase 0 Read-Only Baseline Report

**UTC:** 2026-11-08 (R3.1 session)　**Audited HEAD at session start:** `6be6fb3bf4f0999ebe6bcf9d504d4941d51ad121`
**Remote:** `origin/validation/1da9ae2-w7900-round3` = same SHA (frozen; PR #3 open, Draft, mergeable)
**Working tree:** clean (0 modified). GPU evidence archive commit: `5a6cee126160cde47ac708efb81e32ae95d49194`.

## Baseline verification performed (read-only)

| check | result |
|---|---|
| `sha256sum -c round3/audit/SHA256SUMS` on working tree | PASS (852/852) |
| `bash round3/scripts/audit_round3.sh` on `git archive HEAD` snapshot | **AUDIT PASS (48 checks, exit 0)** — Clean Control already achievable |
| `bash scripts/audit_local.sh` (Round 1/2 audit) in real repo | **AUDIT LOCAL: PASS** (10/10 steps) |
| Round 1/2 sealed manifest (`audit/SHA256SUMS`) | PASS — 676 files verified |
| Round 3 baseline freeze (`round3/audit/baseline_freeze.sha256`) | PASS — 830 files byte-identical |

Environment note: an initial `audit_local.sh` run inside a `/tmp`-tmpfs snapshot failed with
exit 120 — root cause was **tmpfs disk exhaustion during the pytest pristine-copy fixture**
(≈2.4 GB × 2 copies vs 4 GB tmpfs), NOT evidence tampering. Re-run with adequate disk
passes all steps; both the Round 1/2 seal and the Round 3 freeze verify byte-identical.
This environment artifact is recorded here so it is not mistaken for an integrity finding.

## 1. Confirmed vulnerabilities in the audit system at HEAD (to fix this round)

| ID | Finding | Evidence |
|---|---|---|
| V1 | `audit_selftest.sh` passes the snapshot dir as `$0` (`bash -c "$corrupt" "$TMP/repo"`), corruption scripts read `$1` → **corruption never executed** | `negative_tests.log` lines `grep: /round3/audit/SHA256SUMS: No such file or directory`, `FileNotFoundError: '/round3/...'` |
| V2 | Selftest verdict logic = "audit exited nonzero → NEGTEST PASS": no proof the injection happened, no assertion that the *intended* gate fired | `audit_selftest.sh` lines 16–23 |
| V3 | Selftest fixture copies only `round3 configs patches`; the audit also reads repo-root Round 1/2 evidence (baseline freeze targets) → even an *untampered* copy fails the audit → every "rejection" was a fixture failure, not corruption detection. No Clean Control gate exists | `audit_selftest.sh` line 15 vs `audit_round3.sh` §2 |
| V4 | `audit_status_integrity.py` never cross-checks `VALIDATION_CERTIFICATE.json` against the independent `verdicts.json`; flipping a BLOCKED test to PASS (with resolvable evidence paths) passes the audit; raw execution verdicts (e.g. `determinism_r3/verdicts.jsonl` = `BLOCKED_LDS_LIMIT`) are ignored | code review; N07 scenario un-detected |
| V5 | `audit_performance.py`: (a) CSV↔raw mapping is one-directional — extra/duplicate CSV rows and row-count drift undetected; (b) `statistics.json` geo-mean/CI are validated only against `paired_ratios` stored **inside the same file** (self-certification), never recomputed from raw legs; pair counts never checked against execution order; (c) `missing_legs_disclosed` is unconditionally PASS; (d) `arm_totals` never reconciled with the certificate | code review |
| V6 | `audit_server_symmetry.py` silently skips unparsed configs and cells with <2 arms; a parse failure or a missing required arm is not an explicit FAIL | code lines 49–53 |
| V7 | Repo archive inconsistency: `audit_report_raw.log` is a **19:40 pre-repair FAIL run** while `audit_report.json` is a 20:43 PASS run; the stale failing log is not labeled historical | file headers |

## 2. Historical audit failure records (pre-repair; do NOT project onto current code)

- `audit_report_raw.log` @ 2026-11-08T19:40:43Z: `old_new_diff_single_line`, `server_config_symmetric_across_arms`, `status_integrity` FAIL — produced by an earlier script/evidence state on the GPU machine. All three gates PASS on the current tree (verified this session).
- `negative_tests.log`: 10 false `NEGTEST PASS` lines + `SELFTEST_EXIT=0` — artifact of V1–V3 (corruption never ran; rejections came from missing fixtures).
- Both files are preserved byte-identical under `round3/audit/historical/` as **Historical / Pre-repair Failure Evidence**.

## 3. Already fixed at HEAD (verified this session; no action needed)

- Certificate uses standard `BLOCKED` status with `BLOCKED_LDS_LIMIT` as the reason/sub-state — `statuses_valid_and_traced` and `declared_counts_match` now PASS (`{"PASS": 26, "BLOCKED": 1}`).
- `audit_server_symmetry.py` drops only the documented dynamic fields (`model_path`, `port`, `tp_size`, `random_seed` — seed exclusion reason recorded in code comment); all 117 server logs parse and agree on current evidence.
- `old_vs_new.diff` contains exactly one source-line change; `new_gate_is_1da9ae2` PASS.

## 4. Still to fix (R3.1 scope)

1. P0-A/P0-B: rebuild the negative-test framework (explicit function interface, `mktemp -d`, trap cleanup, full `git archive HEAD` snapshot, per-test Clean Control gate, injection proof via pre/post SHA256, target-gate assertion).
2. N01–N10 with semantic tests re-sealing the in-copy manifest so integrity checks pass and the *semantic* gate is proven to fire.
3. P0-C status-integrity hardening (certificate ↔ verdicts ↔ raw verdict records; BLOCKED never counts as PASS).
4. P1-A statistics anti-forgery (bidirectional leg bijection, ratios/CI/pairs recomputed from raw legs + order.jsonl, missing-legs recomputation, arm totals vs certificate).
5. P1-B symmetry hardening (parse-fail and missing-arm FAIL explicitly).
6. P1-C source-integrity robustness (single-line AND single-hunk assertion on the old/new diff; commit pin re-verified).
7. Phase 4 documentation wording (mitigated/near-parity phrasing, c=2 residual, c=4 dual disclosure, end-to-end throughput qualifier, BLOCKED preserved).
8. Reseal `round3/audit/SHA256SUMS` (historical entries preserved, changed files re-hashed, no duplicates/self-reference) + fresh-worktree verification.

**Frozen at baseline (must remain byte-identical through R3.1):** all 830 `baseline_freeze.sha256` entries, all raw `round3/evidence/**` GPU artifacts, `order.jsonl`, GSM8K outputs, kernel artifacts, and the Round 1/2 seals.
