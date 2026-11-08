#!/usr/bin/env bash
# Serving A/B benchmark runner.
# Usage: run_serving_ab.sh <model_key> <concurrency> <input_len> <output_len> <range_ratio> <memfrac> <run_tag> [server_max_total_tokens]
# Executes one ABBA cycle: main -> pr -> pr -> main; each server start gets a
# warmup bench before the measured bench. Saves bench JSON, client log, server
# log, GPU telemetry per leg.
#
# Fail-closed policy (audit round 2026-11): a failed measured bench aborts the
# cell with a non-zero exit; the historical version only echoed the return
# code and continued. Historical cells were driven by an uncommitted
# work/run_final.sh orchestrator; the per-cell invocations are reconstructible
# from each cell's runner.log first line — see
# evidence/performance/*/runner.log and audit/BASELINE_INVENTORY.md §6.
set -euo pipefail
MODEL_KEY="$1"; CONC="$2"; IL="$3"; OL="$4"; RR="$5"; MEMFRAC="$6"; TAG="$7"; MAXTOK="${8:-0}"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-$CAMP/work}"
LAUNCH_SERVER="${SGLANG_VALIDATION_LAUNCH_SERVER:-}"
if [ -z "$LAUNCH_SERVER" ]; then
  if [ -f "$CAMP/scripts/launch_server.sh" ]; then LAUNCH_SERVER="$CAMP/scripts/launch_server.sh";
  elif [ -f "$WORK/launch_server.sh" ]; then LAUNCH_SERVER="$WORK/launch_server.sh";
  else echo "ERROR: no launch_server.sh found (scripts/ or work/)"; exit 64; fi
fi
PORT=31000
OUT="$CAMP/evidence/performance/${TAG}"
mkdir -p "$OUT"
LOG="$OUT/runner.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== serving A/B $MODEL_KEY conc=$CONC il=$IL ol=$OL rr=$RR memfrac=$MEMFRAC tag=$TAG maxtok=$MAXTOK start $(date -Is) ==="

case "$MODEL_KEY" in
  A) MODEL=Qwen/Qwen3-0.6B ;;
  B) MODEL=Qwen/Qwen2.5-3B-Instruct ;;
  C) MODEL=Qwen/Qwen3-8B ;;
  *) echo "unknown model key"; exit 1 ;;
esac

NUM_PROMPTS="$CONC"

bench() { # arm, runno, is_warmup
  local ARM="$1" RUNNO="$2" WARM="$3"
  local SFX="_r${RUNNO}${WARM:+_warmup}"
  local BS="$OUT/bench_${ARM}${SFX}.json"
  local BL="$OUT/bench_${ARM}${SFX}.log"
  echo "--- bench arm=$ARM$SFX $(date -Is)"
  local N; if [ -n "$WARM" ]; then N=$((CONC < 8 ? CONC : 8)); else N=$NUM_PROMPTS; fi
  set +e
  ( source "$WORK/venv_$ARM/bin/activate"
    python -m sglang.benchmark.serving \
      --backend sglang \
      --host 127.0.0.1 --port $PORT \
      --dataset-name random \
      --random-input-len "$IL" --random-output-len "$OL" \
      --random-range-ratio "$RR" \
      --num-prompts "$N" --max-concurrency "$CONC" \
      --seed 1 --output-file "$BS" ) > "$BL" 2>&1
  local RC=$?
  set -e
  if [ "$RC" -ne 0 ]; then
    echo "bench FAILED arm=$ARM$SFX rc=$RC (see $BL)"
    tail -20 "$BL" || true
    return 1
  fi
  [ -f "$BS" ] || { echo "MISSING bench output $BS (rc was 0)"; return 1; }
  return 0
}

telemetry_bg() { # outfile pidfile
  local OUT2="$1" PIDF="$2"
  ( : > "$OUT2"
    while :; do
      { date -Is; rocm-smi --showpower --showtemp --showclocks --showuse --csv 2>/dev/null; } >> "$OUT2" || true
      sleep 5
    done ) &
  echo $! > "$PIDF"
}

SRV_PGID=""
stop_server() {
  [ -n "$SRV_PGID" ] && kill -- -"$SRV_PGID" 2>/dev/null || true
  sleep 8
  [ -n "$SRV_PGID" ] && kill -9 -- -"$SRV_PGID" 2>/dev/null || true
  sleep 4
  SRV_PGID=""
}
cleanup() { stop_server; }
trap cleanup EXIT

run_arm() { # arm
  local ARM="$1"
  echo "=== launch arm=$ARM $(date -Is)"
  setsid bash "$LAUNCH_SERVER" "$ARM" "$MODEL" "$PORT" "$MEMFRAC" "$MAXTOK" \
    > "$OUT/server_${ARM}.log" 2>&1 < /dev/null &
  SRV_PGID=$!
  for i in $(seq 1 150); do
    sleep 5
    if curl -s --max-time 3 http://127.0.0.1:$PORT/health >/dev/null 2>&1; then
      echo "server up arm=$ARM after $((i*5))s"; return 0
    fi
    if ! kill -0 "$SRV_PGID" 2>/dev/null; then
      echo "SERVER DIED arm=$ARM"; tail -40 "$OUT/server_${ARM}.log"; return 2
    fi
  done
  echo "server start timeout arm=$ARM"; return 2
}

for SEQ in "main 1" "pr 1" "pr 2" "main 2"; do
  set -- $SEQ; ARM=$1; RUNNO=$2
  if ! run_arm "$ARM"; then echo "ABORT at $ARM"; exit 3; fi
  bench "$ARM" "$RUNNO" warmup || { echo "ABORT: warmup bench failed arm=$ARM"; exit 4; }
  telemetry_bg "$OUT/telemetry_${ARM}_r${RUNNO}.csv" "$OUT/tele_pid"
  TELE_PID=$(cat "$OUT/tele_pid" 2>/dev/null || echo "")
  bench "$ARM" "$RUNNO" "" || { echo "ABORT: measured bench failed arm=$ARM r$RUNNO"; exit 5; }
  [ -n "$TELE_PID" ] && kill "$TELE_PID" 2>/dev/null || true
  cp "$OUT/server_${ARM}.log" "$OUT/server_${ARM}_r${RUNNO}.log"
  stop_server
done
trap - EXIT
echo "=== serving A/B $TAG done $(date -Is) ==="
