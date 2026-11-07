# REPRODUCE

Everything below ran as root on the W7900 workstation inside this container.
Approximate wall-clock on a quiet GPU: ~6 h including model downloads.

## 0. Sources
```bash
mkdir -p work/dl
# GitHub tarballs (the lab egress proxy throttles git to ~45KB/s; tarballs resume by restart)
for sha in 0afb736d0aab96e3ab80b4c54a376213a1db67a6 \
           3fdf6f7318364c1b09398aea4d947ed633ac9eca \
           025b8806ddd6f6c36722305820dc31db765dfb4f; do
  curl -L -o work/dl/$sha.tar.gz https://codeload.github.com/sgl-project/sglang/tar.gz/$sha
done
mkdir -p work/src_main work/src_pr
tar -xzf work/dl/0afb736*.tar.gz -C work/src_main --strip-components=1
tar -xzf work/dl/3fdf6f7*.tar.gz  -C work/src_pr  --strip-components=1
# verify byte-identity against GitHub's trusted tree API (git blob SHA-1 per file)
gh api "repos/sgl-project/sglang/git/trees/<sha>?recursive=1" > evidence/source/tree_<arm>.json
python3 scripts/verify_source.py evidence/source/tree_main.json work/src_main
python3 scripts/verify_source.py evidence/source/tree_pr.json   work/src_pr
```

## 1. Environments (one per arm, identical dependency set)
```bash
scripts/audit_environment.sh evidence/environment          # Phase 0 evidence
bash scripts/setup_env.sh main    # venv + flat ROCm deps + editable sglang
bash scripts/setup_env.sh pr
# Triton 3.6 (required by this sglang revision):
pip install https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2/triton-3.6.0%2Brocm7.2.0.gitba5c1517-cp312-cp312-linux_x86_64.whl
# sgl_kernel AOT for gfx1100 (official gfx1151 wave32 patch adapted):
bash work/build_sglkernel.sh main
bash work/build_sglkernel.sh pr
# venv-local shims (see ENVIRONMENT.md):
cp work/aiter_compat_shim.py work/norm_compat.py work/venv_<arm>/lib/python3.12/site-packages/
printf 'import aiter_compat_shim\nimport norm_compat\n' > work/venv_<arm>/lib/python3.12/site-packages/zz_aiter_shim.pth
```

## 2. Gate patch (PR arm only)
```bash
# applied already: patches/pr48969-gfx1100-validation.patch
# re-apply on a pristine tree:
(cd work/src_pr && patch -p1 < ../../patches/pr48969-gfx1100-validation.patch)  # or edit per patches/*.applied.diff
```

## 3. Kernel correctness A/B
```bash
work/venv_pr/bin/python  scripts/kernel_ab.py gate
work/venv_<arm>/python   scripts/kernel_ab.py capture   > evidence/kernel/capture_<arm>.json
work/venv_<arm>/python   scripts/kernel_ab.py reference evidence/kernel/ref_<arm>
work/venv_main/bin/python scripts/kernel_ab.py compare evidence/kernel/ref_main evidence/kernel/ref_pr evidence/kernel/cross_arm_compare.json
work/venv_pr/bin/python  scripts/regression_gates.py evidence/regression/arch_gates.json
```

## 4. Serving A/B (per concurrency; ABBA, warmup-separated)
```bash
bash scripts/run_serving_ab.sh A 16 1024 256 1 0.75 A_c16 100000
# full grid: see work/run_final.sh (A: c 1/4/8/16/32/64 + long-context + mixed; B: c 16/32/64 + long + mixed)
python3 scripts/collect_metrics.py     # -> results/performance_raw.csv + decode ms/step series
```

## 5. GSM8K (sgl-eval 0.1.3, own venv, per repo policy)
```bash
bash scripts/run_gsm8k_ab.sh A 0.75 gsm8k_A_diag 200 100000
bash scripts/run_gsm8k_ab.sh A 0.75 gsm8k_A_full 1319 100000
bash scripts/run_gsm8k_ab.sh B 0.75 gsm8k_B_full 1319 260000
```

## 6. Analysis + audit
```bash
work/venv_pr/bin/python scripts/analyze.py     # summaries + plots
python3 scripts/verify_evidence.py             # Phase 10 audit gates
sha256sum ... > evidence/checksums/SHA256SUMS  # sealed manifest
```
