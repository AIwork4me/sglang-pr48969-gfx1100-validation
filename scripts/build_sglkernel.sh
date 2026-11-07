#!/usr/bin/env bash
set -euo pipefail
ARM="$1"
CAMP=/root/sglang-pr48969-validation
source "$CAMP/work/venv_$ARM/bin/activate"
cd "$CAMP/work/src_$ARM/python/sglang/kernels/aot"
if [ ! -f pyproject.toml.orig ]; then cp pyproject.toml pyproject.toml.orig 2>/dev/null || true; fi
cp -f pyproject_rocm.toml pyproject.toml
sh "$CAMP/patches/sgl-kernel-gfx1100.sh" setup_rocm.py
AMDGPU_TARGET=gfx1100 MAX_JOBS=32 python3 setup_rocm.py install
python -c "import sgl_kernel; print('sgl_kernel OK', sgl_kernel.__file__)"
