# GSM8K Execution Manifest (audit round 2026-11)

Authoritative per-run configuration record for every archived GSM8K pair,
derived from the raw artifacts (metrics.json `gen` blocks and the archived
server logs), not from any script default. Enforced by
`scripts/verify_evidence_v2.py` (checks `acc_settings_perfield_symmetric`,
`acc_maxtok_n_labels_consistent`, `acc_server_memconfig_symmetric_and_manifest`).

The committed `scripts/run_gsm8k_ab.sh` as originally sealed **cannot** have
produced the archived gsm8k_A_diag / gsm8k_A_full runs: it hardcoded
`--max-tokens 2048`, while both archived A runs recorded `max_tokens: 1024` in
their metrics.json (the authoritative record of what executed). The runner.log
first lines additionally show the server launcher being called without the
`$MAXTOK` argument in the A_diag/A_full sessions (13:41–13:57 UTC) and with it
in the B_diag/B_full/A_full_2048 sessions (16:44–17:40 UTC), i.e. the script
was edited mid-campaign and only its final version was committed. The
intermediate script versions were not archived — a documented reproduction gap.

Repairs made in this round (see audit/BASELINE_INVENTORY.md for pre-modification
hashes):
  - `scripts/run_gsm8k_ab.sh`: eval `--max-tokens` is now an explicit, required
    parameter (arg 6 / SGLANG_EVAL_MAX_TOKENS; fail-closed), so the per-run
    value can never be silently hidden again.
  - this file records the per-run ground truth from metrics.json;
    `scripts/verify_evidence_v2.py` enforces per-field Main/PR equality
    (temperature/max_tokens/seed/top_p/num_examples/num_threads) and the
    1024-vs-2048 labeling of every run against metrics.json.

Rerunning each pair faithfully (T2):

```bash
bash scripts/run_gsm8k_ab.sh A 0.30 gsm8k_A_diag       200  0      1024
bash scripts/run_gsm8k_ab.sh A 0.30 gsm8k_A_full      1319  0      1024
bash scripts/run_gsm8k_ab.sh A 0.75 gsm8k_A_full_2048 1319  100000 2048
bash scripts/run_gsm8k_ab.sh B 0.75 gsm8k_B_diag       200  260000 2048
bash scripts/run_gsm8k_ab.sh B 0.75 gsm8k_B_full      1319  260000 2048
```

(The historical A_diag/A_full legs ran at memfrac 0.30 with an auto KV pool —
read from the archived server logs; the explicit `--max-total-tokens` server
argument was introduced in a later, also-unarchived script version. A later
committed script version also hard-coded memfrac per invocation; the archived
runner.log first lines do not echo it, so the server logs are the authoritative
source for these two fields.)
