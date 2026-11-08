#!/usr/bin/env bash
# Round 3 environment evidence collection (Phase 0.1): read-only hardware + stack.
set -euo pipefail
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
EV="$CAMP/round3/evidence/environment"
mkdir -p "$EV"
{
  echo "# collected $(date -u --iso-8601=seconds)"
  date -u --iso-8601=seconds
  uname -a
  cat /etc/os-release
  df -h / /workspace
  free -h
  rocminfo
  rocm-smi
  rocm-smi --showmeminfo vram
  rocm-smi --showpids
  hipcc --version
} > "$EV/host_rocm_snapshot.txt" 2>&1

WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
"$WORK/venv_main/bin/python" - <<'EOF' > "$EV/gpu_properties.json"
import json
import torch
import triton

assert torch.cuda.is_available(), "Physical ROCm GPU unavailable"
p = torch.cuda.get_device_properties(0)

from sglang.kernels.arch import current_arch
arch = current_arch()
cc = arch.num_sms

print(json.dumps({
    "torch": torch.__version__,
    "torch_hip": torch.version.hip,
    "triton": triton.__version__,
    "device_name": p.name,
    "gcn_arch_name": getattr(p, "gcnArchName", None),
    "multi_processor_count": p.multi_processor_count,
    "total_memory_bytes": p.total_memory,
    "mem_get_info_bytes": list(torch.cuda.mem_get_info()),
    "sglang_current_arch_num_sms": cc,
    "computed_threshold": max(8, 8 * cc // 20),
}, indent=2))
EOF
echo "environment evidence written to $EV"
