# Round 3 Limitations, Deviations and Coverage Gaps

## Documented deviations from the historical (Rounds 1–2) protocol

1. **Rust extensions not built.** `SGLANG_BUILD_RUST_EXTS=none` in all three
   arms: crates.io is unreachable through the lab egress proxy and the tested
   workload (text-only Qwen3-0.6B serving, triton attention backend) never
   imports `sglang-mm` / the gRPC rust extension. Applied arm-symmetrically;
   disclosed here. The historical rounds did build them; if a future workload
   needs the multimodal pipeline this environment differs.
2. **sgl_kernel built once, installed into all arms.** The `kernels/aot`
   subtree is byte-identical between `cbbc6b6` and `1da9ae2` (verified by git
   tree comparison and recorded in `evidence/environment/build_sglkernel.log`),
   so one gfx1100 AOT build (upstream tree + the repo's documented
   `patches/sgl-kernel-gfx1100.sh` wave32 patch) was installed into all three
   venvs from the identical wheel (sha256 recorded). sgl_kernel is not on the
   attention hot path under test.
3. **Local model path.** The model is served from the pinned local download
   (`round3-work/dl/qwen3-06b`, revision `c1899de2…`, sha256 per file in the
   download manifest) instead of the HF repo id, to remove network influence.
   All arms use the identical path.
4. **Bench client runs from the arm venv** (as in Rounds 1–2): the client is
   `python -m sglang.benchmark.serving` of each arm's own revision. Between
   `cbbc6b6` and `1da9ae2` the bench module differs only by the same tree; any
   client-side effect is part of the arm identity being compared.
5. **GSM8K dataset fetch shim (eval venv only).** sgl-eval's vendored prepare
   downloads the dataset from raw.githubusercontent.com, which the lab egress
   proxy refuses (identical condition documented in Rounds 1–2). A shim in
   `venv_eval` (never in the serving arms) serves the locally pre-fetched
   openai/grade-school-math test split
   (sha256 `3730d312…`, 1319 lines); the resulting transformed dataset sha256
   `67e9046d…` **matches the historical campaign's recorded value exactly**,
   proving dataset identity.
6. **`random_seed` excluded from server-config symmetry check.** sglang draws
   a fresh server seed at every launch (same policy on all arms); the audit
   treats it as a known per-launch field. Every other effective server_args
   field is byte-identical within each cell across arms (audited).
7. **GSM8K truncation.** At the pinned 1024-token cap (historical A_full
   setting) Qwen3-0.6B truncates ~52–53% of answers on both arms; scores are
   therefore cap-dependent and cross-round baseline movement of ~2.5pp was
   observed. No formal equivalence claim is made from p=0.10.

## Statistical caveats

- Same-runno pairing (cycle-position pairing) is used for the log-ratio CIs;
  ABBA/BAAB orientation alternation cancels run-order drift to first order.
- At c=1 the historical protocol measures a single request (~2 s window). The
  sustained c=1 experiment (32 sequential prompts) is the primary
  variance-controlled c=1 measurement; the two are never pooled.
- decode ms/step is NOT re-derived in Round 3 from `Decode batch` log lines
  (author-methodology from the PR body); inter-token latency from the bench
  client is used instead. No kernel-level speedup is inferred from total
  throughput; kernel behavior is established by the physical launch capture.
- Geometric-mean ratios with n pairs have wide CIs at n=2..3; verdicts below
  treat CI-overlaps accordingly (see FINAL_REPORT.md uncertainty section).

## Confounders

- Single GPU, sequential legs; temperature/power drift monitored via per-leg
  telemetry (recorded). On the very short one-wave legs (c=1: ~2 s bench
  window) at most 1–2 telemetry samples fall inside the measured window —
  telemetry is supplementary there; the sustained c=1 and high-concurrency
  legs carry the thermal/state evidence.
- **c=4 first-use stall:** the first measured leg per arm in the c4 cell paid
  a ~1.1 s TTFT stall (vs ~57 ms median) on all three arms — arm-symmetric,
  first-use-only. Pre-declared outlier rule (TTFT > 5× cell median) flags
  exactly these three legs; medians are robust and paired CIs are reported
  raw AND trimmed (statistics.json `ttft_outliers`).
- No co-tenant GPU processes were present during the campaign (admission
  check at start; spot-checked between cells).
- CUDA-graph capture pads batches to captured sizes; the gate decides per
  captured graph. The physical capture proves decisions for kernel batches
  1..64; served concurrency maps to captured batch buckets (1,2,4,8,...),
  which the cell concurrency grid exercises directly.
- `torch.multi_processor_count` = 48 (WGP-pair view on gfx1100 in this ROCm)
  while `rocminfo` reports 96 CUs. The gate scales "as a ratio", per the
  maintainer; the W7900 threshold is 19 with 48. If a future ROCm changes the
  reported count to 96, the threshold becomes 38 and batch≤4 would keep hints —
  this environment-dependence is inherent to the PR's design and is flagged as
  a coverage note for upstream, not a defect of this validation.
- Deterministic-serving retry: both arms fail at startup with the historical
  LDS limit (required 99,328 B > hardware 65,536 B) → BLOCKED with fresh
  round-3 provenance (`evidence/accuracy/determinism_r3/`). Same blocker as
  Rounds 1–2 on the same host stack; no new claim is made.

## Coverage gaps

- Model B (Qwen2.5-3B) and long-context/mixed cells from Rounds 1–2 were not
  re-run (the maintainer's request targets Qwen3-0.6B low concurrency; high
  concurrency non-regression is covered at c=16/32/64).
- Only the `triton` attention backend (as in Rounds 1–2 and the PR's scope).
- gfx1151/gfx1201 hardware not available in this lab (PR-authored parts);
  the 20-core threshold-8 equivalence is only source-verified via the upstream
  unit tests, not measured.
