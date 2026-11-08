#!/usr/bin/env bash
# Round 3 sgl_kernel AOT build for gfx1100.
# The kernels/aot source is byte-identical across the three arms (verified by
# diff at extraction; recorded in round3/evidence/source), so ONE build is made
# from src_main and the identical wheel is installed into all three arm venvs.
set -euo pipefail
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
LOG="$CAMP/round3/evidence/environment/build_sglkernel.log"
export TMPDIR="${TMPDIR_BIG:-/root/tmp-big}"
exec > >(tee -a "$LOG") 2>&1
echo "=== round3 build_sglkernel start $(date -Is) ==="

# prove aot source identity across arms (fail-closed): the working-tree aot
# sources must equal (upstream cbbc6b6 tree) + (documented gfx1100 patch).
cd "$WORK/src_main/python/sglang/kernels/aot"
rm -rf /tmp/opencode/aot_pristine && mkdir -p /tmp/opencode/aot_pristine
git -C /workspace/sglang-upstream archive cbbc6b67f48008a8b739f4667d7b14abb89088cf -- python/sglang/kernels/aot | tar x -C /tmp/opencode/aot_pristine --strip-components=4
sh "$CAMP/patches/sgl-kernel-gfx1100.sh" /tmp/opencode/aot_pristine/setup_rocm.py > /dev/null
cp -f /tmp/opencode/aot_pristine/pyproject_rocm.toml /tmp/opencode/aot_pristine/pyproject.toml
for f in $(cd /tmp/opencode/aot_pristine && find . -type f | sed 's|^\./||' | grep -v -E 'pyproject.toml.orig'); do
  cmp -s "/tmp/opencode/aot_pristine/$f" "$f" || { echo "differs from pristine+patch: $f"; CHANGED=1; }
done
[ "${CHANGED:-0}" = "0" ] || { echo "AOT SOURCE DRIFT"; exit 1; }
echo "aot source == upstream cbbc6b6 (== 1da9ae2 aot tree) + documented gfx1100 patch: OK"

DIST="$WORK/src_main/python/sglang/kernels/aot/dist"
WHEEL="$(ls "$DIST"/sglang_kernel-*.whl 2>/dev/null | tail -1 || true)"
if [ -z "$WHEEL" ]; then
  source "$WORK/venv_main/bin/activate"
  cd "$WORK/src_main/python/sglang/kernels/aot"
  [ -f pyproject.toml.orig ] || cp pyproject.toml pyproject.toml.orig
  cp -f pyproject_rocm.toml pyproject.toml
  sh "$CAMP/patches/sgl-kernel-gfx1100.sh" setup_rocm.py
  AMDGPU_TARGET=gfx1100 MAX_JOBS=32 python3 setup_rocm.py bdist_wheel
  WHEEL="$(ls "$DIST"/sglang_kernel-*.whl | tail -1)"
fi
echo "wheel: $WHEEL"
sha256sum "$WHEEL" | tee "$CAMP/round3/evidence/source/sglkernel_wheel.sha256"

for ARM in main old new; do
  source "$WORK/venv_$ARM/bin/activate"
  pip install -q --force-reinstall --no-deps "$WHEEL"
  python -c "import sgl_kernel; print('sgl_kernel OK', sgl_kernel.__file__)"
  echo "sgl_kernel installed in $ARM"
done
# compat shims (identical files as Rounds 1-2, from the repo's scripts/)
for ARM in main old new; do
  SP="$WORK/venv_$ARM/lib/python3.12/site-packages"
  cp "$CAMP/scripts/aiter_compat_shim.py" "$CAMP/scripts/norm_compat.py" "$SP/"
  printf 'import aiter_compat_shim\nimport norm_compat\n' > "$SP/zz_aiter_shim.pth"
done
echo "=== round3 build_sglkernel done $(date -Is) ==="
