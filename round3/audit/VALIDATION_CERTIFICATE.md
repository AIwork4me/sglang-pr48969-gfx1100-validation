# Round 3 Validation Certificate

**Run ID:** `round3-1da9ae2-w7900-20261108T1652`  
**Window:** 2026-11-08T16:52:08Z → 2026-11-08T19:33:29Z (UTC)  
**Hardware:** AMD Radeon Graphics (gfx1100), rocminfo CUs 96, `multi_processor_count` **48**, VRAM 48 GiB

**Stack:** torch 2.9.1+gitff65f5b (HIP 7.2.53211-e1a6bc5663), Triton 3.6.0+rocm7.2.0.gitba5c1517, ROCm 7.2.1 (host /opt/rocm-7.2.1)

**Gate:** `current_arch().num_sms` = 48 → threshold = max(8, 8×48//20) = **19**; Qwen3-0.6B head_tiles = 8

| test | status | evidence |
|---|---|---|
| env_snapshot | **PASS** | `round3/evidence/environment/gpu_properties.json` |
| baseline_freeze | **PASS** | `round3/audit/baseline_freeze.sha256` |
| source_integrity | **PASS** | `round3/evidence/source/old_vs_new.diff`, `round3/evidence/source/arm_commits.txt` |
| upstream_unit_test_new | **PASS** | `round3/evidence/gate/upstream_unit_test_new_arm.txt` |
| upstream_unit_test_old_expected_fail | **PASS** | `round3/evidence/gate/upstream_unit_test_old_arm.txt` |
| gate_verify_main | **PASS** | `round3/evidence/gate/gate_main.json` |
| gate_verify_old | **PASS** | `round3/evidence/gate/gate_old.json` |
| gate_verify_new | **PASS** | `round3/evidence/gate/gate_new.json` |
| serving_c1 | **PASS** | `round3/evidence/performance/c1/` |
| serving_c2 | **PASS** | `round3/evidence/performance/c2/` |
| serving_c4 | **PASS** | `round3/evidence/performance/c4/` |
| serving_c8 | **PASS** | `round3/evidence/performance/c8/` |
| serving_sustained_c1 | **PASS** | `round3/evidence/performance/sustained_c1/` |
| serving_c16 | **PASS** | `round3/evidence/performance/c16/` |
| serving_c32 | **PASS** | `round3/evidence/performance/c32/` |
| serving_c64 | **PASS** | `round3/evidence/performance/c64/` |
| serving_memfrac030_c1 | **PASS** | `round3/evidence/performance/memfrac030_c1/` |
| serving_c1_oldgate | **PASS** | `round3/evidence/performance/c1/` |
| serving_c2_oldgate | **PASS** | `round3/evidence/performance/c2/` |
| serving_c4_oldgate | **PASS** | `round3/evidence/performance/c4/` |
| serving_c8_oldgate | **PASS** | `round3/evidence/performance/c8/` |
| serving_memfrac030_c1_oldgate | **PASS** | `round3/evidence/performance/memfrac030_c1/` |
| kernel_reference_correctness | **PASS** | `round3/evidence/kernel/ref_main/reference_results.json` |
| kernel_cross_main_vs_new | **PASS** | `round3/evidence/kernel/cross_main_vs_new.json` |
| kernel_cross_old_vs_new | **PASS** | `round3/evidence/kernel/cross_old_vs_new.json` |
| gsm8k_full_ab | **PASS** | `round3/evidence/accuracy/gsm8k_r3_full/paired_stats.json` |
| deterministic_serving_retry | **BLOCKED** — main: BLOCKED_LDS_LIMIT (server_main.log); new: BLOCKED_LDS_LIMIT (server_new.log) | `round3/evidence/accuracy/determinism_r3/` |

**Counts:** {"PASS": 26, "BLOCKED": 1}  
**Measured valid legs:** {"main": 38, "old": 22, "new": 56}

> Project-generated evidence attestation. NOT an AMD-issued certification and NOT cryptographically signed.
