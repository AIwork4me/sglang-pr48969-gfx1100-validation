#!/usr/bin/env bash
# Phase 4/5 serving A/B benchmark runner.
# Usage: run_serving_ab.sh <model_key> <concurrency> <input_len> <output_len> <range_ratio> <memfrac> <run_tag>
# Executes one ABBA cycle: main -> pr -> pr -> main; each server start gets a
# warmup bench before the measured bench. Saves bench JSON, client log, server
# log, GPU telemetry per leg.
set -euo pipefail
MODEL_KEY="$1"; CONC="$2"; IL="$3"; OL="$4"; RR="$5"; MEMFRAC="$6"; TAG="$7"; MAXTOK="${8:-0}"
CAMP=/root/sglang-pr48969-validation
PORT=31000
OUT="$CAMP/evidence/performance/${TAG}"
mkdir -p "$OUT"
LOG="$OUT/runner.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== serving A/B $MODEL_KEY conc=$CONC il=$IL ol=$OL rr=$RR memfrac=$MEMFRAC start $(date -Is) ==="

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
  ( source "$CAMP/work/venv_$ARM/bin/activate"
    python -m sglang.benchmark.serving \
      --backend sglang \
      --host 127.0.0.1 --port $PORT \
      --dataset-name random \
      --random-input-len "$IL" --random-output-len "$OL" \
      --random-range-ratio "$RR" \
      --num-prompts "$N" --max-concurrency "$CONC" \
      --seed 1 --output-file "$BS" ) > "$BL" 2>&1 || echo "bench rc=$? (logged)"
  [ -f "$BS" ] || { echo "MISSING bench output $BS"; return 1; }
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
run_arm() { # arm
  local ARM="$1"
  echo "=== launch arm=$ARM $(date -Is)"
  setsid bash "$CAMP/work/launch_server.sh" "$ARM" "$MODEL" "$PORT" "$MEMFRAC" "$MAXTOK" \
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

stop_server() {
  [ -n "$SRV_PGID" ] && kill -- -"$SRV_PGID" 2>/dev/null || true
  sleep 8
  [ -n "$SRV_PGID" ] && kill -9 -- -"$SRV_PGID" 2>/dev/null || true
  sleep 4
  SRV_PGID=""
}

for SEQ in "main 1" "pr 1" "pr 2" "main 2"; do
  set -- $SEQ; ARM=$1; RUNNO=$2
  if ! run_arm "$ARM"; then echo "ABORT at $ARM"; stop_server; exit 3; fi
  bench "$ARM" "$RUNNO" warmup || true
  telemetry_bg "$OUT/telemetry_${ARM}_r${RUNNO}.csv" "$OUT/tele_pid"
  TELE_PID=$(cat "$OUT/tele_pid" 2>/dev/null || echo "")
  bench "$ARM" "$RUNNO" ""
  [ -n "$TELE_PID" ] && kill "$TELE_PID" 2>/dev/null || true
  cp "$OUT/server_${ARM}.log" "$OUT/server_${ARM}_r${RUNNO}.log"
  stop_server
done
echo "=== serving A/B $TAG done $(date -Is) ==="
