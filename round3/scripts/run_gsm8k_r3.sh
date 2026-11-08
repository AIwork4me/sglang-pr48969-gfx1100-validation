#!/usr/bin/env bash
# Round 3 GSM8K A/B (Main vs New gate) via sgl-eval 0.1.3 (own venv).
# Primary config matches the historical gsm8k_A_full run: Qwen3-0.6B,
# mem-fraction 0.30, auto max-total-tokens, eval max_tokens 1024, temp 0,
# seed 0, 64 threads, full 1319-question test split.
# Usage: run_gsm8k_r3.sh <tag> [num_examples] [eval_max_tokens]
set -euo pipefail
TAG="${1:-gsm8k_r3_full}"; NEX="${2:-1319}"; EVAL_MAX_TOKENS="${3:-1024}"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
MODEL="$WORK/dl/qwen3-06b"
PORT=31000
OUT="$CAMP/round3/evidence/accuracy/${TAG}"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/runner.log") 2>&1
echo "=== round3 gsm8k A/B n=$NEX eval_max_tokens=$EVAL_MAX_TOKENS start $(date -Is) ==="

SRV_PGID=""
stop() { [ -n "$SRV_PGID" ] && { kill -- -"$SRV_PGID" 2>/dev/null || true; sleep 8; kill -9 -- -"$SRV_PGID" 2>/dev/null || true; SRV_PGID=""; } }
trap stop EXIT

for ARM in main new; do
  echo "--- arm=$ARM $(date -Is)"
  setsid bash "$CAMP/round3/scripts/launch_server_r3.sh" "$ARM" "$MODEL" "$PORT" 0.30 0 plain \
    > "$OUT/server_${ARM}.log" 2>&1 < /dev/null &
  SRV_PGID=$!
  for i in $(seq 1 180); do
    sleep 5
    curl -s --max-time 3 http://127.0.0.1:$PORT/health >/dev/null 2>&1 && break
    kill -0 "$SRV_PGID" 2>/dev/null || { echo "SERVER DIED arm=$ARM"; tail -30 "$OUT/server_${ARM}.log"; exit 2; }
    [ $i -eq 180 ] && { echo "timeout"; exit 2; }
  done
  curl -s --max-time 120 http://127.0.0.1:$PORT/generate -H 'Content-Type: application/json' \
    -d '{"text":"1+1=","sampling_params":{"max_new_tokens":8,"temperature":0}}' >/dev/null || true
  echo "--- sgl-eval arm=$ARM n=$NEX $(date -Is)"
  ( source "$WORK/venv_eval/bin/activate"
    export HF_HOME=/workspace/.cache/huggingface
    export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
    export HF_DATASETS_ENDPOINT="${HF_DATASETS_ENDPOINT:-https://hf-mirror.com}"
    sgl-eval run gsm8k \
      --base-url "http://127.0.0.1:$PORT/v1" \
      --model "$MODEL" \
      --num-examples "$NEX" \
      --num-threads 64 \
      --max-tokens "$EVAL_MAX_TOKENS" \
      --temperature 0 \
      --seed 0 \
      --out-dir "$OUT/run_${ARM}" ) > "$OUT/sgl_eval_${ARM}.log" 2>&1 || {
        echo "sgl-eval FAILED arm=$ARM"; tail -20 "$OUT/sgl_eval_${ARM}.log" || true; exit 3; }
  ls "$OUT/run_${ARM}"/sgl_eval_gsm8k_*/metrics.json >/dev/null 2>&1 || { echo "metrics.json missing arm=$ARM"; exit 5; }
  stop
done
trap - EXIT
python3 "$CAMP/round3/scripts/gsm8k_paired_stats.py" "$OUT" || true
echo "=== round3 gsm8k A/B $TAG done $(date -Is) ==="
