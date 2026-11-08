#!/usr/bin/env bash
# negtest_lib.sh — negative-test harness for the round3 audit. Sourced by
# audit_selftest.sh and test_audit_framework.py; never executed directly.
#
# A negative test PASSES only when ALL of the following hold:
#   1. a full, committed snapshot of the repo (git archive HEAD) passes the
#      audit untouched (per-test Clean Control gate);
#   2. the intended corruption was verifiably applied in the disposable copy
#      (self-verifying corruption function + pre/post SHA256 evidence, with at
#      least one declared target actually changed);
#   3. the audit rejected the corrupted copy (nonzero exit);
#   4. the EXPECTED audit gate is among the failures it reported.
# Anything else is FAIL (injection_failed / clean_control_failed /
# audit_accepted / target_gate_not_hit / fixture) — never a PASS.
#
# All tampering happens inside NEGTEST_TMPROOT (secure mktemp -d; honour
# TMPDIR for small-/tmp hosts). The real repository tree is never written to;
# the harness refuses snapshot roots that resolve inside the source repo.

NEGTEST_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -n "${NEGTEST_TMPROOT:-}" ] && [ -d "${NEGTEST_TMPROOT:-}" ]; then
  :
else
  NEGTEST_TMPROOT="$(mktemp -d -t round3-negtest.XXXXXX)" || exit 2
fi
NEGTEST_LOGDIR="${NEGTEST_LOGDIR:-}"          # optional archive dir for per-test logs
NEGTEST_RESULTS_JSON="${NEGTEST_RESULTS_JSON:-}"
NEGTEST_FIXTURE_HOOK="${NEGTEST_FIXTURE_HOOK:-}"  # unit-test hook: script <root> run after fresh_repo, before clean control
NEGTEST_SUMMARY_PASSED=0
NEGTEST_SUMMARY_TOTAL=0
NEGTEST_LAST_VERDICT=""

negtest_fresh_repo() { # <dst> — full snapshot of the committed HEAD
  local dst="$1"
  mkdir -p "$dst"
  git -C "$NEGTEST_SRC" archive --format=tar HEAD | tar -x -C "$dst"
}

negtest_run_audit() { # <root> <logfile> — runs the snapshot's own audit
  local root="$1" log="$2"
  ( cd "$root" && bash "$root/round3/scripts/audit_round3.sh" ) > "$log" 2>&1
}

negtest_hash_of() { # <root> <repo-relative> — sha256 or "<absent>"
  if [ -e "$1/$2" ]; then sha256sum "$1/$2" | awk '{print $1}'; else printf '<absent>'; fi
}

negtest_rehash() { # <root> <repo-relative> — update the manifest entry of a MODIFIED file
  python3 - "$1" "$2" <<'EOF'
import hashlib, sys
root, rel = sys.argv[1], sys.argv[2]
mp = f"{root}/round3/audit/SHA256SUMS"
h = hashlib.sha256(open(f"{root}/{rel}", "rb").read()).hexdigest()
lines = open(mp).read().splitlines()
out, replaced = [], False
for ln in lines:
    if ln.endswith(f"  {rel}") and len(ln) == 66 + len(rel):
        out.append(f"{h}  {rel}"); replaced = True
    else:
        out.append(ln)
if not replaced:
    out.append(f"{h}  {rel}")
open(mp, "w").write("\n".join(out) + "\n")
EOF
}

negtest_unlist() { # <root> <repo-relative> — drop a DELETED file from the manifest
  python3 - "$1" "$2" <<'EOF'
import sys
root, rel = sys.argv[1], sys.argv[2]
mp = f"{root}/round3/audit/SHA256SUMS"
keep = [ln for ln in open(mp).read().splitlines() if not ln.endswith(f"  {rel}")]
open(mp, "w").write("\n".join(keep) + "\n")
EOF
}

negtest_manifest_ok() { # <root> — sha256sum -c over the copy's manifest
  ( cd "$1" && sha256sum -c round3/audit/SHA256SUMS --quiet ) >/dev/null 2>&1
}

negtest_verdict() { # <id> <verdict>
  local id="$1" v="$2"
  echo "NEGTEST $id $v"
  NEGTEST_LAST_VERDICT="$v"
}

negtest() { # <id> <desc> <expected-gate> <targets:-sep-rel-paths> <corrupt-fn>
  local id="$1" desc="$2" gate="$3" targets_arg="$4" cfn="$5"
  local root="$NEGTEST_TMPROOT/$id"
  local cclog="$NEGTEST_TMPROOT/$id.clean_control.log"
  local alog="$NEGTEST_TMPROOT/$id.audit.log"
  local tlog="$NEGTEST_TMPROOT/$id.transcript.txt"
  local verdict="FAIL:internal"
  NEGTEST_SUMMARY_TOTAL=$((NEGTEST_SUMMARY_TOTAL+1))
NEGTEST_LAST_VERDICT=""

negtest_cleanup() { # remove the disposable temp root (trap handler)
  [ -n "${NEGTEST_TMPROOT:-}" ] && rm -rf "$NEGTEST_TMPROOT"
}

  local realroot
  realroot="$(cd "$root" 2>/dev/null && pwd || true)"
  if [ -n "$realroot" ]; then
    case "$realroot" in
      "$NEGTEST_SRC"|"$NEGTEST_SRC"/*)
        echo "NEGTEST $id FAIL:unsafe_root (refusing to operate inside the real repo)"
        return 1;;
    esac
  fi

  rm -rf "$root"; mkdir -p "$root"
  local -a targets=()
  local rel t0 changed post failed_gates
  local -A PREH=()
  for rel in $targets_arg; do targets+=("$rel"); done

  negtest_body() {
    echo "[$id] $desc"
    echo "expected gate: $gate"
    if ! negtest_fresh_repo "$root" 2>"$NEGTEST_TMPROOT/$id.fixture.err"; then
      echo "fixture: FAILED to create git-archive snapshot of HEAD"
      sed -n '1,5p' "$NEGTEST_TMPROOT/$id.fixture.err"
      negtest_verdict "$id" "FAIL:fixture"
      return
    fi
    echo "fixture: full git archive of HEAD -> $root"

    if [ -n "$NEGTEST_FIXTURE_HOOK" ]; then
      bash "$NEGTEST_FIXTURE_HOOK" "$root" || true
      echo "fixture hook applied: $NEGTEST_FIXTURE_HOOK"
    fi

    # --- per-test Clean Control gate (P0-B) -----------------------------
    t0=$SECONDS
    if negtest_run_audit "$root" "$cclog"; then
      echo "clean control: PASS ($((SECONDS-t0))s)"
    else
      echo "clean control: FAILED — this negative test is NO-GO"
      grep '^FAIL' "$cclog" | head -5
      negtest_verdict "$id" "FAIL:clean_control_failed"
      return
    fi

    # --- pre-corruption hashes of the declared targets -------------------
    if [ "${#targets[@]}" -eq 0 ]; then
      echo "injection: no target paths declared"
      negtest_verdict "$id" "FAIL:injection_failed"
      return
    fi
    for rel in "${targets[@]}"; do
      PREH["$rel"]="$(negtest_hash_of "$root" "$rel")"
      echo "target $rel pre  sha256=${PREH[$rel]}"
    done

    # --- corruption (explicit function interface, self-verifying) -------
    TEST_ROOT="$root"
    if ! "$cfn"; then
      echo "injection: corruption function SELF-VERIFY FAILED"
      negtest_verdict "$id" "FAIL:injection_failed"
      return
    fi
    changed=0
    for rel in "${targets[@]}"; do
      post="$(negtest_hash_of "$root" "$rel")"
      echo "target $rel post sha256=$post"
      [ "$post" != "${PREH[$rel]}" ] && changed=1
    done
    if [ "$changed" != "1" ]; then
      echo "injection: NO declared target changed on disk"
      negtest_verdict "$id" "FAIL:injection_failed"
      return
    fi
    echo "injection: VERIFIED (self-verified by the corruption function; hashes above)"

    # --- audit the corrupted copy ---------------------------------------
    if negtest_run_audit "$root" "$alog"; then
      echo "audit: ACCEPTED the corrupted copy (exit 0) — negative test FAIL"
      negtest_verdict "$id" "FAIL:audit_accepted"
      return
    fi
    failed_gates="$(grep '^FAIL ' "$alog" | awk '{print $2}' | sort -u | tr '\n' ' ')"
    echo "audit: rejected (nonzero exit); failed gates: ${failed_gates:-<none parsed>}"
    if printf '%s\n' $failed_gates | grep -qx "$gate"; then
      echo "expected gate '$gate' fired: YES"
      negtest_verdict "$id" "PASS"
    else
      echo "expected gate '$gate' fired: NO"
      negtest_verdict "$id" "FAIL:target_gate_not_hit"
    fi
  }
  negtest_body > "$tlog" 2>&1
  cat "$tlog"
  verdict="$(grep '^NEGTEST ' "$tlog" | tail -1 | sed 's/^NEGTEST //')"
  NEGTEST_LAST_VERDICT="$verdict"
  [ "$verdict" = "$id PASS" ] && NEGTEST_SUMMARY_PASSED=$((NEGTEST_SUMMARY_PASSED+1))
  if [ -n "$NEGTEST_LOGDIR" ]; then
    mkdir -p "$NEGTEST_LOGDIR"
    cp -f "$tlog" "$NEGTEST_LOGDIR/$id.log" 2>/dev/null || true
    cp -f "$alog" "$NEGTEST_LOGDIR/$id.audit_output.log" 2>/dev/null || true
    cp -f "$cclog" "$NEGTEST_LOGDIR/$id.clean_control.log" 2>/dev/null || true
  fi
  [ "$verdict" = "$id PASS" ]
}

# ---------------------------------------------------------------------------
# Corruption functions (N01–N10). Each receives TEST_ROOT and must:
#   - touch exactly the paths declared in the negtest table;
#   - return nonzero unless it has VERIFIED its own corruption took effect.
# Integrity tests (N01–N05) leave the manifest stale on purpose.
# Semantic tests (N06–N10) re-seal the copy's manifest so the integrity gates
# PASS and only the semantic gate under test can fire.
# ---------------------------------------------------------------------------

corrupt_N01() { # one byte appended to a raw benchmark JSON (no re-seal)
  local f="round3/evidence/performance/c1/bench_main_r1.json"
  NEGTEST_TARGETS=("$f")
  printf '\x00' >> "$TEST_ROOT/$f" || return 1
  [ "$(tail -c 1 "$TEST_ROOT/$f" | od -An -tx1 | tr -d ' \n')" = "00" ] || return 1
}

corrupt_N02() { # delete the SHA256 manifest
  local f="round3/audit/SHA256SUMS"
  NEGTEST_TARGETS=("$f")
  rm -f "$TEST_ROOT/$f" || return 1
  [ ! -e "$TEST_ROOT/$f" ] || return 1
}

corrupt_N03() { # truncate the SHA256 manifest to zero bytes
  local f="round3/audit/SHA256SUMS"
  NEGTEST_TARGETS=("$f")
  : > "$TEST_ROOT/$f" || return 1
  [ -e "$TEST_ROOT/$f" ] && [ ! -s "$TEST_ROOT/$f" ] || return 1
}

corrupt_N04() { # manifest entry pointing outside the repo
  local f="round3/audit/SHA256SUMS"
  NEGTEST_TARGETS=("$f")
  printf '%s  %s\n' "0000000000000000000000000000000000000000000000000000000000000000" \
    "../../etc/passwd" >> "$TEST_ROOT/$f" || return 1
  tail -1 "$TEST_ROOT/$f" | grep -qE '\.\./\.\./etc/passwd' || return 1
}

corrupt_N05() { # duplicate manifest record
  local f="round3/audit/SHA256SUMS" rel="round3/results/gate_matrix.json"
  NEGTEST_TARGETS=("$f")
  grep "  ${rel}\$" "$TEST_ROOT/$f" | head -1 >> "$TEST_ROOT/$f" || return 1
  [ "$(grep -c "  ${rel}\$" "$TEST_ROOT/$f")" = "2" ] || return 1
}

corrupt_N06() { # delete a REQUIRED benchmark leg + sync the manifest so the
                # integrity gate passes and leg_completeness finds the gap
  local f="round3/evidence/performance/c1/bench_new_r10.json"
  NEGTEST_TARGETS=("$f" "round3/audit/SHA256SUMS")
  rm -f "$TEST_ROOT/$f" || return 1
  [ ! -e "$TEST_ROOT/$f" ] || return 1
  negtest_unlist "$TEST_ROOT" "$f"
  ! grep -qE "^[0-9a-f]{64}  ${f}\$" "$TEST_ROOT/round3/audit/SHA256SUMS" || return 1
  negtest_manifest_ok "$TEST_ROOT" || return 1
}

corrupt_N07() { # certificate claims PASS for a genuinely BLOCKED test
                # (verdicts.json untouched, manifest re-sealed)
  local f="round3/audit/VALIDATION_CERTIFICATE.json"
  NEGTEST_TARGETS=("$f" "round3/audit/SHA256SUMS")
  python3 - "$TEST_ROOT" <<'EOF' || return 1
import json, sys
root = sys.argv[1]
p = f"{root}/round3/audit/VALIDATION_CERTIFICATE.json"
d = json.load(open(p))
t = d["tests"]["deterministic_serving_retry"]
assert t["status"] == "BLOCKED", "precondition: original status must be BLOCKED"
t["status"] = "PASS"
t.pop("reason", None)
json.dump(d, open(p, "w"), indent=2)
d2 = json.load(open(p))
assert d2["tests"]["deterministic_serving_retry"]["status"] == "PASS"
v = json.load(open(f"{root}/round3/audit/verdicts.json"))
assert v["deterministic_serving_retry"]["status"] == "BLOCKED"
EOF
  negtest_rehash "$TEST_ROOT" "$f"
  negtest_manifest_ok "$TEST_ROOT" || return 1
}

corrupt_N08() { # forged core count (48 -> 96) + threshold, manifest re-sealed
  local f="round3/evidence/environment/gpu_properties.json"
  NEGTEST_TARGETS=("$f" "round3/audit/SHA256SUMS")
  python3 - "$TEST_ROOT" <<'EOF' || return 1
import json, sys
root = sys.argv[1]
p = f"{root}/round3/evidence/environment/gpu_properties.json"
d = json.load(open(p))
assert d["sglang_current_arch_num_sms"] == 48, "precondition: measured 48"
d["sglang_current_arch_num_sms"] = 96
d["computed_threshold"] = max(8, 8 * 96 // 20)
json.dump(d, open(p, "w"), indent=2)
d2 = json.load(open(p))
assert d2["sglang_current_arch_num_sms"] == 96 and d2["computed_threshold"] == 38
EOF
  negtest_rehash "$TEST_ROOT" "$f"
  negtest_manifest_ok "$TEST_ROOT" || return 1
}

corrupt_N09() { # throughput statistics inflated 100% in the summary CSV,
                # manifest re-sealed so summary_medians_recompute must catch it
  local f="round3/results/performance_summary.csv"
  NEGTEST_TARGETS=("$f" "round3/audit/SHA256SUMS")
  python3 - "$TEST_ROOT" <<'EOF' || return 1
import csv, sys
root = sys.argv[1]
p = f"{root}/round3/results/performance_summary.csv"
rows = list(csv.reader(open(p)))
hdr = rows[0]
ic, ia, iv = hdr.index("cell"), hdr.index("arm"), hdr.index("thr_median")
orig = None
for r in rows[1:]:
    if r and r[ic] == "c1" and r[ia] == "new":
        orig = float(r[iv]); r[iv] = str(orig * 2.0); break
assert orig is not None and orig > 0, "precondition: c1/new row must exist"
csv.writer(open(p, "w", newline="")).writerows(rows)
for r in list(csv.reader(open(p)))[1:]:
    if r and r[ic] == "c1" and r[ia] == "new":
        assert abs(float(r[iv]) - orig * 2.0) < 1e-9
EOF
  negtest_rehash "$TEST_ROOT" "$f"
  negtest_manifest_ok "$TEST_ROOT" || return 1
}

corrupt_N10() { # second modification appended to the old/new source diff
  local f="round3/evidence/source/old_vs_new.diff"
  NEGTEST_TARGETS=("$f" "round3/audit/SHA256SUMS")
  printf '%s\n' "120a121,122" \
    ">     # injected second local modification (round3.1 negative test N10)" \
    "<     # line removed by injected drift" >> "$TEST_ROOT/$f" || return 1
  [ "$(grep -c '^[<>]' "$TEST_ROOT/$f")" = "4" ] || return 1
  negtest_rehash "$TEST_ROOT" "$f"
  negtest_manifest_ok "$TEST_ROOT" || return 1
}

negtest_write_results_json() { # machine-readable summary (if target given)
  [ -n "$NEGTEST_RESULTS_JSON" ] || return 0
  NEGTEST_LOGDIR="$NEGTEST_LOGDIR" NEGTEST_SUMMARY_PASSED="$NEGTEST_SUMMARY_PASSED" \
  NEGTEST_SUMMARY_TOTAL="$NEGTEST_SUMMARY_TOTAL" \
  python3 - "$NEGTEST_RESULTS_JSON" <<'EOF'
import json, os, sys
out = sys.argv[1]
npass, ntot = int(os.environ["NEGTEST_SUMMARY_PASSED"]), int(os.environ["NEGTEST_SUMMARY_TOTAL"])
per = []
ld = os.environ.get("NEGTEST_LOGDIR")
if ld and os.path.isdir(ld):
    for f in sorted(os.listdir(ld)):
        if f.endswith(".log") and ".audit_output" not in f and ".clean_control" not in f:
            verdict = "UNKNOWN"
            for ln in open(os.path.join(ld, f), errors="replace"):
                if ln.startswith("NEGTEST "):
                    verdict = ln[len("NEGTEST "):].strip()
            per.append({"log": f, "verdict_line": verdict})
json.dump({"passed": npass, "total": ntot,
           "all_passed": npass == ntot and ntot > 0,
           "per_log": per}, open(out, "w"), indent=2)
EOF
}
