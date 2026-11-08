#!/usr/bin/env bash
set -euo pipefail
ARM="$1"
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname '${BASH_SOURCE[0]}')" && cd .. && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-$CAMP/work}"
export TMPDIR="${TMPDIR_BIG:-/root/tmp-big}"
source "$WORK/venv_$ARM/bin/activate"
cd "$WORK/src_$ARM"
[ -f python/pyproject.toml.orig ] || cp python/pyproject.toml python/pyproject.toml.orig
cp python/pyproject_other.toml python/pyproject.toml
pip install --no-deps --no-build-isolation -e python/
python -c "import sglang, torch; print('sglang import OK; torch', torch.__version__)"
