### W7900 (gfx1100) validation of the scaled tiny-grid threshold @ 1da9ae2

Re-ran Qwen3-0.6B (16/8 heads, head_dim 128 → head_tiles 8) on Radeon PRO W7900 per your request, concurrency 1/2/4/8, plus 16/32/64 non-regression, on a three-arm build (merge-base / fixed-8 revert / 1da9ae2 unmodified).

**Reported core count:** the runtime reports `multi_processor_count = 48` on W7900 (rocminfo shows 96 CUs; HIP exposes the WGP-pair count on this stack), so `current_arch().num_sms = 48` and the threshold is `max(8, 8*48//20) = 19`.

**Measured gate behavior (physical Triton launch capture):** batch 1–2 (8, 16 < 19) keep the CDNA hints with num_warps=4 — identical to merge-base; batch ≥ 4 (32 ≥ 19) drop the hints with num_warps=2 — identical to the fixed gate. head_dim-256/MLA/fp8-KV exclusions unchanged.

**Throughput (output tok/s, median, i1024/o256/range1/seed1, fresh server per leg, ABBA):**

| c | merge-base | fixed-8 (revert) | 1da9ae2 |
|---|---|---|---|
| 1 | 132.8 | 130.4 (0.982x) | 132.4 (0.996x paired) |
| 2 | 240.9 | 240.9 | 240.0 |
| 4 | 455.1 | 455.1 | 454.5 |
| 8 | 801.7 | 839.3 | 838.6 |
| 16 | 1182.1 | — | 1310.5 |
| 32 | 1635.9 | — | 1902.3 |
| 64 | 1715.6 | — | 2257.0 |

**Headline c=1 conclusion:** the previously observed ~2% c=1 regression is substantially mitigated. The sustained c=1 workload is near parity, with the original launch configuration restored (new/main 0.9961 [0.9932, 0.9991] one-wave; 0.9992 [0.9969, 1.0016] sustained ×32; 1.0011 [0.9964, 1.0059] at mem-frac 0.30 — the fixed-8 revert is ~0.98x in all three, matching the 0.98x you measured). We do not claim exact mathematical equivalence. c=2 retains a small ~0.56% residual (0.9944 [0.9908, 0.9980], CI excludes 1.0). c=4 is disclosed both untrimmed (0.9856 [0.9633, 1.0085]) and after the pre-registered first-use TTFT-stall trim (0.9972 [0.9938, 1.0005]; 3 legs, arm-symmetric). c=16–64 keep the hint-free gains (figures are end-to-end output throughput, not pure kernel speedup). A 32-sequential-prompt sustained c=1 run and kernel-level A/B correctness (17 fixed-seed geometries vs fp32 reference, bitwise-identical across arms) agree; full evidence, per-leg telemetry and a CPU-only audit (integrity + independent recompute + 10 verified negative tests) are in the validation repo. Deterministic-serving retry remains BLOCKED on both arms (LDS 99,328B > 65,536B).

Links: [validation repo](https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation) — `round3/` (see `round3/README.md`, `round3/FINAL_REPORT.md`, `round3/audit/VALIDATION_CERTIFICATE.md`).
