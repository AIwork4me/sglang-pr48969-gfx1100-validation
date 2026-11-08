# Historical / Pre-repair Failure Evidence (Round 3)

These are **archived pre-repair audit artifacts**, preserved byte-identical for
traceability. They record problems that were real at the time they were
produced; they are NOT the current audit state and must not be read as claims
about the repaired code.

| file | provenance | content |
|---|---|---|
| `audit_report_raw_pre_repair.log` | GPU machine, 2026-11-08T19:40:43Z | Round-3 audit run with three FAILs (`old_new_diff_single_line`, `server_symmetry`, `status_integrity`) from an earlier script/evidence state. All three gates PASS on the sealed post-repair tree; the current full log is `round3/audit/audit_report_raw.log`. |
| `negative_tests_pre_repair.log` | GPU machine, 2026-11-08T19:40Z | Ten false `NEGTEST PASS` lines caused by (a) the `bash -c "$corrupt" "$repo"` `$0`/`$1` parameter bug — corruption scripts saw an empty target dir (`grep: /round3/...: No such file or directory`) and never ran — and (b) an incomplete fixture (`tar cf - round3 configs patches`) whose untampered copy already failed the audit for missing Round 1/2 baseline-freeze inputs, so "audit rejected" never implied "corruption detected". Replaced in R3.1 by `round3/audit/negative_tests.log` + `round3/audit/negative_tests/` (verified injections, expected-gate assertions). |
| `audit_local_round3_gpu_1701.log` | GPU machine, 2026-11-08T17:01Z | Round-1/2 `scripts/audit_local.sh` PASS recorded during the Round-3 campaign. The refreshed run for R3.1 lives at `round3/audit/audit_local_round3.log`. |

The `5a6cee126160cde47ac708efb81e32ae95d49194` commit remains the original
GPU evidence archive; the R3.1 audit-repair commits are separate and do not
re-run or re-seal any GPU measurement.
