#!/usr/bin/env bash
# GSM8K A/B via sgl-eval (separate venv) per the repo's .claude/rules/prefer-sgl-eval.md
# policy at the tested revision.
#
# Usage: run_gsm8k_ab.sh <model_key> <memfrac> <tag> [num_examples] [server_max_total_tokens] [eval_max_tokens]
#   model_key: A | B | C
#   num_examples: 200 | 1319           (default 200)
#   server_max_total_tokens: 0 = auto  (e.g. 100000 for A, 260000 for B)
#   eval_max_tokens: REQUIRED for a faithful rerun — 1024 or 2048.
#     This is the sgl-eval --max-tokens value. It is a historical run parameter
#     (A runs used 1024; A_full_2048 and all B runs used 2048 — see
#     evidence/accuracy/EXECUTION_MANIFEST.md). The value must be passed
#     explicitly so it can never be silently hidden again. The pre-audit
#     version of this script hardcoded 2048 and therefore could NOT reproduce
#     the archived gsm8k_A_diag / gsm8k_A_full runs; that gap is documented in
#     evidence/accuracy/EXECUTION_MANIFEST.md.
#
# Fail-closed policy (audit round 2026-11): every command's exit status is
# checked; a failed sgl-eval aborts the run with a non-zero exit. (The
# historical version logged "sgl-eval rc=... (logged)" and continued.)
set -euo pipefail
MODEL_KEY="$1"; MEMFRAC="$2"; TAG="$3"; NEX="${4:-200}"; MAXTOK="${5:-0}"
EVAL_MAX_TOKENS="${6:-${SGLANG_EVAL_MAX_TOKENS:-}}"
if [ -z "$EVAL_MAX_TOKENS" ]; then
  echo "ERROR: eval_max_tokens (arg 6 or SGLANG_EVAL_MAX_TOKENS) is required." >&2
  echo "       Historical values: gsm8k_A_diag/A_full=1024, gsm8k_A_full_2048=2048," >&2
  echo "       gsm8k_B_diag/B_full=2048 (see evidence/accuracy/EXECUTION_MANIFEST.md)." >&2
  exit 64
fi
# Repository root: default = parent of this script's directory; override for the
# historical layout via SGLANG_VALIDATION_ROOT=/root/sglang-pr48969-validation.
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-$CAMP/work}"
# Launcher: committed copy preferred; historical work/ copy used if that is all
# that exists (byte-identity between the two was never proven — see
# audit/BASELINE_INVENTORY.md §6).
LAUNCH_SERVER="${SGLANG_VALIDATION_LAUNCH_SERVER:-}"
if [ -z "$LAUNCH_SERVER" ]; then
  if [ -f "$CAMP/scripts/launch_server.sh" ]; then LAUNCH_SERVER="$CAMP/scripts/launch_server.sh";
  elif [ -f "$WORK/launch_server.sh" ]; then LAUNCH_SERVER="$WORK/launch_server.sh";
  else echo "ERROR: no launch_server.sh found (scripts/ or work/)"; exit 64; fi
fi
PORT=31000
OUT="$CAMP/evidence/accuracy/${TAG}"
mkdir -p "$OUT"
LOG="$OUT/runner.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== gsm8k A/B $MODEL_KEY n=$NEX eval_max_tokens=$EVAL_MAX_TOKENS start $(date -Is) ==="

case "$MODEL_KEY" in
  A) MODEL=Qwen/Qwen3-0.6B ;;
  B) MODEL=Qwen/Qwen2.5-3B-Instruct ;;
  C) MODEL=Qwen/Qwen3-8B ;;
  *) echo "unknown model key"; exit 1 ;;
esac

SRV_PGID=""
cleanup() {
  [ -n "$SRV_PGID" ] && { kill -- -"$SRV_PGID" 2>/dev/null || true; sleep 8; kill -9 -- -"$SRV_PGID" 2>/dev/null || true; }
}
trap cleanup EXIT

for ARM in main pr; do
  echo "--- launch arm=$ARM $(date -Is)"
  setsid bash "$LAUNCH_SERVER" "$ARM" "$MODEL" "$PORT" "$MEMFRAC" "$MAXTOK" \
    > "$OUT/server_${ARM}.log" 2>&1 < /dev/null &
  SRV_PGID=$!
  UP=0
  for i in $(seq 1 150); do
    sleep 5
    if curl -s --max-time 3 http://127.0.0.1:$PORT/health >/dev/null 2>&1; then UP=1; break; fi
    kill -0 "$SRV_PGID" 2>/dev/null || { echo "SERVER DIED arm=$ARM"; tail -30 "$OUT/server_${ARM}.log"; exit 2; }
    [ $i -eq 150 ] && { echo "timeout"; exit 2; }
  done
  [ "$UP" = 1 ] || { echo "server never became healthy arm=$ARM"; exit 2; }
  # warm the server (best effort; warmup failure is not fatal)
  curl -s --max-time 120 http://127.0.0.1:$PORT/generate -H 'Content-Type: application/json' \
    -d '{"text":"1+1=","sampling_params":{"max_new_tokens":8,"temperature":0}}' >/dev/null || true
  echo "--- sgl-eval arm=$ARM n=$NEX max_tokens=$EVAL_MAX_TOKENS $(date -Is)"
  set +e
  ( source "$WORK/venv_eval/bin/activate"
    export HF_HOME="${HF_HOME:-/workspace/.cache/huggingface}"
    sgl-eval run gsm8k \
      --base-url "http://127.0.0.1:$PORT/v1" \
      --model "$MODEL" \
      --num-examples "$NEX" \
      --num-threads 64 \
      --max-tokens "$EVAL_MAX_TOKENS" \
      --temperature 0 \
      --seed 0 \
      --out-dir "$OUT/run_${ARM}" ) > "$OUT/sgl_eval_${ARM}.log" 2>&1
  RC=$?
  set -e
  if [ "$RC" -ne 0 ]; then
    echo "sgl-eval FAILED arm=$ARM rc=$RC (see $OUT/sgl_eval_${ARM}.log); aborting — this cell is NOT complete"
    tail -20 "$OUT/sgl_eval_${ARM}.log" || true
    exit "$RC"
  fi
  # the metrics file must exist for this arm, else fail closed
  ls "$OUT/run_${ARM}"/sgl_eval_gsm8k_*/metrics.json >/dev/null 2>&1 || {
    echo "metrics.json missing for arm=$ARM despite rc=0"; exit 5; }
  kill -- -"$SRV_PGID" 2>/dev/null || true
  sleep 8
  kill -9 -- -"$SRV_PGID" 2>/dev/null || true
  sleep 4
  SRV_PGID=""
done
trap - EXIT
echo "=== gsm8k A/B $TAG done $(date -Is) ==="
