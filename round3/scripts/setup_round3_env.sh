#!/usr/bin/env bash
# Round 3 environment setup per arm: venv inheriting the host ROCm torch stack
# read-only (replicates docker/rocm-gfx1151.Dockerfile flatten, as in Rounds 1-2).
# Usage: setup_round3_env.sh <arm: main|old|new>
set -euo pipefail
ARM="$1"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
SRC="$WORK/src_$ARM"
VENV="$WORK/venv_$ARM"
LOG="$CAMP/round3/evidence/environment/setup_env_${ARM}.log"
mkdir -p "${TMPDIR_BIG:-/root/tmp-big}" "$CAMP/round3/evidence/environment"
export TMPDIR="${TMPDIR_BIG:-/root/tmp-big}"
exec > >(tee -a "$LOG") 2>&1
echo "=== round3 setup_env $ARM start $(date -Is) ==="
[ -d "$SRC" ] || { echo "missing $SRC (run extract_sources.sh)"; exit 1; }

rm -rf "$VENV"
/usr/bin/python3.12 -m venv "$VENV"
echo "/opt/venv/lib/python3.12/site-packages" > "$VENV/lib/python3.12/site-packages/00_base_rocm.pth"
source "$VENV/bin/activate"
python -V
python -c "import torch, triton; assert torch.version.hip; print('inherited torch', torch.__version__, '| triton', triton.__version__)"
pip install --upgrade pip wheel setuptools "setuptools-rust>=1.11" "setuptools-scm>=8.0" ninja -q
pip install -q -r "$CAMP/configs/rocm_flat_deps.txt"

# Triton 3.6 (rocm 7.2 build) — identical wheel in every arm
pip install -q "https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2/triton-3.6.0%2Brocm7.2.0.gitba5c1517-cp312-cp312-linux_x86_64.whl"

cd "$SRC"
[ -f python/pyproject.toml.orig ] || cp python/pyproject.toml python/pyproject.toml.orig
cp python/pyproject_other.toml python/pyproject.toml
# No Rust extensions: crates.io is unreachable through the lab egress proxy and
# the text-only serving under test does not import them (sglang-mm is the
# multimodal pipeline). Documented deviation, applied identically to all arms.
export SGLANG_BUILD_RUST_EXTS=none
pip install --no-deps --no-build-isolation -q -e python/

python -c "import sglang, torch, triton; print('sglang OK', sglang.__version__, '| torch', torch.__version__, '| triton', triton.__version__)"
echo "=== round3 setup_env $ARM done $(date -Is) ==="
