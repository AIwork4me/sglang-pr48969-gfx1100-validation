# Round 3 — W7900 physical validation of SGLang PR #48969 @ 1da9ae2

Third-round independent validation of [sgl-project/sglang PR #48969](https://github.com/sgl-project/sglang/pull/48969)
("[Perf] [AMD] decode-attention: Skip the CDNA launch hints on RDNA3/3.5/4 for GQA decode"),
specifically maintainer **@twoask**'s scaled tiny-grid threshold commit `1da9ae2fcba99be22ed756083e1eb505c1cf5afe`:

```python
- if batch * head_tiles < 8:
+ if batch * head_tiles < max(8, 8 * core_count // 20):
```

Primary question: does the scaled threshold eliminate the historical gfx1100 (W7900)
concurrency-1 throughput regression while keeping the high-concurrency gains?

## Headline hardware facts (measured, not assumed)

| quantity | value | source |
|---|---|---|
| device | AMD Radeon Graphics, gfx1100 (Radeon PRO W7900) | `rocminfo`, `gpu_properties.json` |
| rocminfo Compute Units | 96 | `rocminfo` |
| `torch.cuda.get_device_properties(0).multi_processor_count` | **48** | `gpu_properties.json` |
| SGLang `current_arch().num_sms` (at `1da9ae2`) | **48** | `gpu_properties.json` |
| computed new threshold `max(8, 8*48//20)` | **19** | gate evidence |
| Qwen3-0.6B `head_tiles` (16 Q / 8 KV heads) | 8 | physical launch grid `[b, 8, 16]` |

So on W7900 the new gate keeps the CDNA launch hints for kernel batch 1–2
(`8·1, 8·2 < 19`) and drops them for batch ≥ 3. The pre-`1da9ae2` fixed gate (`< 8`)
dropped the hints at **every** batch for this geometry — that is the mechanism of
the historical c=1 regression.

## Three arms

| arm | source | tree | role |
|---|---|---|---|
| `main` | `cbbc6b67f48008a8b739f4667d7b14abb89088cf` (PR merge base) | `da0fbfed…` | upstream reference |
| `old_gate` | `1da9ae2` + one-line revert of the scaled threshold to fixed `8` | `9a35c22b…` + 1 line | reproduce the defect |
| `new_gate` | `1da9ae2` **unmodified** (native gfx1100 support; no local gate patch) | `9a35c22b…` | the maintainer's fix |

`old_gate` vs `new_gate` differ by exactly one source line (verified at extraction
and re-verified by the audit): `evidence/source/old_vs_new.diff`.

## Layout

```
round3/
  README.md            this file
  TEST_PLAN.md         the executed test plan with statuses
  FINAL_REPORT.md      Chinese final report (mission deliverable)
  LIMITATIONS.md       deviations, confounders, coverage gaps
  scripts/             every script that ran (GPU + CPU-audit)
  configs/             campaign configuration
  evidence/
    environment/       host/ROCm/GPU snapshots, env setup + build logs
    source/            arm commits, tree SHAs, inter-arm diffs, wheel hash
    gate/              gate unit tests + physical launch-capture verdicts per arm
    performance/       raw bench JSON/logs/telemetry per leg + order.jsonl
    kernel/            kernel A/B correctness artifacts
    accuracy/          GSM8K artifacts (or NOT_RUN record)
  results/             derived data: per_leg.csv, performance_summary.csv,
                       statistics.json, gate_matrix.json
  audit/               audit_report.{json,md}, negative_tests.log, SHA256SUMS,
                       baseline_freeze.sha256, VALIDATION_CERTIFICATE.{json,md}
  UPSTREAM_REPLY_DRAFT.md
```

## Reproduce the audit (CPU only, fresh clone)

```bash
bash round3/scripts/audit_round3.sh            # integrity + recompute + symmetry
bash round3/scripts/audit_round3.sh --selftest # negative tests on disposable copies
```

GPU experiments are documented in `TEST_PLAN.md`; every leg's raw JSON, client
log, server log and GPU telemetry are archived under `evidence/performance/`.
`evidence/performance/_smoke/` is a single pre-grid pipeline-validation leg
(new arm, c=1) — not part of any measured cell and excluded from all results.

## Leg schedule (pairing semantics)

Within a cell, legs with the **same run number** are consecutive positions of the
same A/B cycle (r1: A then B; r2: B then A), so same-runno pairing is
cycle-position pairing. Cycles alternate orientation (ABBA, BAAB, ABBA).
The exact global execution order is `evidence/performance/order.jsonl`.

## Headline results (see FINAL_REPORT.md for full statistics)

- **c=1 sustained (32 prompts):** new/main = 0.9992 [0.9969, 1.0016] — parity;
  fixed-8 revert simultaneously at ~0.983x (the historical regression, and the
  0.98x @twoask measured on this part).
- **c=1 one-wave:** new/main = 0.9961 [0.9932, 0.9991]; old = 0.9825x.
- **c=1 mem-frac 0.30:** new/main = 1.0011 [0.9964, 1.0059].
- **c=8:** new/main = 1.0454 [1.0423, 1.0486]; **c=16/32/64:** 1.109 / 1.163 /
  1.316 — high-concurrency gains preserved.
- **Kernel outputs:** 17/17 cases bitwise identical across all three arms.
