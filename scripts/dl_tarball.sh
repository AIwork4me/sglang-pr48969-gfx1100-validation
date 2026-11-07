#!/usr/bin/env bash
# Resumable-by-restart tarball fetcher (codeload lacks Range support; restart on failure)
sha="$1"; out="$2"
for i in $(seq 1 200); do
  curl -sL --max-time 14400 --speed-limit 2000 --speed-time 120 -o "$out.part" "https://codeload.github.com/sgl-project/sglang/tar.gz/${sha}" && gzip -t "$out.part" 2>/dev/null && mv "$out.part" "$out" && echo "DONE $sha $(date -Is)" && exit 0
  echo "retry $i $(date -Is) size=$(stat -c%s "$out.part" 2>/dev/null)"
  sleep 5
done
exit 1
