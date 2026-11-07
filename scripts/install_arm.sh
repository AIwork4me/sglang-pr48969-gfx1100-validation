#!/usr/bin/env bash
set -euo pipefail
ARM="$1"
CAMP=/root/sglang-pr48969-validation
export TMPDIR=/root/tmp-big
source "$CAMP/work/venv_$ARM/bin/activate"
cd "$CAMP/work/src_$ARM"
[ -f python/pyproject.toml.orig ] || cp python/pyproject.toml python/pyproject.toml.orig
cp python/pyproject_other.toml python/pyproject.toml
pip install --no-deps --no-build-isolation -e python/
python -c "import sglang, torch; print('sglang import OK; torch', torch.__version__)"
