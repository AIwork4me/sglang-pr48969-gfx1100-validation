#!/usr/bin/env bash
# Round 3 serving leg runner: one leg = fresh server start + readiness check +
# warmup bench + measured bench + telemetry + clean shutdown.
# Usage: run_leg.sh <cell_dir> <arm> <runno> <conc> <il> <ol> <rr> <memfrac> <maxtok> <num_prompts> <mode: plain|spy>
set -euo pipefail
CELL="$1"; ARM="$2"; RUNNO="$3"; CONC="$4"; IL="$5"; OL="$6"; RR="$7"; MEMFRAC="$8"; MAXTOK="$9"; NP="${10}"; MODE="${11:-plain}"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
MODEL="$WORK/dl/qwen3-06b"
LAUNCH="$CAMP/round3/scripts/launch_server_r3.sh"
PORT=31000
mkdir -p "$CELL"
SFX="${ARM}_r${RUNNO}"
BENCH="$CELL/bench_${SFX}.json"
LOG="$CELL/bench_${SFX}.log"
SRVLOG="$CELL/server_${SFX}.log"

bench() { # n_prompts out_json out_log
  local N="$1" BS="$2" BL="$3"
  ( source "$WORK/venv_$ARM/bin/activate"
    python -m sglang.benchmark.serving \
      --backend sglang \
      --host 127.0.0.1 --port $PORT \
      --dataset-name random \
      --random-input-len "$IL" --random-output-len "$OL" \
      --random-range-ratio "$RR" \
      --num-prompts "$N" --max-concurrency "$CONC" \
      --seed 1 --output-file "$BS" ) > "$BL" 2>&1
  [ -f "$BS" ] || { echo "MISSING bench output $BS"; return 1; }
}

SRV_PGID=""
stop_server() {
  [ -n "$SRV_PGID" ] && kill -- -"$SRV_PGID" 2>/dev/null || true
  sleep 8
  [ -n "$SRV_PGID" ] && kill -9 -- -"$SRV_PGID" 2>/dev/null || true
  sleep 4
  SRV_PGID=""
}
trap stop_server EXIT

echo "=== leg $SFX start $(date -Is) mode=$MODE ==="
setsid bash "$LAUNCH" "$ARM" "$MODEL" "$PORT" "$MEMFRAC" "$MAXTOK" "$MODE" \
  > "$SRVLOG" 2>&1 < /dev/null &
SRV_PGID=$!
for i in $(seq 1 180); do
  sleep 5
  if curl -s --max-time 3 http://127.0.0.1:$PORT/health >/dev/null 2>&1; then
    echo "server up arm=$ARM after $((i*5))s"; break
  fi
  if ! kill -0 "$SRV_PGID" 2>/dev/null; then
    echo "SERVER DIED arm=$ARM"; tail -40 "$SRVLOG"; exit 2
  fi
  [ "$i" = "180" ] && { echo "server start timeout arm=$ARM"; exit 2; }
done

WARMUP=$((CONC < 8 ? CONC : 8))
[ "$NP" -gt 32 ] && WARMUP=8
bench "$WARMUP" "$CELL/bench_${SFX}_warmup.json" "$CELL/bench_${SFX}_warmup.log" \
  || { echo "WARMUP FAILED $SFX"; exit 4; }

( : > "$CELL/telemetry_${SFX}.csv"
  while :; do
    { date -Is; rocm-smi --showpower --showtemp --showclocks --showuse --csv 2>/dev/null; } >> "$CELL/telemetry_${SFX}.csv" || true
    sleep 5
  done ) &
TELE=$!
bench "$NP" "$BENCH" "$LOG" || { kill $TELE 2>/dev/null || true; echo "MEASURED BENCH FAILED $SFX"; exit 5; }
kill $TELE 2>/dev/null || true
stop_server
trap - EXIT
echo "=== leg $SFX done $(date -Is) ==="
