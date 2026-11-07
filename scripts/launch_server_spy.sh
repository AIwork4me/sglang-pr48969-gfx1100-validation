#!/usr/bin/env bash
set -euo pipefail
ARM="$1"; MODEL="$2"; PORT="$3"; MEMFRAC="$4"; shift 4
CAMP=/root/sglang-pr48969-validation
source "$CAMP/work/venv_$ARM/bin/activate"
export SGLANG_DISABLE_LEAN_ATTENTION=1
export SGLANG_USE_AITER=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=/workspace/.cache/huggingface
export SGLANG_LAUNCH_SPY_LOG="$CAMP/logs/server/spy_${ARM}.jsonl"
: > "$SGLANG_LAUNCH_SPY_LOG"
exec python "$CAMP/work/launch_server_instrumented.py" \
  --model-path "$MODEL" \
  --attention-backend triton \
  --context-length 10240 \
  --mem-fraction-static "$MEMFRAC" \
  --host 127.0.0.1 --port "$PORT" \
  "$@"
