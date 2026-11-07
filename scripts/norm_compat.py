"""Environment workaround part 2 (symmetric across arms): out-parameter-style
RMSNorm ops for HIP serving.

This sglang revision's RMSNorm.forward_hip calls
  fused_add_rms_norm(out, x, residual_out, residual, weight, eps)
  rms_norm(out, x, weight, eps)
and expects the provider registered at import from vllm._custom_ops (fallback)
or aiter (primary, requires aiter@>=c16d44b which is network-infeasible here)
to expose that out-style API. The host vllm 0.16.1 exports an older in-place
4-argument API, so the call crashes. The AOT sgl_kernel ROCm subset does not
ship the norm ops at all.

This module provides out-style implementations as Triton kernels (fp32
statistics, identical formulation to sgl_kernel's CUDA reference
llama_rms_norm / fused_add_rms_norm), and installs a lazy meta-path hook that
overrides the two names on vllm._custom_ops after it is first imported.

The implementation is bit-stable and identical on both arms; it is used for
all serving in this campaign. Documented in ENVIRONMENT.md.
"""
import importlib.abc
import importlib.util
import sys

import torch
import triton
import triton.language as tl


@triton.jit
def _rmsnorm_out_kernel(X, W, Y, D, EPS: tl.constexpr, BLOCK: tl.constexpr):
    row = tl.program_id(0).to(tl.int64)
    col = tl.arange(0, BLOCK)
    mask = col < D
    x = tl.load(X + row * D + col, mask=mask, other=0.0).to(tl.float32)
    w = tl.load(W + col, mask=mask, other=0.0).to(tl.float32)
    inv = tl.rsqrt(tl.sum(x * x, axis=0) / D + EPS)
    y = x * inv * w
    tl.store(Y + row * D + col, y.to(Y.dtype.element_ty), mask=mask)


@triton.jit
def _fused_add_rmsnorm_out_kernel(
    X, R, W, Y, RO, D, EPS: tl.constexpr, BLOCK: tl.constexpr
):
    row = tl.program_id(0).to(tl.int64)
    col = tl.arange(0, BLOCK)
    mask = col < D
    x = tl.load(X + row * D + col, mask=mask, other=0.0).to(tl.float32)
    r = tl.load(R + row * D + col, mask=mask, other=0.0).to(tl.float32)
    w = tl.load(W + col, mask=mask, other=0.0).to(tl.float32)
    s = x + r
    inv = tl.rsqrt(tl.sum(s * s, axis=0) / D + EPS)
    y = s * inv * w
    tl.store(RO + row * D + col, s.to(RO.dtype.element_ty), mask=mask)
    tl.store(Y + row * D + col, y.to(Y.dtype.element_ty), mask=mask)


def _flat_2d(t):
    return t.reshape(-1, t.shape[-1])


def rms_norm_out(out, x, weight, eps):
    xf = _flat_2d(x)
    of = _flat_2d(out)
    rows, dim = xf.shape
    _rmsnorm_out_kernel[(rows,)](
        xf, weight, of, dim, eps, triton.next_power_of_2(dim),
        num_warps=min(16, max(1, triton.next_power_of_2(dim) // 512)),
    )
    return out


def fused_add_rms_norm_out(out, x, residual_out, residual, weight, eps):
    xf = _flat_2d(x)
    rf = _flat_2d(residual)
    of = _flat_2d(out)
    rof = _flat_2d(residual_out)
    rows, dim = xf.shape
    _fused_add_rmsnorm_out_kernel[(rows,)](
        xf, rf, weight, of, rof, dim, eps, triton.next_power_of_2(dim),
        num_warps=min(16, max(1, triton.next_power_of_2(dim) // 512)),
    )
    return out, residual_out


_TARGET = "vllm._custom_ops"


class _PatchLoader(importlib.abc.Loader):
    def __init__(self, inner):
        self._inner = inner

    def create_module(self, spec):
        return self._inner.create_module(spec)

    def exec_module(self, module):
        self._inner.exec_module(module)
        try:
            module.fused_add_rms_norm = fused_add_rms_norm_out
            module.rms_norm = rms_norm_out
        except Exception:  # noqa: BLE001
            pass


class _PatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != _TARGET:
            return None
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(fullname)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _PatchLoader(spec.loader)
        return spec


def install() -> None:
    already = sys.modules.get(_TARGET)
    if already is not None:
        try:
            already.fused_add_rms_norm = fused_add_rms_norm_out
            already.rms_norm = rms_norm_out
        except Exception:  # noqa: BLE001
            pass
        return
    for f in sys.meta_path:
        if isinstance(f, _PatchFinder):
            return
    sys.meta_path.insert(0, _PatchFinder())


install()
