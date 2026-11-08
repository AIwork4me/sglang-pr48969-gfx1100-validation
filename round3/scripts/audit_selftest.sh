#!/usr/bin/env bash
# Negative self-tests for the round3 audit, run against a DISPOSABLE COPY of the
# repo (never the real tree). Each test corrupts one thing and requires the
# audit to FAIL (exit nonzero). Any negative test passing the audit is a bug.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d /tmp/opencode/round3-negtest.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
FAIL=0

negtest() { # name, corruption-fn, expected audit check to fail
  local name="$1" corrupt="$2"
  rm -rf "$TMP/repo"; mkdir -p "$TMP/repo"
  # copy only what the audit reads (fast subset)
  (cd "$SRC" && tar cf - round3 configs patches | tar xf - -C "$TMP/repo")
  bash -c "$corrupt" "$TMP/repo" || true
  if bash "$TMP/repo/round3/scripts/audit_round3.sh" > "$TMP/audit.log" 2>&1; then
    echo "NEGTEST FAIL (audit passed despite corruption): $name"
    FAIL=1
  else
    echo "NEGTEST PASS (audit rejected): $name"
  fi
}

negtest "one-byte tamper" '
  f=$(grep -m1 "evidence/performance/c1/bench_main_r1.json" "$1/round3/audit/SHA256SUMS" | awk "{print \$2}")
  [ -n "$f" ] && printf "\x00" >> "$1/$f" || exit 0
  exit 0'

negtest "delete manifest" 'rm -f "$1/round3/audit/SHA256SUMS"'

negtest "empty manifest" ': > "$1/round3/audit/SHA256SUMS"'

negtest "manifest escape path" 'echo "0000000000000000000000000000000000000000000000000000000000000000  ../../etc/passwd" >> "$1/round3/audit/SHA256SUMS"'

negtest "manifest duplicate path" 'grep "gate_matrix.json" "$1/round3/audit/SHA256SUMS" | head -1 >> "$1/round3/audit/SHA256SUMS"'

negtest "missing benchmark leg" 'rm -f "$1/round3/evidence/performance/c1/bench_main_r1.json"'

negtest "fake PASS for NOT_RUN test" '
python3 - "$1" <<EOF
import json
p = "$1/round3/audit/VALIDATION_CERTIFICATE.json"
d = json.load(open(p))
for k, v in d["tests"].items():
    if v.get("status") == "NOT_RUN":
        v["status"] = "PASS"; v.pop("reason", None); break
json.dump(d, open(p, "w"), indent=2)
EOF
sed -i "s|round3/audit/SHA256SUMS|x|g" /dev/null 2>/dev/null || true
# manifest check will also fire — that is fine, audit must fail either way
exit 0'

negtest "wrong core count claim" '
python3 - "$1" <<EOF
import json
p = "$1/round3/evidence/environment/gpu_properties.json"
d = json.load(open(p))
d["sglang_current_arch_num_sms"] = 96
d["computed_threshold"] = max(8, 8*96//20)
json.dump(d, open(p, "w"), indent=2)
EOF'

negtest "inflated speedup in summary" '
python3 - "$1" <<EOF
import csv
p = "$1/round3/results/performance_summary.csv"
rows = list(csv.reader(open(p)))
for r in rows[1:]:
    if r and r[1] == "new":
        r[4] = str(float(r[4]) * 2.0)
        break
csv.writer(open(p, "w", newline="")).writerows(rows)
EOF'

negtest "old/new source drift" '
f="$1/round3/evidence/source/old_vs_new.diff"
printf "%s\n" "95c95" "<  extra local change" "---" ">  different" >> "$f"'

exit $FAIL
