#!/usr/bin/env bash
# Deterministic-serving verification (follow-up round 2026-11-08).
# For each arm: launch the server with --enable-deterministic-inference, then:
#   A) same greedy prompt alone, twice (run-to-run invariance)
#   B) same prompt concurrently with a distractor prompt (batch-invariance)
#   C) same prompt alone again
# Compare output token ids across A/B/C. Fail-closed.
set -euo pipefail
CAMP="${SGLANG_VALIDATION_ROOT:-/root/followup}"
WORK="${SGLANG_VALIDATION_WORK:-/root/sglang-pr48969-validation/work}"
OUT="$CAMP/evidence/determinism"
mkdir -p "$OUT"
PORT=31000
MODEL=Qwen/Qwen3-0.6B

cleanup() { [ -n "${SRV_PGID:-}" ] && { kill -- -"$SRV_PGID" 2>/dev/null || true; sleep 5; kill -9 -- -"$SRV_PGID" 2>/dev/null || true; }; }
trap cleanup EXIT

for ARM in main pr; do
  echo "=== determinism arm=$ARM start $(date -Is)"
  source "$WORK/venv_$ARM/bin/activate"
  setsid python -m sglang.launch_server \
    --model-path "$MODEL" --attention-backend triton --context-length 10240 \
    --mem-fraction-static 0.75 --max-total-tokens 100000 \
    --enable-deterministic-inference \
    --host 127.0.0.1 --port $PORT > "$OUT/server_${ARM}.log" 2>&1 < /dev/null &
  SRV_PGID=$!
  UP=0
  for i in $(seq 1 150); do
    sleep 5
    curl -s --max-time 3 http://127.0.0.1:$PORT/health >/dev/null 2>&1 && { UP=1; break; }
    kill -0 "$SRV_PGID" 2>/dev/null || { echo "SERVER DIED arm=$ARM"; tail -30 "$OUT/server_${ARM}.log"; exit 2; }
  done
  [ "$UP" = 1 ] || { echo "health timeout arm=$ARM"; exit 2; }
  grep -oE "enable_deterministic_inference.: [A-Za-z]+" "$OUT/server_${ARM}.log" | head -1 || true

  python - "$PORT" "$OUT" "$ARM" <<'PYEOF'
import json, sys, urllib.request, concurrent.futures
port, out, arm = sys.argv[1], sys.argv[2], sys.argv[3]
PROMPT = {"text": "The capital of France is", "sampling_params": {"temperature": 0, "max_new_tokens": 64, "ignore_eos": True}}
DISTRACT = {"text": "Write the number 7 in words, then count to five slowly:", "sampling_params": {"temperature": 0, "max_new_tokens": 64}}
def gen(payload):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/generate",
                                 data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())
def ids_of(resp):
    mi = resp.get("meta_info", {})
    ids = mi.get("output_ids") or resp.get("output_ids")
    return ids
# A: alone twice
a1 = gen(PROMPT); a2 = gen(PROMPT)
# B: concurrent with distractor
with concurrent.futures.ThreadPoolExecutor(2) as ex:
    f1 = ex.submit(gen, PROMPT); f2 = ex.submit(gen, DISTRACT)
    b1 = f1.result(); _ = f2.result()
# C: alone again
c1 = gen(PROMPT)
ia1, ia2, ib1, ic1 = ids_of(a1), ids_of(a2), ids_of(b1), ids_of(c1)
rec = {"arm": arm, "have_ids": ia1 is not None,
       "text_a1": a1["text"], "text_a2": a2["text"], "text_b1": b1["text"], "text_c1": c1["text"],
       "ids_a1": ia1, "ids_a2": ia2, "ids_b1": ib1, "ids_c1": ic1,
       "run_to_run_identical": a1["text"] == a2["text"],
       "batch_invariant_text": a1["text"] == b1["text"] == c1["text"]}
if ia1 is not None:
    rec["batch_invariant_ids"] = ia1 == ia2 == ib1 == ic1
json.dump(rec, open(f"{out}/result_{arm}.json", "w"), indent=1)
print(json.dumps({k: rec[k] for k in rec if k.startswith(("run_", "batch_", "have_"))}, indent=1))
PYEOF
  kill -- -"$SRV_PGID" 2>/dev/null || true; sleep 6; kill -9 -- -"$SRV_PGID" 2>/dev/null || true; sleep 3
  SRV_PGID=""
  echo "=== determinism arm=$ARM done $(date -Is)"
done
trap - EXIT
echo "determinism run complete"
