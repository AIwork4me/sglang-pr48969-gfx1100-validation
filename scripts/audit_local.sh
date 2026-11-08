#!/usr/bin/env bash
# CPU-only local audit entry point (tier T3 in REPRODUCE.md).
# Runs from a clean clone; no GPU, no network, no benchmark execution.
# Fail-closed: any non-zero sub-check fails the audit.
#
# Usage: bash scripts/audit_local.sh [logfile]
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${1:-$REPO/audit/audit_local.log}"
mkdir -p "$(dirname "$LOG")"

FAILED=0
step() { echo -e "\n=== [$(date -u +%H:%M:%S)] $* ===" | tee -a "$LOG"; }
run() { # name, command...
  local NAME="$1"; shift
  step "$NAME: $*"
  "$@" >>"$LOG" 2>&1
  local RC=$?
  if [ $RC -ne 0 ]; then
    echo "FAIL ($RC) — $NAME (log: $LOG)" | tee -a "$LOG"
    FAILED=1
  else
    echo "PASS — $NAME" | tee -a "$LOG"
  fi
}

: > "$LOG"
step "CPU-only audit of $REPO (no GPU work is performed by this script)"

# 1. Python syntax checks
PY_ERR=0
for f in "$REPO"/scripts/*.py; do
  python3 -m py_compile "$f" >>"$LOG" 2>&1 || { echo "py_compile FAIL: $f" | tee -a "$LOG"; PY_ERR=1; }
done
[ $PY_ERR -eq 0 ] && { echo "PASS — python syntax (scripts/*.py)" | tee -a "$LOG"; } || FAILED=1

# 2. Shell syntax checks
SH_ERR=0
for f in "$REPO"/scripts/*.sh; do
  bash -n "$f" >>"$LOG" 2>&1 || { echo "bash -n FAIL: $f" | tee -a "$LOG"; SH_ERR=1; }
done
[ $SH_ERR -eq 0 ] && { echo "PASS — shell syntax (scripts/*.sh)" | tee -a "$LOG"; } || FAILED=1

# 3. Reproduction-path contract
run "reproduction paths" python3 "$REPO/scripts/verify_reproduction_paths.py"

# 4. Independent evidence audit V2 (fail-closed; writes EVIDENCE_AUDIT_V2.{md,json})
run "evidence audit v2" python3 "$REPO/scripts/verify_evidence_v2.py"

# 5. Auditor regression tests (pure CPU, fixture-based tamper tests).
#    basetemp is kept inside the repo so a full system /tmp is reported as an
#    environment error by the OS, not silently breaking the audit; ambient
#    site-level pytest plugins (shard/xdist) are disabled to keep the run
#    deterministic and isolated from host configuration.
run "auditor regression tests" python3 -m pytest "$REPO/tests" -q \
    --basetemp="$REPO/audit/.pytest_tmp" -p no:shard -p no:xdist -p no:cacheprovider

# 6. Sealed-manifest verification of raw evidence.
#    Files repaired in this round (tooling/config/docs, listed in
#    audit/SHA256SUMS_AUDIT_ROUND) are expected to mismatch the historical
#    seal; anything else failing means raw evidence changed.
step "sealed manifest (evidence/checksums/SHA256SUMS)"
EXPECTED_MISMATCH=$(awk '{print $2}' "$REPO/audit/SHA256SUMS_AUDIT_ROUND" 2>/dev/null | sort -u || true)
BAD=0; TOTAL=0; MISMATCHED=""
while read -r HASH PATH2; do
  [ -f "$REPO/$PATH2" ] || { MISMATCHED="$MISMATCHED$PATH2 (missing)\n"; BAD=1; TOTAL=$((TOTAL+1)); continue; }
  TOTAL=$((TOTAL+1))
  ACTUAL=$(sha256sum "$REPO/$PATH2" | awk '{print $1}')
  if [ "$ACTUAL" != "$HASH" ]; then
    if echo "$EXPECTED_MISMATCH" | grep -qxF "$PATH2"; then
      :  # documented, legitimately repaired this round
    else
      MISMATCHED="$MISMATCHED$PATH2 (changed)\n"; BAD=1
    fi
  fi
done < "$REPO/evidence/checksums/SHA256SUMS"
if [ $BAD -eq 0 ]; then
  echo "PASS — sealed manifest: $TOTAL files verified (repaired-this-round files accounted for)" | tee -a "$LOG"
else
  echo -e "FAIL — sealed manifest mismatches:\n$MISMATCHED" | tee -a "$LOG"; FAILED=1
fi

# 7. Accuracy summary recompute (independent of analyze.py)
run "accuracy recompute" python3 "$REPO/scripts/recompute_accuracy.py"

# 8. Performance summary recompute (independent of analyze.py)
run "performance recompute" python3 "$REPO/scripts/recompute_performance.py"

echo
if [ $FAILED -eq 0 ]; then
  echo "AUDIT LOCAL: PASS (details: $LOG)" | tee -a "$LOG"
  exit 0
else
  echo "AUDIT LOCAL: FAIL (details: $LOG)" | tee -a "$LOG"
  exit 1
fi
