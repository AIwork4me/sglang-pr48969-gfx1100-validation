#!/usr/bin/env bash
# Download Qwen/Qwen3-0.6B at the pinned revision via the configured HF mirror.
set -euo pipefail
REV=c1899de289a04d12100db370d81485cdf75e47ca
OUT="${1:-/workspace/round3-work/dl/qwen3-06b}"
EP="${HF_ENDPOINT:-https://hf-mirror.com}"
REPO="Qwen/Qwen3-0.6B"
mkdir -p "$OUT"
FILES=$(curl -sf --retry 5 "$EP/api/models/$REPO/revision/$REV" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for f in d['siblings']:
    n=f['rfilename']
    if n.startswith(('model','tokenizer','vocab','merges','generation','config')) and not n.endswith('.bin.index.json'):
        print(n)")
echo "$FILES"
for fn in $FILES; do
  dst="$OUT/$fn"
  [ -s "$dst" ] && { echo "skip $fn"; continue; }
  echo "get $fn"
  curl -sfL --retry 8 --retry-delay 3 -C - -o "$dst.part" "$EP/$REPO/resolve/$REV/$fn" && mv "$dst.part" "$dst" || { echo "FAILED $fn"; exit 1; }
done
cd "$OUT"
sha256sum $FILES > round3_model_files.sha256
python3 - <<'EOF'
import json, hashlib, os
files = [l.split()[1] for l in open('round3_model_files.sha256') if l.strip()]
json.dump({"repo": "Qwen/Qwen3-0.6B", "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
           "files": {f: {"size": os.path.getsize(f),
                         "sha256": hashlib.sha256(open(f,'rb').read()).hexdigest()} for f in files}},
          open("round3_download_manifest.json","w"), indent=2)
print("DONE", len(files), "files")
EOF
