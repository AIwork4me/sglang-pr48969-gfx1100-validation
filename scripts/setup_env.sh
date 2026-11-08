#!/usr/bin/env bash
# Build one isolated SGLang environment replicating docker/rocm-gfx1151.Dockerfile
# on the host (no nested docker here). Usage: setup_env.sh <arm: main|pr>
set -euo pipefail
ARM="$1"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname '${BASH_SOURCE[0]}')" && cd .. && pwd)}"
SRC="$CAMP/work/src_$ARM"
VENV="$CAMP/work/venv_$ARM"
LOG="$CAMP/logs/setup_env_${ARM}.log"
mkdir -p "${TMPDIR_BIG:-/root/tmp-big}"
export TMPDIR="${TMPDIR_BIG:-/root/tmp-big}"
exec > >(tee -a "$LOG") 2>&1
echo "=== setup_env $ARM start $(date -Is) ==="
[ -d "$SRC" ] || { echo "missing $SRC"; exit 1; }

# Plain venv; the host ROCm stack (/opt/venv: torch 2.9.1+git rocm7.21, triton
# 3.5.1) is attached read-only via a .pth so both arms inherit identical
# torch/triton without re-downloading 3GB+ of AMD wheels.
rm -rf "$VENV"
/usr/bin/python3.12 -m venv "$VENV"
echo "/opt/venv/lib/python3.12/site-packages" > "$VENV/lib/python3.12/site-packages/00_base_rocm.pth"
source "$VENV/bin/activate"
python -V
python -c "import torch, triton; assert torch.version.hip; print('inherited torch', torch.__version__, '| triton', triton.__version__)"
pip install --upgrade pip wheel setuptools "setuptools-rust>=1.11" "setuptools-scm>=8.0" ninja

# Flat ROCm dependency set (official gfx1151 docker flatten: runtime_base,
# runtime_common, srt_hip, diffusion_common, diffusion_hip minus sglang[..]
# self-refs, torch, st_attn, vsa; compressed-tensors pinned to 0.15.0).
FLAT_DEPS="${SGLANG_VALIDATION_FLAT_DEPS:-}"
if [ -z "$FLAT_DEPS" ]; then
  if [ -f "$CAMP/configs/rocm_flat_deps.txt" ]; then FLAT_DEPS="$CAMP/configs/rocm_flat_deps.txt";
  elif [ -f "$CAMP/work/rocm_flat_deps.txt" ]; then FLAT_DEPS="$CAMP/work/rocm_flat_deps.txt";
  else echo "ERROR: rocm_flat_deps.txt not found"; exit 64; fi
fi
pip install -r "$FLAT_DEPS"

# monokernels_hip extra: sgl-amd-mono at the exact pinned git SHA (installed
# from the GitHub tarball of e52803f9d2b7dabff4bfd2f53ec25c03d56af947).
if [ -d "$CAMP/work/dl/sgl_amd_mono_src" ]; then
  pip install --no-deps "$CAMP/work/dl/sgl_amd_mono_src"
fi

# pyproject swap exactly as docker/rocm-gfx1151.Dockerfile performs it, but
# preserving the original file for audit (cp instead of rm+mv).
cd "$SRC"
if [ ! -f python/pyproject.toml.orig ]; then
  cp python/pyproject.toml python/pyproject.toml.orig
fi
cp python/pyproject_other.toml python/pyproject.toml

# Editable install without dependency resolution and without build isolation
# (build isolation would try to pull the CUDA-pinned torch==2.14.1).
pip install --no-deps --no-build-isolation -e python/

python -c "import sglang, torch; print('sglang import OK', 'torch', torch.__version__)"
echo "=== setup_env $ARM done $(date -Is) ==="
