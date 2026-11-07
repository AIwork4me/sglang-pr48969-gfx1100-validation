#!/usr/bin/env bash
# Usage: launch_server.sh <arm> <model> <port> <memfrac> [max_total_tokens]
set -euo pipefail
ARM="$1"; MODEL="$2"; PORT="$3"; MEMFRAC="$4"; MAXTOK="${5:-0}"
CAMP=/root/sglang-pr48969-validation
source "$CAMP/work/venv_$ARM/bin/activate"
export SGLANG_DISABLE_LEAN_ATTENTION=1
export SGLANG_USE_AITER=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=/workspace/.cache/huggingface
EXTRA=()
if [ "$MAXTOK" != "0" ]; then EXTRA+=(--max-total-tokens "$MAXTOK"); fi
exec python -m sglang.launch_server \
  --model-path "$MODEL" \
  --attention-backend triton \
  --context-length 10240 \
  --mem-fraction-static "$MEMFRAC" \
  --host 127.0.0.1 --port "$PORT" \
  "${EXTRA[@]}"
