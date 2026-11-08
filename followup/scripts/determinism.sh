#!/usr/bin/env bash
# Deterministic-serving verification — REPAIR-ROUND VERSION (2026-11-08).
#
# History: the experiment-round version of this script ran `for ARM in main pr`
# under `set -euo pipefail` with `exit 2` on arm startup failure, so a single
# execution stopped after the first failing arm. The archived evidence was
# therefore produced by TWO invocations (this script for main; the sed-derived
# single-arm variant determinism_pr.historical.sh for pr — provable by a
# one-line diff). Both logs show the identical startup failure and are
# authoritative. This rewrite makes the intended per-arm behavior explicit:
#   - run_arm main and run_arm pr execute INDEPENDENTLY; one arm failing never
#     prevents the other from running;
#   - each arm records launch command, timestamps, PID/PGID, exit code,
#     readiness, error class, verdict, and evidence path to record_<arm>.json;
#   - verdicts: PASS (started + determinism checks all identical),
#     BLOCKED (startup failure classified as resource/environment, e.g.
#     OutOfResources/OOM), FAIL (unexpected behavior or evidence
#     inconsistency), NOT_RUN (arm skipped by caller);
#   - cleanup kills ONLY the process group this script created ($SRV_PGID).
#
# GPU note: NOT executed in the 2026-11-08 repair round (NO-NEW-GPU policy);
# control flow is covered by tests/test_determinism_flow.py using a fake
# launcher (DETERMINISM_LAUNCHER env override). The archived GPU evidence
# remains the determinism logs committed with the follow-up round.
#
# Usage: determinism.sh [arm ...]   (default: main pr)
set -uo pipefail   # NOT -e: per-arm failures must be recorded, not abort
CAMP="${SGLANG_VALIDATION_ROOT:-/root/followup}"
WORK="${SGLANG_VALIDATION_WORK:-/root/sglang-pr48969-validation/work}"
OUT="${DETERMINISM_OUT:-$CAMP/evidence/determinism}"
LAUNCHER="${DETERMINISM_LAUNCHER:-python -m sglang.launch_server}"
PORT="${DETERMINISM_PORT:-31000}"
READY_TRIES="${DETERMINISM_READY_TRIES:-150}"
READY_SLEEP="${DETERMINISM_READY_SLEEP:-5}"
MODEL="${DETERMINISM_MODEL:-Qwen/Qwen3-0.6B}"
mkdir -p "$OUT"

SRV_PGID=""
cleanup() {
  if [ -n "$SRV_PGID" ]; then
    echo "cleanup: killing process group $SRV_PGID (created by this script)" >&2
    kill -- -"$SRV_PGID" 2>/dev/null || true
    sleep 5
    kill -9 -- -"$SRV_PGID" 2>/dev/null || true
    SRV_PGID=""
  fi
}
trap cleanup EXIT
trap 'echo "interrupted" >&2; exit 130' INT TERM

classify_log() { # log_path → echoes "class|detail"
  local LOG="$1"
  if grep -q "OutOfResources" "$LOG" 2>/dev/null; then
    local REQ HW
    REQ=$(grep -oE 'Required: [0-9]+' "$LOG" | head -1 | cut -d' ' -f2)
    HW=$(grep -oE 'Hardware limit: [0-9]+' "$LOG" | head -1 | cut -d' ' -f3)
    if [ -n "$REQ" ] && [ -n "$HW" ]; then
      echo "OutOfResources|shared memory Required: ${REQ} > Hardware limit: ${HW}"
      return
    fi
    echo "OutOfResources|unparsed resource numbers"
    return
  fi
  if grep -qiE 'out of memory|CUDA error: out of memory|HIP error.*oom' "$LOG" 2>/dev/null; then
    echo "OOM|out-of-memory class"
    return
  fi
  echo "UNEXPECTED|see server log"
}

run_arm() { # arm
  local ARM="$1"
  local REC="$OUT/record_${ARM}.json"
  local LOG="$OUT/server_${ARM}.log"
  local START END PID PGID EXITCODE READY=0 VERDICT ECLASS EDETAIL
  local ARGS=(--model-path "$MODEL" --attention-backend triton --context-length 10240
              --mem-fraction-static 0.75 --max-total-tokens 100000
              --enable-deterministic-inference
              --host 127.0.0.1 --port "$PORT")
  echo "=== determinism arm=$ARM start $(date -u +%FT%TZ)"
  START=$(date -u +%FT%TZ)
  # setsid: the launcher gets its own process group so cleanup can target
  # exactly this arm's server (and nothing else on the host)
  ( source "$WORK/venv_$ARM/bin/activate"
    exec setsid $LAUNCHER "${ARGS[@]}" ) > "$LOG" 2>&1 < /dev/null &
  PID=$!
  PGID=$(ps -o pgid= -p "$PID" 2>/dev/null | tr -d ' ')
  SRV_PGID="$PGID"
  for i in $(seq 1 "$READY_TRIES"); do
    sleep "$READY_SLEEP"
    if curl -s --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then READY=1; break; fi
    kill -0 "$PID" 2>/dev/null || break
  done
  if [ "$READY" != 1 ]; then
    if kill -0 "$PID" 2>/dev/null; then
      EXITCODE=-1   # still running (readiness timeout): the script kills it below
    else
      wait "$PID" 2>/dev/null; EXITCODE=$?
    fi
    IFS='|' read -r ECLASS EDETAIL < <(classify_log "$LOG")
    if [ "$ECLASS" = "OutOfResources" ] || [ "$ECLASS" = "OOM" ]; then VERDICT="BLOCKED"
    else VERDICT="FAIL"; fi
    END=$(date -u +%FT%TZ)
    python3 - "$REC" "$ARM" "$START" "$END" "$PID" "$PGID" "$EXITCODE" 0 "$VERDICT" "$ECLASS" "$EDETAIL" "$LOG" "${ARGS[*]}" <<'PY'
import json, sys
(rec, arm, start, end, pid, pgid, code, ready, verdict, ecl, edet, log, args) = sys.argv[1:15]
json.dump({"arm": arm, "launch_command": args, "launcher": "see server log for effective argv",
           "start_utc": start, "end_utc": end, "pid": pid, "pgid": pgid,
           "exit_code": int(code), "server_ready": bool(int(ready)),
           "error_class": ecl, "error_detail": edet, "verdict": verdict,
           "evidence": log}, open(rec, "w"), indent=1)
PY
    echo "arm=$ARM verdict=$VERDICT ($ECLASS: $EDETAIL)"
    kill -- -"$PGID" 2>/dev/null || true; sleep 3; kill -9 -- -"$PGID" 2>/dev/null || true; SRV_PGID=""
    return 0
  fi
  # server ready: run the determinism probes (alone x2, concurrent, alone)
  PROBE_RESULT=$(python3 - "$PORT" <<'PY'
import json, sys, urllib.request, concurrent.futures
port = sys.argv[1]
PROMPT = {"text": "The capital of France is", "sampling_params": {"temperature": 0, "max_new_tokens": 64, "ignore_eos": True}}
DISTRACT = {"text": "Write the number 7 in words, then count to five slowly:", "sampling_params": {"temperature": 0, "max_new_tokens": 64}}
def gen(p):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/generate",
                                 data=json.dumps(p).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())
try:
    a1 = gen(PROMPT); a2 = gen(PROMPT)
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        f1 = ex.submit(gen, PROMPT); f2 = ex.submit(gen, DISTRACT)
        b1 = f1.result(); _ = f2.result()
    c1 = gen(PROMPT)
    out = {"probe_ok": True,
           "run_to_run_identical": a1["text"] == a2["text"],
           "batch_invariant": a1["text"] == b1["text"] == c1["text"],
           "texts": [a1["text"], a2["text"], b1["text"], c1["text"]]}
except Exception as e:
    out = {"probe_ok": False, "error": repr(e)}
print(json.dumps(out))
PY
)
  kill -- -"$PGID" 2>/dev/null || true; sleep 3
  kill -9 -- -"$PGID" 2>/dev/null || true; SRV_PGID=""
  END=$(date -u +%FT%TZ)
  python3 - "$REC" "$ARM" "$START" "$END" "$PID" "$PGID" 0 1 "$PROBE_RESULT" "$LOG" "${ARGS[*]}" <<'PY'
import json, sys
(rec, arm, start, end, pid, pgid, code, ready, probe, log, args) = sys.argv[1:12]
try:
    p = json.loads(probe)
except json.JSONDecodeError:
    p = {"probe_ok": False, "error": "unparseable probe output"}
if not p.get("probe_ok"):
    verdict, ecl, edet = "FAIL", "PROBE", p.get("error", "probe failed")
elif p.get("run_to_run_identical") and p.get("batch_invariant"):
    verdict, ecl, edet = "PASS", None, "outputs identical across runs/batches"
else:
    verdict, ecl, edet = "FAIL", "OUTPUT-MISMATCH", \
        f"run_to_run_identical={p.get('run_to_run_identical')} batch_invariant={p.get('batch_invariant')}"
json.dump({"arm": arm, "launch_command": args, "start_utc": start, "end_utc": end,
           "pid": pid, "pgid": pgid, "exit_code": int(code), "server_ready": bool(int(ready)),
           "probe": p, "error_class": ecl, "error_detail": edet, "verdict": verdict,
           "evidence": log}, open(rec, "w"), indent=1)
print(f"arm={arm} verdict={verdict} ({edet})")
PY
}

ARMS="${*:-main pr}"
for ARM in $ARMS; do
  case "$ARM" in main|pr) ;; *) echo "unknown arm $ARM" >&2; exit 64;; esac
done
for ARM in $ARMS; do run_arm "$ARM"; done

# overall verdict: FAIL > BLOCKED > NOT_RUN > PASS
python3 - "$OUT" $ARMS <<'PY'
import json, sys
out, arms = sys.argv[1], sys.argv[2:]
recs = {}
for a in arms:
    p = f"{out}/record_{a}.json"
    recs[a] = json.load(open(p)) if __import__("os").path.exists(p) else {"arm": a, "verdict": "NOT_RUN"}
order = {"FAIL": 0, "BLOCKED": 1, "NOT_RUN": 2, "PASS": 3}
overall = sorted((r["verdict"] for r in recs.values()), key=lambda v: order[v])[0]
classes = {r.get("error_class") for r in recs.values() if r.get("error_class")}
identical = len(classes) == 1
json.dump({"overall": overall, "identical_error_class_across_arms": identical,
           "arms": recs}, open(f"{out}/verdict.json", "w"), indent=1)
print(f"overall verdict: {overall}; identical_error_class_across_arms={identical}")
PY
trap - EXIT
