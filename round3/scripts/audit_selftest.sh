#!/usr/bin/env bash
# Negative self-tests for the round3 audit (round3.1 hardened framework).
#
# Every test runs against a FULL, DISPOSABLE snapshot of the committed HEAD
# (git archive — never the real tree), proves its Clean Control passes,
# then applies one verified corruption and requires the audit to reject the
# copy WITH THE EXPECTED GATE FAILING. See negtest_lib.sh for the protocol.
#
# A negative test passes only when the intended corruption was actually
# applied and the expected audit gate correctly detected it.
#
# Usage: bash round3/scripts/audit_selftest.sh
# Env:   NEGTEST_LOGDIR / NEGTEST_RESULTS_JSON (optional archives),
#        NEGTEST_TMPROOT / TMPDIR (temp placement; needs ~200 MB per test).
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SRC/negtest_lib.sh"
# shellcheck source=negtest_lib.sh
source "$LIB"
trap negtest_cleanup EXIT

echo "== round3 negative self-test (hardened, r3.1) =="
echo "source repo : $NEGTEST_SRC"
echo "temp root   : $NEGTEST_TMPROOT"
echo "fixture     : full git archive of HEAD (complete audit dependencies)"

# ---------------------------------------------------------------------------
# Global Clean Control (P0-B): an untampered snapshot MUST pass the audit
# before any negative test is allowed to claim anything.
# ---------------------------------------------------------------------------
CC_ROOT="$NEGTEST_TMPROOT/_clean_control"
CC_LOG="$NEGTEST_TMPROOT/_clean_control.audit.log"
rm -rf "$CC_ROOT"; mkdir -p "$CC_ROOT"
if ! negtest_fresh_repo "$CC_ROOT"; then
  echo "CLEAN CONTROL: FAILED to create snapshot"
  echo "SELFTEST NO-GO: no negative verdicts will be issued"
  exit 1
fi
if ! negtest_run_audit "$CC_ROOT" "$CC_LOG"; then
  echo "CLEAN CONTROL: AUDIT FAILED on the untampered snapshot:"
  grep '^FAIL' "$CC_LOG" | head -10
  echo "SELFTEST NO-GO: fix the fixture/environment first; no negative test"
  echo "may be reported as PASS while the clean control fails."
  if [ -n "$NEGTEST_LOGDIR" ]; then
    mkdir -p "$NEGTEST_LOGDIR"
    cp -f "$CC_LOG" "$NEGTEST_LOGDIR/clean_control.audit.log" 2>/dev/null || true
  fi
  exit 1
fi
echo "CLEAN CONTROL: PASS ($(grep -c '^PASS' "$CC_LOG") checks) — negative tests are GO"
if [ -n "$NEGTEST_LOGDIR" ]; then
  mkdir -p "$NEGTEST_LOGDIR"
  cp -f "$CC_LOG" "$NEGTEST_LOGDIR/clean_control.audit.log" 2>/dev/null || true
fi
rm -rf "$CC_ROOT"

# ---------------------------------------------------------------------------
# N01–N10: id | description | expected gate | declared targets | corruption fn
# ---------------------------------------------------------------------------
MAN="round3/audit/SHA256SUMS"

negtest N01 "one byte appended to a raw benchmark JSON (integrity, stale manifest)" \
  manifest_verifies \
  "round3/evidence/performance/c1/bench_main_r1.json" \
  corrupt_N01

negtest N02 "SHA256 manifest deleted (fail-closed)" \
  manifest_exists \
  "$MAN" \
  corrupt_N02

negtest N03 "SHA256 manifest truncated to zero bytes (fail-closed)" \
  manifest_exists \
  "$MAN" \
  corrupt_N03

negtest N04 "manifest entry escaping the repository root" \
  manifest_no_escape_paths \
  "$MAN" \
  corrupt_N04

negtest N05 "duplicate manifest record (integrity must still verify, only the dup gate may fire)" \
  manifest_no_duplicates \
  "$MAN" \
  corrupt_N05

negtest N06 "required benchmark leg deleted, manifest re-sealed -> completeness gate must find it" \
  leg_completeness \
  "round3/evidence/performance/c1/bench_new_r10.json $MAN" \
  corrupt_N06

negtest N07 "BLOCKED test forged to PASS in the certificate (verdicts untouched, manifest re-sealed)" \
  certificate_matches_verdicts \
  "round3/audit/VALIDATION_CERTIFICATE.json $MAN" \
  corrupt_N07

negtest N08 "W7900 core count forged 48->96 (gate consistency, manifest re-sealed)" \
  env_core_count_is_48 \
  "round3/evidence/environment/gpu_properties.json $MAN" \
  corrupt_N08

negtest N09 "throughput statistics inflated +100% (independent recompute, manifest re-sealed)" \
  summary_medians_recompute \
  "round3/results/performance_summary.csv $MAN" \
  corrupt_N09

negtest N10 "second modification added to the old/new source diff (manifest re-sealed)" \
  old_new_diff_single_line \
  "round3/evidence/source/old_vs_new.diff $MAN" \
  corrupt_N10

# ---------------------------------------------------------------------------
negtest_write_results_json
echo "== negative self-test summary: $NEGTEST_SUMMARY_PASSED/$NEGTEST_SUMMARY_TOTAL PASS =="
if [ "$NEGTEST_SUMMARY_PASSED" -eq "$NEGTEST_SUMMARY_TOTAL" ] \
   && [ "$NEGTEST_SUMMARY_TOTAL" -eq 10 ]; then
  echo "SELFTEST PASS (10/10, each with verified injection + expected-gate rejection)"
  exit 0
fi
echo "SELFTEST FAIL"
exit 1
