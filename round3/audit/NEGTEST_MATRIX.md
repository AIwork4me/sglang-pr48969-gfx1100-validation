# Round 3.1 — Negative-Test Matrix (fixture → expected failing gate)

Framework: `round3/scripts/negtest_lib.sh` (protocol) + `audit_selftest.sh` (driver).
Per-test protocol: fresh `git archive HEAD` snapshot → **Clean Control audit must PASS**
→ corruption applied → **injection self-verified** (pre/post SHA256 recorded) → audit
must exit nonzero → **expected gate must be among the reported FAILs**. Any other
outcome is `FAIL:injection_failed | clean_control_failed | audit_accepted |
target_gate_not_hit` — never a PASS.

| ID | corruption injected (disposable copy only) | manifest state during audit | expected gate that must FAIL | other gates that legitimately fire |
|---|---|---|---|---|
| N01 | one `0x00` byte appended to `evidence/performance/c1/bench_main_r1.json` | stale (hash mismatch by design) | `manifest_verifies` | per_leg/summary/pairs/missing/legs gates (raw leg becomes unparseable) |
| N02 | `round3/audit/SHA256SUMS` deleted | absent | `manifest_exists` | — (fail-closed) |
| N03 | `round3/audit/SHA256SUMS` truncated to 0 bytes | empty | `manifest_exists` | — (fail-closed) |
| N04 | entry `000…0  ../../etc/passwd` appended | poisoned | `manifest_no_escape_paths` | `manifest_verifies`, `manifest_paths_exist` |
| N05 | duplicate line for `results/gate_matrix.json` | verifies OK; dup present | `manifest_no_duplicates` | **none** — proves integrity still passes and only the dup gate fires |
| N06 | required leg `c1/bench_new_r10.json` deleted; its line removed from the manifest | re-sealed → verifies OK | `leg_completeness` (9/10) | per_leg bijection, order coverage, summary counts, pairs, missing_legs, arm totals |
| N07 | certificate flips `deterministic_serving_retry` BLOCKED→PASS (reason dropped); `verdicts.json` untouched; cert re-hashed | re-sealed → verifies OK | `certificate_matches_verdicts` | `declared_counts_match`, `pass_not_contradicted_by_raw_verdicts` (raw `determinism_r3/verdicts.jsonl` = `BLOCKED_LDS_LIMIT`) |
| N08 | `gpu_properties.json` core count 48→96, threshold→38; re-hashed | re-sealed → verifies OK | `env_core_count_is_48` | `torch_mpc_equals_sglang_num_sms`, `matrix_*`, `new_b4_keep`, `gate_consistency` |
| N09 | `performance_summary.csv` c1/new `thr_median` ×2; re-hashed | re-sealed → verifies OK | `summary_medians_recompute` | **none besides the wrapper** — proves the independent recompute (not the hash) catches the forged statistic |
| N10 | second hunk (2 lines) appended to `evidence/source/old_vs_new.diff`; re-hashed | re-sealed → verifies OK | `old_new_diff_single_line` | `old_new_diff_single_hunk` |

Semantic tests (N06–N10) deliberately re-seal the in-copy manifest so the SHA256
integrity gates PASS: this proves the corresponding **semantic** gate — not a stale
hash — is what rejects the forged evidence.

## Framework unit tests (`round3/scripts/test_audit_framework.py`)

| scenario | property under test | expected outcome |
|---|---|---|
| S1 | Clean Control broken (gate_matrix removed + unlisted) | `FAIL:clean_control_failed`; a negative PASS is never reported |
| S2 | corruption function changes nothing | `FAIL:injection_failed` |
| S3 | real corruption, wrong expected gate (`manifest_verifies` for N05) | `FAIL:target_gate_not_hit` — non-target gates cannot substitute |
| S4 | undetectable doc append, manifest re-hashed, audit accepts | `FAIL:audit_accepted` |
| S5 | certificate BLOCKED→PASS vs verdicts.json BLOCKED (module-level fixture) | `audit_status_integrity.py` exit≠0 with `FAIL certificate_matches_verdicts` + `FAIL pass_not_contradicted_by_raw_verdicts` |
| S6 | manifest deleted / file hash wrong (snapshot-level) | `FAIL manifest_exists` / `FAIL manifest_verifies`, exit≠0 |
