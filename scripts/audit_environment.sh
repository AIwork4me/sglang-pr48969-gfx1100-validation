#!/usr/bin/env bash
# Phase 0 environment audit. Non-destructive. Writes machine-readable evidence.
set -euo pipefail
OUT="${1:-evidence/environment}"
mkdir -p "$OUT"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
{
  echo "run_id=$RUN_ID"
  date -Is
  uname -a
  lsb_release -a 2>/dev/null || cat /etc/os-release
} > "$OUT/system_${RUN_ID}.txt"
rocminfo > "$OUT/rocminfo_${RUN_ID}.txt" 2>&1 || true
rocm-smi > "$OUT/rocm_smi_${RUN_ID}.txt" 2>&1 || true
rocm-smi --showmeminfo vram --showpids > "$OUT/rocm_smi_mem_${RUN_ID}.txt" 2>&1 || true
hipcc --version > "$OUT/hipcc_${RUN_ID}.txt" 2>&1 || true
/opt/venv/bin/python - <<PY > "$OUT/python_env_${RUN_ID}.txt" 2>&1 || true
import sys, json
print("python", sys.version)
import torch
print("torch", torch.__version__)
print("torch.version.hip", torch.version.hip)
print("torch.version.cuda", torch.version.cuda)
print("cuda_available", torch.cuda.is_available())
print("device_name", torch.cuda.get_device_name(0))
p = torch.cuda.get_device_properties(0)
print("gcn_arch_name", p.gcnArchName)
print("total_vram_bytes", p.total_memory)
free, total = torch.cuda.mem_get_info()
print("mem_get_info_free_bytes", free)
print("mem_get_info_total_bytes", total)
import triton
print("triton", triton.__version__)
PY
df -h > "$OUT/df_h_${RUN_ID}.txt" 2>&1 || true
df -i > "$OUT/df_i_${RUN_ID}.txt" 2>&1 || true
free -h > "$OUT/free_h_${RUN_ID}.txt" 2>&1 || true
lscpu > "$OUT/lscpu_${RUN_ID}.txt" 2>&1 || true
pip freeze > "$OUT/pip_freeze_base_${RUN_ID}.txt" 2>&1 || true
git config --global --list > "$OUT/git_config_${RUN_ID}.txt" 2>&1 || true
gh auth status > "$OUT/gh_auth_${RUN_ID}.txt" 2>&1 || true
echo "audit_complete run_id=$RUN_ID"
