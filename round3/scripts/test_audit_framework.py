#!/usr/bin/env python3
"""Unit tests for the round3.1 negative-test framework itself.

Covers the failure modes that previously produced false PASS verdicts:
  S1  Clean Control failing  -> a negative test must NEVER report PASS;
  S2  injection not applied  -> verdict must be FAIL:injection_failed;
  S3  non-target gate firing -> must not substitute for the expected gate;
  S4  injection applied but audit accepts -> FAIL:audit_accepted;
  S5  standard BLOCKED must not be impersonatable as PASS (status audit);
  S6  manifest missing / file-hash mismatch must trigger rejection.

Exits nonzero if any scenario fails. CPU-only; uses disposable snapshots."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
LIB = os.path.join(HERE, "negtest_lib.sh")
WORK = tempfile.mkdtemp(prefix="r31-fwtest.", dir=os.environ.get("FWTEST_TMPDIR") or None)
RESULTS = []


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def snapshot(dst):
    os.makedirs(dst, exist_ok=True)
    r = run(["bash", "-c",
             f'git -C "{REPO}" archive --format=tar HEAD | tar -x -C "$0"', dst])
    assert r.returncode == 0, r.stderr
    return dst


def drive_negtest(scenario_id, desc, gate, targets, fn_name, hook=None, fn_body=""):
    """Run one negtest in a fresh bash process; return its verdict line."""
    script = f'''
source "{LIB}"
trap negtest_cleanup EXIT
{fn_body}
'''
    if hook:
        script += f'NEGTEST_FIXTURE_HOOK="{hook}"\n'
    script += (f'negtest {scenario_id} "{desc}" {gate} "{targets}" {fn_name}\n'
               f'echo "RC_$?"\n')
    r = run(["bash", "-c", script], env={**os.environ, "NEGTEST_TMPROOT":
            os.path.join(WORK, f"tmp_{scenario_id}")})
    verdict = ""
    for ln in r.stdout.splitlines():
        if ln.startswith(f"NEGTEST {scenario_id} "):
            verdict = ln.split(" ", 2)[2]
    return verdict, r.stdout, r.stderr


def check(sid, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + sid + (f" :: {detail}" if detail else ""))
    RESULTS.append((sid, bool(cond)))


def s1_clean_control_gate():
    hook = os.path.join(WORK, "s1_hook.sh")
    with open(hook, "w") as fh:
        fh.write('''#!/usr/bin/env bash
root="$1"
rm -f "$root/round3/results/gate_matrix.json"
m="$root/round3/audit/SHA256SUMS"
grep -v "  round3/results/gate_matrix.json$" "$m" > "$m.tmp" && mv "$m.tmp" "$m"
''')
    v, out, err = drive_negtest(
        "S1", "clean control broken (gate_matrix removed + unlisted)",
        "manifest_no_duplicates", "round3/audit/SHA256SUMS", "corrupt_N05",
        hook=hook)
    check("S1_clean_control_failure_never_reports_negative_PASS",
          v == "FAIL:clean_control_failed", f"verdict={v!r}")


def s2_injection_failed():
    v, out, err = drive_negtest(
        "S2", "corruption function that changes nothing",
        "manifest_verifies", "round3/README.md", "corrupt_noop",
        fn_body='''corrupt_noop() { NEGTEST_TARGETS=("round3/README.md"); return 0; }''')
    check("S2_unapplied_injection_is_FAIL", v == "FAIL:injection_failed",
          f"verdict={v!r}")


def s3_wrong_gate():
    v, out, err = drive_negtest(
        "S3", "N05 duplicate-line corruption but WRONG expected gate",
        "manifest_verifies", "round3/audit/SHA256SUMS", "corrupt_N05")
    check("S3_non_target_gate_cannot_substitute", v == "FAIL:target_gate_not_hit",
          f"verdict={v!r}")


def s4_audit_accepted():
    v, out, err = drive_negtest(
        "S4", "undetectable doc append (audit accepts) must not yield PASS",
        "manifest_verifies", "round3/LIMITATIONS.md", "corrupt_accepted",
        fn_body='''corrupt_accepted() {
  local f="round3/LIMITATIONS.md"
  NEGTEST_TARGETS=("$f")
  printf '\\n_round3.1 audit-acceptance probe (framework unit test S4)_\\n' >> "$TEST_ROOT/$f" || return 1
  grep -q "audit-acceptance probe" "$TEST_ROOT/$f" || return 1
  negtest_rehash "$TEST_ROOT" "$f"
}''')
    check("S4_accepted_corruption_is_FAIL", v == "FAIL:audit_accepted",
          f"verdict={v!r}")


def s5_blocked_impersonation():
    fx = os.path.join(WORK, "s5_fixture", "round3")
    os.makedirs(os.path.join(fx, "audit"), exist_ok=True)
    shutil.copy(os.path.join(REPO, "round3/audit/VALIDATION_CERTIFICATE.json"),
                os.path.join(fx, "audit"))
    shutil.copy(os.path.join(REPO, "round3/audit/verdicts.json"),
                os.path.join(fx, "audit"))
    dst_ev = os.path.join(fx, "evidence/accuracy/determinism_r3")
    os.makedirs(dst_ev, exist_ok=True)
    for f in os.listdir(os.path.join(REPO, "round3/evidence/accuracy/determinism_r3")):
        shutil.copy(os.path.join(REPO, "round3/evidence/accuracy/determinism_r3", f), dst_ev)
    cert_p = os.path.join(fx, "audit/VALIDATION_CERTIFICATE.json")
    cert = json.load(open(cert_p))
    t = cert["tests"]["deterministic_serving_retry"]
    assert t["status"] == "BLOCKED"
    t["status"] = "PASS"
    t.pop("reason", None)
    json.dump(cert, open(cert_p, "w"), indent=2)

    env = {**os.environ, "AUDIT_R3_ROOT": fx}
    r = run([sys.executable, os.path.join(HERE, "audit_status_integrity.py")], env=env)
    ok = r.returncode != 0 and "FAIL certificate_matches_verdicts" in r.stdout \
        and "FAIL pass_not_contradicted_by_raw_verdicts" in r.stdout
    check("S5_blocked_cannot_be_forged_as_PASS", ok,
          f"rc={r.returncode}; stdout[:400]={r.stdout[:400]!r}")


def s6_manifest_rejection():
    snap_a = snapshot(os.path.join(WORK, "s6a"))
    os.remove(os.path.join(snap_a, "round3/audit/SHA256SUMS"))
    ra = run(["bash", os.path.join(snap_a, "round3/scripts/audit_round3.sh")])
    ok_a = ra.returncode != 0 and "FAIL manifest_exists" in ra.stdout

    snap_b = snapshot(os.path.join(WORK, "s6b"))
    tgt = os.path.join(snap_b, "round3/evidence/performance/c1/bench_main_r1.json")
    with open(tgt, "ab") as fh:
        fh.write(b"\x00")
    rb = run(["bash", os.path.join(snap_b, "round3/scripts/audit_round3.sh")])
    ok_b = rb.returncode != 0 and "FAIL manifest_verifies" in rb.stdout
    check("S6_manifest_missing_and_hash_mismatch_rejected", ok_a and ok_b,
          f"missing->rc={ra.returncode}; hash->rc={rb.returncode}")


def main():
    print("== round3.1 negative-test framework unit tests ==")
    print(f"work dir: {WORK}")
    s1_clean_control_gate()
    s2_injection_failed()
    s3_wrong_gate()
    s4_audit_accepted()
    s5_blocked_impersonation()
    s6_manifest_rejection()
    shutil.rmtree(WORK, ignore_errors=True)
    bad = [sid for sid, ok in RESULTS if not ok]
    print(f"== framework unit tests: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS ==")
    if bad:
        print("FRAMEWORK UNIT TESTS FAIL:", bad)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
