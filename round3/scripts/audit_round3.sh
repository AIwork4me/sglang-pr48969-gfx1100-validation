#!/usr/bin/env bash
# Round 3 independent audit — CPU-ONLY, works from a fresh GitHub clone.
# Verifies evidence integrity, source provenance, gate decisions, performance
# recomputation, and configuration symmetry. Exits nonzero on any mandatory
# failure. Negative tests against disposable copies: audit_round3.sh --selftest
set -euo pipefail
CAMP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
R3="$CAMP/round3"
FAIL=0
declare -a FAILS

ck() { # name, condition-as-command
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS $name"; else echo "FAIL $name"; FAIL=1; FAILS+=("$name"); fi
}

echo "== round3 audit: $(date -u --iso-8601=seconds) =="

# --- 1. SHA256 manifest verification (fail-closed) ---
ck "manifest_exists" test -s "$R3/audit/SHA256SUMS"
if [ -s "$R3/audit/SHA256SUMS" ]; then
  (cd "$CAMP" && sha256sum -c "$R3/audit/SHA256SUMS" --quiet) && echo "PASS manifest_verifies" || { echo "FAIL manifest_verifies"; FAIL=1; FAILS+=(manifest_verifies); }
  # reject path escape / duplicates
  ESC=$(grep -cE '(\.\.|^\s*/|//)' "$R3/audit/SHA256SUMS" || true)
  ck "manifest_no_escape_paths" test "$ESC" = "0"
  DUP=$(awk '{print $2}' "$R3/audit/SHA256SUMS" | sort | uniq -d | wc -l)
  ck "manifest_no_duplicates" test "$DUP" = "0"
  MISS=$(awk '{print $2}' "$R3/audit/SHA256SUMS" | while read -r f; do [ -e "$CAMP/$f" ] || echo "$f"; done | wc -l)
  ck "manifest_paths_exist" test "$MISS" = "0"
fi

# --- 2. historical evidence untouched ---
if [ -s "$R3/audit/baseline_freeze.sha256" ]; then
  BAD=0
  while read -r h f; do
    [ -f "$CAMP/$f" ] || { BAD=1; echo "  baseline file missing: $f"; continue; }
    CUR=$(sha256sum "$CAMP/$f" | awk '{print $1}')
    [ "$CUR" = "$h" ] || { BAD=1; echo "  baseline file modified: $f"; }
  done < "$R3/audit/baseline_freeze.sha256"
  ck "historical_evidence_unmodified" test "$BAD" = "0"
fi

# --- 3. gate decisions consistent with measured core count + threshold ---
python3 "$R3/scripts/audit_gate.py" || { echo "FAIL gate_consistency"; FAIL=1; FAILS+=(gate_consistency); }
ck "gate_matrix_exists" test -s "$R3/results/gate_matrix.json"

# --- 4. performance recompute: every published summary number re-derived ---
python3 "$R3/scripts/audit_performance.py" || { echo "FAIL performance_recompute"; FAIL=1; FAILS+=(performance_recompute); }

# --- 5. source provenance: commits recorded, single-line old/new diff ---
ck "arm_commits_recorded" test -s "$R3/evidence/source/arm_commits.txt"
grep -q "new_gate_sha  1da9ae2fcba99be22ed756083e1eb505c1cf5afe" "$R3/evidence/source/arm_commits.txt" \
  && echo "PASS new_gate_is_1da9ae2" || { echo "FAIL new_gate_is_1da9ae2"; FAIL=1; FAILS+=(new_gate_is_1da9ae2); }
if [ -s "$R3/evidence/source/old_vs_new.diff" ]; then
  N=$(grep -c '^[<>]' "$R3/evidence/source/old_vs_new.diff" || true)
  ck "old_new_diff_single_line" test "$N" = "2"
  H=$(grep -cE '^[0-9]+(,[0-9]+)?[acd][0-9]+' "$R3/evidence/source/old_vs_new.diff" || true)
  ck "old_new_diff_single_hunk" test "$H" = "1"
fi

# --- 6. server configuration symmetry: all launch commands identical except arm ---
python3 "$R3/scripts/audit_server_symmetry.py" || { echo "FAIL server_symmetry"; FAIL=1; FAILS+=(server_symmetry); }

# --- 7. status integrity: no PASS for tests marked BLOCKED/NOT_RUN ---
python3 "$R3/scripts/audit_status_integrity.py" || { echo "FAIL status_integrity"; FAIL=1; FAILS+=(status_integrity); }

# --- 8. secrets scan (tokens/keys) ---
python3 "$R3/scripts/audit_secrets.py" || { echo "FAIL secrets_scan"; FAIL=1; FAILS+=(secrets_scan); }

# --- 9. benchmark legs present per REQUIRED_LEGS ---
python3 "$R3/scripts/audit_legs.py" || { echo "FAIL leg_completeness"; FAIL=1; FAILS+=(leg_completeness); }

echo "== verdict =="
if [ "$FAIL" = "0" ]; then
  echo "AUDIT PASS"
else
  echo "AUDIT FAIL (${FAILS[*]})"
  exit 1
fi

# --- optional: negative self-tests on disposable copies ---
if [ "${1:-}" = "--selftest" ]; then
  bash "$R3/scripts/audit_selftest.sh" || exit 1
fi
