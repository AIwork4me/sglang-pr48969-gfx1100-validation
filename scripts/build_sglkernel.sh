#!/usr/bin/env bash
set -euo pipefail
ARM="$1"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname '${BASH_SOURCE[0]}')" && cd .. && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-$CAMP/work}"
source "$WORK/venv_$ARM/bin/activate"
cd "$WORK/src_$ARM/python/sglang/kernels/aot"
if [ ! -f pyproject.toml.orig ]; then cp pyproject.toml pyproject.toml.orig 2>/dev/null || true; fi
cp -f pyproject_rocm.toml pyproject.toml
sh "$CAMP/patches/sgl-kernel-gfx1100.sh" setup_rocm.py
AMDGPU_TARGET=gfx1100 MAX_JOBS=32 python3 setup_rocm.py install
python -c "import sgl_kernel; print('sgl_kernel OK', sgl_kernel.__file__)"
