#!/usr/bin/env bash
# Round 3 server launcher. Usage: launch_server_r3.sh <arm: main|old|new> <model_path> <port> <memfrac> [max_total_tokens] [extra: spy]
set -euo pipefail
ARM="$1"; MODEL="$2"; PORT="$3"; MEMFRAC="$4"; MAXTOK="${5:-0}"; MODE="${6:-plain}"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
source "$WORK/venv_$ARM/bin/activate"
export SGLANG_DISABLE_LEAN_ATTENTION=1
export SGLANG_USE_AITER=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_HOME=/workspace/.cache/huggingface
export HF_HUB_OFFLINE=1
EXTRA=()
[ "$MAXTOK" != "0" ] && EXTRA+=(--max-total-tokens "$MAXTOK")
if [ "$MODE" = "spy" ]; then
  export SGLANG_LAUNCH_SPY_LOG="${SGLANG_LAUNCH_SPY_LOG:?}"
  exec python "$CAMP/round3/scripts/launch_server_spy_r3.py" \
    --model-path "$MODEL" --attention-backend triton --context-length 10240 \
    --mem-fraction-static "$MEMFRAC" --host 127.0.0.1 --port "$PORT" "${EXTRA[@]}"
fi
exec python -m sglang.launch_server \
  --model-path "$MODEL" \
  --attention-backend triton \
  --context-length 10240 \
  --mem-fraction-static "$MEMFRAC" \
  --host 127.0.0.1 --port "$PORT" \
  "${EXTRA[@]}"
