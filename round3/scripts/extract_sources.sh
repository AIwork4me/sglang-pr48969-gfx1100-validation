#!/usr/bin/env bash
# Round 3 source preparation: extract the three arm trees from the local
# verified sglang git object store (objects fetched from sgl-project/sglang
# via gh-proxy.org; commits independently confirmed against the GitHub API).
#
# Arms:
#   main = cbbc6b67f48008a8b739f4667d7b14abb89088cf  (PR #48969 merge base)
#   old  = 1da9ae2fcba99be22ed756083e1eb505c1cf5afe  with ONLY the tiny-grid
#          threshold line reverted to the pre-1da9ae2 fixed value (batch * head_tiles < 8)
#   new  = 1da9ae2fcba99be22ed756083e1eb505c1cf5afe  (upstream PR head, unmodified)
set -euo pipefail
CAMP="${SGLANG_VALIDATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="${SGLANG_VALIDATION_WORK:-/workspace/round3-work}"
SGIT="${SGLANG_UPSTREAM_GIT:-/workspace/sglang-upstream}"
NEW_SHA=1da9ae2fcba99be22ed756083e1eb505c1cf5afe
MAIN_SHA=cbbc6b67f48008a8b739f4667d7b14abb89088cf
mkdir -p "$WORK"
cd "$SGIT"

for pair in "main $MAIN_SHA" "new $NEW_SHA"; do
  set -- $pair; ARM=$1; SHA=$2
  rm -rf "$WORK/src_$ARM"; mkdir -p "$WORK/src_$ARM"
  git archive "$SHA" | tar x -C "$WORK/src_$ARM"
  echo "$SHA" > "$WORK/src_$ARM/.round3_base_sha"
done

rm -rf "$WORK/src_old"; cp -a "$WORK/src_new" "$WORK/src_old"
echo "$NEW_SHA + round3 revert of the scaled threshold" > "$WORK/src_old/.round3_base_sha"
PYF="python/sglang/kernels/ops/attention/decode_attention.py"
python3 - "$WORK/src_old/$PYF" <<'EOF'
import sys
p = sys.argv[1]
src = open(p).read()
old = "if batch * head_tiles < max(8, 8 * core_count // 20):"
new = "if batch * head_tiles < 8:"
assert src.count(old) == 1, "threshold line not found exactly once"
open(p, "w").write(src.replace(old, new))
EOF

# record provenance
EV="$CAMP/round3/evidence/source"; mkdir -p "$EV"
{
  echo "main_base_sha $MAIN_SHA"
  echo "main_base_tree $(git log -1 --format=%T $MAIN_SHA)"
  echo "new_gate_sha  $NEW_SHA"
  echo "new_gate_tree $(git log -1 --format=%T $NEW_SHA)"
} > "$EV/arm_commits.txt"
for ARM in main old new; do
  sha256sum "$WORK/src_$ARM/$PYF" >> "$EV/arm_gate_file.sha256"
done
diff -r -x '.round3_base_sha' -x '__pycache__' -x '*.egg-info' -x 'pyproject.toml.orig' -x '.pytest_cache' "$WORK/src_new" "$WORK/src_old" > "$EV/old_vs_new.diff" || true
diff -r -x '.round3_base_sha' -x '__pycache__' -x '*.egg-info' -x 'pyproject.toml.orig' -x '.pytest_cache' -x 'aot' "$WORK/src_main" "$WORK/src_new" > "$EV/main_vs_new.diff" || true
echo "=== extract_sources done: only-expected-diff check ==="
# ignore our own provenance marker files in the source diff
LINES=$(diff -r -x '.round3_base_sha' -x '__pycache__' -x '*.egg-info' -x 'pyproject.toml.orig' -x '.pytest_cache' "$WORK/src_new" "$WORK/src_old" | grep -c '^[<>]' || true)
echo "old_vs_new source diff lines: $LINES (expect 2: one < and one > threshold line)"
[ "$LINES" = "2" ] || { echo "UNEXPECTED old/new source drift"; exit 1; }
