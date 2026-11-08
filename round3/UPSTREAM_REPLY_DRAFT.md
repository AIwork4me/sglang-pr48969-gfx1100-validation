### W7900 (gfx1100) validation of the scaled tiny-grid threshold @ 1da9ae2

Re-ran Qwen3-0.6B (16/8 heads, head_dim 128 → head_tiles 8) on Radeon PRO W7900 per your request, concurrency 1/2/4/8, plus 16/32/64 non-regression, on a three-arm build (merge-base / fixed-8 revert / 1da9ae2 unmodified).

**Reported core count:** the runtime reports `multi_processor_count = 48` on W7900 (rocminfo shows 96 CUs; HIP exposes the WGP-pair count on this stack), so `current_arch().num_sms = 48` and the threshold is `max(8, 8*48//20) = 19`.

**Measured gate behavior (physical Triton launch capture):** batch 1–2 (8, 16 < 19) keep the CDNA hints with num_warps=4 — identical to merge-base; batch ≥ 4 (32 ≥ 19) drop the hints with num_warps=2 — identical to the fixed gate. head_dim-256/MLA/fp8-KV exclusions unchanged.

**Throughput (output tok/s, median, i1024/o256/range1/seed1, fresh server per leg, ABBA):**

| c | merge-base | fixed-8 (revert) | 1da9ae2 |
|---|---|---|---|
| 1 | 132.8 | 130.4 (0.982x) | 132.4 (0.998x) |
| 2 | 240.9 | 240.9 | 240.0 |
| 4 | 455.1 | 455.1 | 454.5 |
| 8 | 801.7 | 839.3 | 838.6 |
| 16 | 1182.1 | — | 1310.5 |
| 32 | 1635.9 | — | 1902.3 |
| 64 | 1715.6 | — | 2257.0 |

The c=1 single-wave regression is gone (new/main 0.9961 [0.9932, 0.9991] (n=6) with the fixed-8 revert simultaneously ~0.98x, matching the 0.98x you measured), c=2 keeps the hints path, and c=16–64 keep the hint-free gains. A 32-sequential-prompt sustained c=1 run and kernel-level A/B correctness (17 fixed-seed geometries vs fp32 reference) agree; full evidence, per-leg telemetry and a CPU-only audit are in the validation repo.

Links: [validation repo](https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation) — `round3/` (see `round3/README.md`, `round3/FINAL_REPORT.md`, `round3/audit/VALIDATION_CERTIFICATE.md`).
