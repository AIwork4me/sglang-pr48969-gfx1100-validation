# ENVIRONMENT

## Hardware
- GPU: AMD Radeon PRO W7900 48GB — gfx1100 (RDNA3.0), chip 0x744b, 96 CUs, 6 shader engines, wave32, max 1760 MHz
- CPU: 2x AMD EPYC 9334 (64c/128t), 503 GiB RAM
- OS: Ubuntu 24.04.4, kernel 6.8.0-79-generic

## Software stack (identical on both arms)
| Component | Version | Source |
|---|---|---|
| ROCm | HIP 7.2.53211 (ROCk 6.16.13) | host /opt/rocm-7.2.1 |
| PyTorch | 2.9.1+gitff65f5b (ROCm 7.2.1) | host /opt/venv, attached read-only to each arm venv via `.pth` |
| Triton | 3.6.0+rocm7.2.0.gitba5c1517 | AMD stable wheel (repo.radeon.com rocm-rel-7.2), sha256 in evidence/checksums |
| sgl_kernel | 0.4.10 | built from each arm's own tree, `AMDGPU_TARGET=gfx1100` |
| sglang | main 0afb736 / PR 3fdf6f7 (+gfx1100 gate patch) | GitHub tarballs, byte-verified vs git blob SHAs |
| sgl-eval | 0.1.3 | PyPI (test-extra pin at the tested revision) |
| Python | 3.12.3 | Ubuntu |

The gfx1151 reference image (docker/rocm-gfx1151.Dockerfile at the PR revision)
pins "ROCm 7.2.4 / PyTorch 2.9.1" — our stack (ROCm 7.2.1 host runtime, torch
2.9.1, Triton 3.6.0) matches that generation of the official AMD-supported
combination. The PR author measured on ROCm 7.13/torch 2.10/Triton 3.6.

## Replicated official recipe (no nested Docker in this lab)
The environment replicates `docker/rocm-gfx1151.Dockerfile` steps on the host:
1. `python/pyproject.toml` swapped for `python/pyproject_other.toml` (as the Dockerfile does; original preserved as `pyproject.toml.orig`).
2. Dependency flatten of `runtime_base + runtime_common + srt_hip + diffusion_common + diffusion_hip` minus `sglang[...]` self-references, torch, st_attn, vsa; `compressed-tensors==0.15.0` (`work/rocm_flat_deps.txt`).
3. `pip install --no-deps --no-build-isolation -e python` (build isolation would pull CUDA-pinned torch==2.14.1).
4. sgl_kernel AOT build for gfx1100 using the Dockerfile's own wave32 patch script adapted from gfx1151 (`patches/sgl-kernel-gfx1100.sh`).

## Documented environment workarounds (symmetric on both arms)
1. **aiter_compat_shim** (`work/aiter_compat_shim.py`, venv-local `.pth`): the host
   aiter predates five `aiter.ops.triton.gemm...`/top-level symbols that this
   sglang revision imports at module scope from the quark mxfp4 scheme. The shim
   satisfies the imports and raises on use; the mxfp4 path is never exercised by
   dense bf16 GQA serving. Upstream's recipe installs full aiter from git, which
   is network-infeasible through this lab's egress proxy (~45 KB/s to GitHub).
2. **norm_compat** (`work/norm_compat.py`): this sglang revision calls
   out-parameter-style `fused_add_rms_norm(out,x,res_out,res,w,eps)` /
   `rms_norm(out,x,w,eps)` in `RMSNorm.forward_hip`, expecting new-aiter
   (unavailable, see above); the vllm fallback present in the host env exports an
   older 4-arg in-place API and crashes. The module provides out-style Triton
   kernels (fp32 statistics, formulation identical to sgl_kernel's CUDA reference
   `llama_rms_norm`/`fused_add_rms_norm`) and lazily overrides the two names on
   `vllm._custom_ops` when that module is imported. Verified ≤1 bf16 ULP against
   a torch fp32 reference. Identical on both arms, so the A/B is unaffected; see
   LIMITATIONS.md for cross-stack comparability caveats.
3. **Triton 3.6 required**: sglang at this revision fails to compile
   `kernels/ops/memory/small_copy.py` on Triton 3.5.1 (constexpr tuple indexing).
   AMD's ROCm 7.2 Triton 3.6 wheel is the upgrade the repo's own
   `3rdparty/amd/wheel/README.md` recommends.

## Co-tenant GPU memory constraint
A host-level process outside this container (PID 3906994, not visible in our PID
namespace, PROTECTED per campaign rules) holds 33.26 GB of the W7900's 51.5 GB
for the entire campaign, leaving ~18.2 GB. GPU compute utilization from that
process is 0% (8 W idle) — it does not contend for SM time, only memory. All
runs fit inside the remaining memory; see LIMITATIONS.md for the
`--max-total-tokens` consequences.
