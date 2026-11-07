import sys, os, logging
os.environ.setdefault("HF_HOME", "/root/sglang-pr48969-validation/models_cache/hf")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
from huggingface_hub import snapshot_download
repo = sys.argv[1]
rev = sys.argv[2] if len(sys.argv) > 2 else None
p = snapshot_download(repo, revision=rev)
print("SNAPSHOT_PATH", p)
