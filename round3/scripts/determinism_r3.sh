#!/usr/bin/env bash
# Round 3 deterministic-serving retry (Phase 3.4). Historical result: BLOCKED on
# both arms (LDS 99,328B required vs 65,536B hardware limit at startup). This
# retries on the new stack with fresh provenance; failure classification is
# recorded per arm. One GPU launch per arm; runs ONLY when the GPU is otherwise
# free (invoke manually, never alongside the serving grid).
# Usage: determinism_r3.sh <arm>   (main | old | new)
set -uo pipefail
ARM="${1:?arm required}"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
MODEL="$WORK/dl/qwen3-06b"
OUT="$CAMP/round3/evidence/accuracy/determinism_r3"
mkdir -p "$OUT"
LOG="$OUT/server_${ARM}.log"
echo "=== determinism_r3 arm=$ARM start $(date -Is) ===" | tee -a "$OUT/record.log"

source "$WORK/venv_$ARM/bin/activate"
export SGLANG_DISABLE_LEAN_ATTENTION=1 SGLANG_USE_AITER=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HUB_OFFLINE=1
setsid python -m sglang.launch_server \
  --model-path "$MODEL" --attention-backend triton --context-length 10240 \
  --mem-fraction-static 0.75 --enable-deterministic-inference \
  --host 127.0.0.1 --port 31098 > "$LOG" 2>&1 < /dev/null &
PGID=$!
VERDICT=NOT_RUN
for i in $(seq 1 120); do
  sleep 5
  curl -s --max-time 3 http://127.0.0.1:31098/health >/dev/null 2>&1 && { VERDICT=STARTED; break; }
  kill -0 $PGID 2>/dev/null || break
  [ $i -eq 120 ] && VERDICT=TIMEOUT
done
if [ "$VERDICT" = "STARTED" ]; then
  # basic determinism probe: two identical greedy generations must match
  A=$(curl -s --max-time 300 http://127.0.0.1:31098/generate -H 'Content-Type: application/json' \
    -d '{"text":"The capital of France is","sampling_params":{"max_new_tokens":32,"temperature":0}}')
  B=$(curl -s --max-time 300 http://127.0.0.1:31098/generate -H 'Content-Type: application/json' \
    -d '{"text":"The capital of France is","sampling_params":{"max_new_tokens":32,"temperature":0}}')
  echo "$A" > "$OUT/probe_${ARM}_a.json"; echo "$B" > "$OUT/probe_${ARM}_b.json"
  python3 -c "
import json,sys
a=json.load(open('$OUT/probe_${ARM}_a.json')); b=json.load(open('$OUT/probe_${ARM}_b.json'))
same = a.get('text')==b.get('text')
print('determinism probe identical:', same)
sys.exit(0 if same else 1)" && VERDICT=PASS || VERDICT=FAIL
fi
kill -- -$PGID 2>/dev/null || true; sleep 5; kill -9 -- -$PGID 2>/dev/null || true
# classify startup failure from the log
if [ "$VERDICT" != "PASS" ] && [ "$VERDICT" != "FAIL" ]; then
  if grep -q "LDS\|shared memory\|OutOfResources\|99328\|65536" "$LOG" 2>/dev/null; then
    VERDICT="BLOCKED_LDS_LIMIT"
  elif grep -qi "triton.compile\|CompilationError" "$LOG" 2>/dev/null; then
    VERDICT="BLOCKED_COMPILE"
  else
    VERDICT="BLOCKED_OTHER"
  fi
fi
echo "{\"arm\": \"$ARM\", \"verdict\": \"$VERDICT\", \"utc\": \"$(date -u --iso-8601=seconds)\", \"log\": \"server_${ARM}.log\"}" >> "$OUT/verdicts.jsonl"
echo "=== determinism_r3 arm=$ARM verdict=$VERDICT ===" | tee -a "$OUT/record.log"
