#!/usr/bin/env bash
# Usage: launch_server.sh <arm> <model> <port> <memfrac> [max_total_tokens]
set -euo pipefail
ARM="$1"; MODEL="$2"; PORT="$3"; MEMFRAC="$4"; MAXTOK="${5:-0}"
# Repo root: default = parent of this script; historical layout override:
# SGLANG_VALIDATION_ROOT=/root/sglang-pr48969-validation
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-$CAMP/work}"
source "$WORK/venv_$ARM/bin/activate"
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
