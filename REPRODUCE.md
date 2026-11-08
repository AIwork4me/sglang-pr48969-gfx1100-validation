# REPRODUCE

Reproduction contract for this evidence package, revised in the 2026-11 audit
round to be executable from a clean clone. The original version of this file
referenced uncommitted files under a historical `work/` directory; those
references are now explicitly classified (see §Reproduction tiers).

**Four tiers — do not conflate them:**

| tier | meaning | runnable from clean clone? |
|---|---|---|
| T1 Historical exact execution | what actually ran on the W7900 on 2026-11-07 (campaign root `/root/sglang-pr48969-validation`, uncommitted `work/`) | **No** — GPU + historical env; partially reconstructible |
| T2 Current supported reproduction | rerun the campaign with the committed scripts (GPU required) | Yes, on a gfx1100 + ROCm 7.2 host (see §2) |
| T3 Analysis-only reproduction | recompute every number in `results/` from the committed raw evidence (CPU only) | **Yes** — `bash scripts/audit_local.sh` |
| T4 GPU validation required | open questions that need new GPU work | No — listed in LIMITATIONS.md |

Nothing in this repository requires a GPU to *audit*: tier T3 below verifies
every published number against the raw artifacts.

## 1. Sources (T2 precondition)

```bash
mkdir -p work/dl
# GitHub tarballs (the lab egress proxy throttles git to ~45KB/s; tarballs resume by restart)
for sha in 0afb736d0aab96e3ab80b4c54a376213a1db67a6 \
           3fdf6f7318364c1b09398aea4d947ed633ac9eca \
           025b8806ddd6f6c36722305820dc31db765dfb4f; do
  bash scripts/dl_tarball.sh "$sha" "work/dl/$sha.tar.gz" || exit 1
done
mkdir -p work/src_main work/src_pr
tar -xzf work/dl/0afb736*.tar.gz -C work/src_main --strip-components=1 || exit 1
tar -xzf work/dl/3fdf6f7*.tar.gz  -C work/src_pr  --strip-components=1 || exit 1
# verify byte-identity against GitHub's trusted tree API (git blob SHA-1 per file)
gh api "repos/sgl-project/sglang/git/trees/<sha>?recursive=1" > evidence/source/tree_<arm>.json
python3 scripts/verify_source.py evidence/source/tree_main.json work/src_main || exit 1
python3 scripts/verify_source.py evidence/source/tree_pr.json   work/src_pr   || exit 1
```

Historical note (T1): the tarball SHA256s actually used are recorded in
`evidence/checksums/sources.sha256` (`work/dl/*.tar.gz`, lab-local, not
committed — they cannot be re-verified from a clone; recorded as a
reproduction gap, see `audit/BASELINE_INVENTORY.md` §4).

## 2. Environments (T2; one per arm, identical dependency set)

Preconditions: Ubuntu 24.04 host with ROCm 7.2.1 at `/opt/rocm-7.2.1`, host
torch 2.9.1+gitff65f5b (rocm7.21) venv at `/opt/venv` (see ENVIRONMENT.md —
this replicates `docker/rocm-gfx1151.Dockerfile`, which was the closest
official recipe; no nested Docker was available in the lab).

```bash
bash scripts/audit_environment.sh evidence/environment   # environment evidence (needs rocm-smi/rocminfo)
bash scripts/setup_env.sh main    # venv + flat ROCm deps + editable sglang
bash scripts/setup_env.sh pr
# Triton 3.6 (required by this sglang revision):
pip install https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2/triton-3.6.0%2Brocm7.2.0.gitba5c1517-cp312-cp312-linux_x86_64.whl || exit 1
# sgl_kernel AOT for gfx1100 (official gfx1151 wave32 patch adapted):
bash scripts/build_sglkernel.sh main
bash scripts/build_sglkernel.sh pr
# venv-local shims (see ENVIRONMENT.md). The committed copies are in scripts/;
# copy them into each arm venv:
for ARM in main pr; do
  cp scripts/aiter_compat_shim.py scripts/norm_compat.py "work/venv_${ARM}/lib/python3.12/site-packages/" || exit 1
  printf 'import aiter_compat_shim\nimport norm_compat\n' > "work/venv_${ARM}/lib/python3.12/site-packages/zz_aiter_shim.pth"
done
```

**Reproduction gaps (T1 → T2), stated honestly:**

1. `work/run_final.sh` (the grid orchestrator that drove the historical serving
   cells) was never committed. The per-cell invocations *are* reconstructible
   from the first line of each `evidence/performance/*/runner.log`, but the
   orchestrator itself is not byte-reproducible.
2. The historical scripts executed `$CAMP/work/launch_server.sh`,
   `$CAMP/work/build_sglkernel.sh`, `$CAMP/work/aiter_compat_shim.py`,
   `$CAMP/work/norm_compat.py` and `$CAMP/work/launch_server_instrumented.py`.
   The committed `scripts/` copies are equivalent in function (the server
   command lines they generate match the archived `server_*.log`
   `launch_command` fields exactly — this equivalence is *checked* by Audit V2),
   but byte-identity with the executed `work/` files cannot be proven because
   `work/` was not committed.
3. `work/venv_eval` (sgl-eval 0.1.3) and the arm venvs are not committable;
   recreate via `scripts/setup_env.sh` + pip install sgl-eval==0.1.3.
4. The GSM8K runner script that produced the archived 1024-max-tokens A runs is
   **not the committed script**: the committed pre-audit version hardcoded
   `--max-tokens 2048`. The current version parameterizes it (arg 6 /
   `SGLANG_EVAL_MAX_TOKENS`, fail-closed). See
   `evidence/accuracy/EXECUTION_MANIFEST.md` for the per-run ground truth
   recorded in each `metrics.json`.

## 3. Gate patch (T2; PR arm only)

```bash
# applied already in the campaign; re-apply on a pristine tree:
(cd work/src_pr && patch -p1 < ../../patches/pr48969-gfx1100-validation.patch) || exit 1
# the exactly-applied diff is archived: patches/pr48969-gfx1100-validation.applied.diff
```

## 4. Kernel correctness A/B (T2; GPU required)

```bash
work/venv_pr/bin/python  scripts/kernel_ab.py gate      || exit 1
for ARM in main pr; do
  work/venv_$ARM/bin/python scripts/kernel_ab.py capture   > evidence/kernel/capture_${ARM}.json || exit 1
  work/venv_$ARM/bin/python scripts/kernel_ab.py reference evidence/kernel/ref_${ARM}            || exit 1
done
work/venv_main/bin/python scripts/kernel_ab.py compare evidence/kernel/ref_main evidence/kernel/ref_pr evidence/kernel/cross_arm_compare.json || exit 1
work/venv_pr/bin/python  scripts/regression_gates.py evidence/regression/arch_gates.json || exit 1
```

(The pre-audit REPRODUCE.md wrote `work/venv_<arm>/python`, which is not the
venv executable path — corrected to `bin/python`.)

## 5. Serving A/B (T2; per concurrency; ABBA, warmup-separated)

```bash
bash scripts/run_serving_ab.sh A 16 1024 256 1 0.75 A_c16 100000 || exit 1
# Full formal grid (15 cells), reconstructed from runner.log first lines:
#   A: c 1/4/8/16/32/64 (maxtok 100000), long 4k/8k @c8, mixed c16/c32 (maxtok 100000)
#   B: c 16/32/64 (maxtok 260000), long 8k @c8, mixed c16 (maxtok 260000)
# The 16th cell, _pilot4x_A_c16 (memfrac 0.30, 4x prompts), is a PILOT, not formal.
python3 scripts/collect_metrics.py || exit 1   # -> results/performance_raw.csv + decode ms/step series
work/venv_pr/bin/python scripts/analyze.py     # summaries + plots (needs matplotlib)
```

All runner scripts now default the campaign root to this repository and accept
`SGLANG_VALIDATION_ROOT` / `SGLANG_VALIDATION_WORK` overrides (historical
values: `/root/sglang-pr48969-validation` and its `work/`). Bench and eval
failures abort the cell (fail-closed) — the pre-audit versions logged the
return code and continued.

## 6. GSM8K (T2; sgl-eval 0.1.3, own venv, per repo policy)

```bash
# eval max-tokens is an EXPLICIT parameter (fail-closed). Historical values
# (memfrac / server max-total-tokens per pair, from the archived server logs —
# see configs/eval_config.yaml and evidence/accuracy/EXECUTION_MANIFEST.md):
bash scripts/run_gsm8k_ab.sh A 0.30 gsm8k_A_diag       200  0      1024 || exit 1
bash scripts/run_gsm8k_ab.sh A 0.30 gsm8k_A_full      1319  0      1024 || exit 1
bash scripts/run_gsm8k_ab.sh A 0.75 gsm8k_A_full_2048 1319  100000 2048 || exit 1
bash scripts/run_gsm8k_ab.sh B 0.75 gsm8k_B_diag       200  260000 2048 || exit 1
bash scripts/run_gsm8k_ab.sh B 0.75 gsm8k_B_full      1319  260000 2048 || exit 1
```

## 7. Analysis + audit (T3; CPU-only — run this from a clean clone)

```bash
bash scripts/audit_local.sh            # runs everything below, checks exit codes
```

which executes:

```bash
python3 -m py_compile scripts/*.py                     # syntax
bash -n scripts/*.sh                                   # shell syntax
python3 scripts/verify_reproduction_paths.py           # every doc/script path reference resolves (fail-closed)
python3 scripts/verify_evidence_v2.py                  # independent evidence audit (V2), fail-closed
python3 -m pytest tests -q                             # auditor regression tests (pure CPU, fixtures)
sha256sum -c evidence/checksums/SHA256SUMS             # raw-evidence integrity vs the sealed manifest
                                                       # (expected mismatches: files legitimately repaired
                                                       #  this round — listed in audit/SHA256SUMS_AUDIT_ROUND)
```

Sealing a new manifest (what the historical unfinished placeholder command in
this section was meant to be):

```bash
find results evidence plots configs -type f -print0 | sort -z | xargs -0 sha256sum > evidence/checksums/SHA256SUMS
```

The historical manifest (`evidence/checksums/SHA256SUMS`, 676 files) was
sealed 2026-11-07 and is preserved; this audit round's additions/repairs are
recorded in the separate `audit/SHA256SUMS_AUDIT_ROUND` (never self-including,
no circular references, historical raw evidence untouched).

## 8. What each tier can and cannot claim

- T3 (CPU audit) reproduces **all published numbers**: throughput medians,
  speedups, decode ms/step, ITL/TTFT, GSM8K scores/truncation, kernel
  equality counts, launch-capture claims, source-integrity verdicts.
- T2 re-runs the campaign; results are expected to differ run-to-run within
  the spreads documented in LIMITATIONS.md L7 (throughput 0.0–3.0%,
  ms/step 0.03–3.2%, most cells ≤0.7%) — a T2 rerun is not expected to be bit-identical to T1.
- T1 is only partially reconstructible (§2 gaps); the archived raw logs under
  `evidence/` are the authoritative record of what actually executed.
