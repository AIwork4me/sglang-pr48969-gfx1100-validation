# Round 3 Test Plan — executed on the physical W7900 (gfx1100)

All GPU tests ran on the single Radeon PRO W7900 of the lab host
(ROCm 7.2.1, torch 2.9.1+gitff65f5b HIP 7.2.53211, Triton 3.6.0+rocm7.2.0),
2026-11-08. Statuses: PASS / FAIL / BLOCKED / NOT_RUN.

## Phase 0 — baseline freeze and hardware admission

| # | test | status | evidence |
|---|---|---|---|
| 0.1 | host/ROCm/GPU read-only snapshot | PASS | `evidence/environment/host_rocm_snapshot.txt` |
| 0.2 | runtime GPU properties incl. `multi_processor_count` | PASS | `evidence/environment/gpu_properties.json` |
| 0.3 | resource admission (VRAM free, no co-tenant GPU procs) | PASS | `host_rocm_snapshot.txt` (`rocm-smi --showpids`: none) |
| 0.4 | upstream PR head == pinned `1da9ae2` (GitHub API) | PASS | `evidence/source/arm_commits.txt` |
| 0.5 | historical evidence frozen (baseline SHA256) | PASS | `audit/baseline_freeze.sha256` |

## Phase 1 — three-arm source integrity

| # | test | status | evidence |
|---|---|---|---|
| 1.1 | `new_gate` == upstream `1da9ae2` tree, no local patch | PASS | `evidence/source/arm_commits.txt`, `main_vs_new.diff` |
| 1.2 | `old_gate` differs by exactly the one threshold line | PASS | `evidence/source/old_vs_new.diff` (2 diff lines) |
| 1.3 | sgl_kernel AOT: source identical across arms + documented gfx1100 patch only | PASS | `evidence/environment/build_sglkernel.log`, `evidence/source/sglkernel_wheel.sha256` |
| 1.4 | environments: identical dependency set, torch, Triton per arm | PASS | `evidence/environment/setup_env_*.log` |

## Phase 1b — gate verification (source + physical)

| # | test | status | evidence |
|---|---|---|---|
| 1.5 | upstream unit test `test_rdna_decode_launch.py` on `new_gate` | PASS (7/7) | `evidence/gate/upstream_unit_test_new_arm.txt` |
| 1.6 | upstream unit test on `old_gate` — must FAIL the scaled-core-count case | PASS (fails as expected: 1 failed) | `evidence/gate/upstream_unit_test_old_arm.txt` |
| 1.7 | gate matrix + physical launch capture, all arms | PASS | `evidence/gate/gate_{main,old,new}.json`, `results/gate_matrix.json` |
| 1.8 | exclusions preserved (MLA/fp8-KV/hd256/fp32) | PASS | `gate_*.json` `excl_*` checks |

## Phase 2 — serving A/B (fresh server per leg, warmup before every measured run)

| # | test | status | evidence |
|---|---|---|---|
| 2.1 | c=1 Main/New 3 ABBA cycles (6+6 legs) | see certificate | `evidence/performance/c1/` |
| 2.2 | c=2, c=4, c=8 Main/New 3 ABBA cycles each | see certificate | `evidence/performance/{c2,c4,c8}/` |
| 2.3 | c=1,2,4,8 Old/New 2 ABBA cycles each | see certificate | same cells |
| 2.4 | sustained c=1 (32 sequential prompts) Main/New ×2 + Old/New ×1 | see certificate | `evidence/performance/sustained_c1/` |
| 2.5 | c=16/32/64 Main/New 1 ABBA cycle each | see certificate | `evidence/performance/{c16,c32,c64}/` |
| 2.6 | c=1 mem-fraction 0.30 auto-KV, all arms symmetric | see certificate | `evidence/performance/memfrac030_c1/` |

Configuration (identical to Rounds 1–2): `--attention-backend triton
--context-length 10240 --mem-fraction-static 0.75 --max-total-tokens 100000`,
`SGLANG_DISABLE_LEAN_ATTENTION=1`, `SGLANG_USE_AITER=0`,
random dataset input 1024 / output 256 / range-ratio 1, seed 1.
Bench client = `python -m sglang.benchmark.serving` from the arm venv (as in Rounds 1–2).

## Phase 3 — correctness and boundaries

| # | test | status | evidence |
|---|---|---|---|
| 3.1 | gate/unit tests (1.5–1.8 above) | PASS | `evidence/gate/` |
| 3.2 | kernel A/B vs fp32 reference, all arms (17-case sweep, tolerances unchanged) | see certificate | `evidence/kernel/` |
| 3.3 | cross-arm kernel output comparison (Main vs New, Old vs New) | see certificate | `evidence/kernel/` |
| 3.4 | full GSM8K 1319q, Main + New, identical settings | see certificate | `evidence/accuracy/` |
| 3.5 | deterministic-serving mode retry (historical LDS blocker) | see certificate | `evidence/accuracy/` or `LIMITATIONS.md` |

## Phase 4 — independent analysis

| # | test | status | evidence |
|---|---|---|---|
| 4.1 | recompute per-leg/median/ratios from raw JSON (no trust of summaries) | see certificate | `results/`, `scripts/analyze_r3.py` |
| 4.2 | paired log-ratio CIs; spread; valid-run counts | see certificate | `results/statistics.json` |
| 4.3 | verdict classification per concurrency (RESTORED / REGRESSION_PERSISTS / INCONCLUSIVE / BLOCKED) | see certificate | `FINAL_REPORT.md`, `VALIDATION_CERTIFICATE.json` |

## Phase 6 — independent CPU audit

| # | test | status | evidence |
|---|---|---|---|
| 6.1 | `bash round3/scripts/audit_round3.sh` from fresh clone | see certificate | `audit/audit_report.{json,md}` |
| 6.2 | negative self-tests (tamper/escape/duplicate/fake-PASS/…) | see certificate | `audit/negative_tests.log` |
| 6.3 | historical `scripts/audit_local.sh` | see certificate | `audit/audit_local_round3.log` |

Instrumentation (JIT spy) is used ONLY in gate verification, never during
measured benchmark runs (measured servers launch plain; spy mode is a separate
launch path).
