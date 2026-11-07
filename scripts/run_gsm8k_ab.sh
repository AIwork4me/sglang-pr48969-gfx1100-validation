#!/usr/bin/env bash
# Phase 6 GSM8K A/B via sgl-eval 0.1.3 (separate venv) per the repo's
# .claude/rules/prefer-sgl-eval.md policy.
# Usage: run_gsm8k_ab.sh <model_key> <memfrac> <tag> [num_examples: 200|1319]
set -euo pipefail
MODEL_KEY="$1"; MEMFRAC="$2"; TAG="$3"; NEX="${4:-200}"; MAXTOK="${5:-0}"
CAMP=/root/sglang-pr48969-validation
PORT=31000
OUT="$CAMP/evidence/accuracy/${TAG}"
mkdir -p "$OUT"
LOG="$OUT/runner.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== gsm8k A/B $MODEL_KEY n=$NEX start $(date -Is) ==="

case "$MODEL_KEY" in
  A) MODEL=Qwen/Qwen3-0.6B ;;
  B) MODEL=Qwen/Qwen2.5-3B-Instruct ;;
  C) MODEL=Qwen/Qwen3-8B ;;
  *) echo "unknown model key"; exit 1 ;;
esac

SRV_PGID=""
for ARM in main pr; do
  echo "--- launch arm=$ARM $(date -Is)"
  setsid bash "$CAMP/work/launch_server.sh" "$ARM" "$MODEL" "$PORT" "$MEMFRAC" "$MAXTOK" \
    > "$OUT/server_${ARM}.log" 2>&1 < /dev/null &
  SRV_PGID=$!
  for i in $(seq 1 150); do
    sleep 5
    curl -s --max-time 3 http://127.0.0.1:$PORT/health >/dev/null 2>&1 && break
    kill -0 "$SRV_PGID" 2>/dev/null || { echo "SERVER DIED arm=$ARM"; tail -30 "$OUT/server_${ARM}.log"; exit 2; }
    [ $i -eq 150 ] && { echo "timeout"; exit 2; }
  done
  # warm the server
  curl -s --max-time 120 http://127.0.0.1:$PORT/generate -H 'Content-Type: application/json' \
    -d '{"text":"1+1=","sampling_params":{"max_new_tokens":8,"temperature":0}}' >/dev/null || true
  echo "--- sgl-eval arm=$ARM n=$NEX $(date -Is)"
  ( source "$CAMP/work/venv_eval/bin/activate"
    export HF_HOME=/workspace/.cache/huggingface
    sgl-eval run gsm8k \
      --base-url "http://127.0.0.1:$PORT/v1" \
      --model "$MODEL" \
      --num-examples "$NEX" \
      --num-threads 64 \
      --max-tokens 2048 \
      --temperature 0 \
      --seed 0 \
      --out-dir "$OUT/run_${ARM}" ) > "$OUT/sgl_eval_${ARM}.log" 2>&1 || echo "sgl-eval rc=$? (logged)"
  kill -- -"$SRV_PGID" 2>/dev/null || true
  sleep 8
  kill -9 -- -"$SRV_PGID" 2>/dev/null || true
  sleep 4
  SRV_PGID=""
done
echo "=== gsm8k A/B $TAG done $(date -Is) ==="
