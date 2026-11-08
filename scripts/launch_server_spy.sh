#!/usr/bin/env bash
set -euo pipefail
ARM="$1"; MODEL="$2"; PORT="$3"; MEMFRAC="$4"; shift 4
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-$CAMP/work}"
source "$WORK/venv_$ARM/bin/activate"
export SGLANG_DISABLE_LEAN_ATTENTION=1
export SGLANG_USE_AITER=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=/workspace/.cache/huggingface
export SGLANG_LAUNCH_SPY_LOG="$CAMP/logs/server/spy_${ARM}.jsonl"
: > "$SGLANG_LAUNCH_SPY_LOG"
SPY_PY="${SGLANG_VALIDATION_SPY_PY:-}"
if [ -z "$SPY_PY" ]; then
  if [ -f "$CAMP/scripts/launch_server_instrumented.py" ]; then SPY_PY="$CAMP/scripts/launch_server_instrumented.py";
  elif [ -f "$WORK/launch_server_instrumented.py" ]; then SPY_PY="$WORK/launch_server_instrumented.py";
  else echo "ERROR: launch_server_instrumented.py not found"; exit 64; fi
fi
exec python "$SPY_PY" \
  --model-path "$MODEL" \
  --attention-backend triton \
  --context-length 10240 \
  --mem-fraction-static "$MEMFRAC" \
  --host 127.0.0.1 --port "$PORT" \
  "$@"
