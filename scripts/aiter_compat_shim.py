"""Environment workaround (symmetric across arms): the host's preinstalled
aiter (from the AMD lab image) predates the modules sglang's quark-mxfp4
scheme imports at module load. Those kernels are CDNA/mxfp4-only and are never
used by this campaign (dense bf16 GQA models, --attention-backend triton,
SGLANG_USE_AITER=0). Upstream's own gfx1151 recipe installs full aiter from
git, which is network-infeasible here; this shim keeps imports working and
fails loudly if the mxfp4 path is ever actually invoked.

Installed into each arm venv via a .pth import hook (venv-local, does not
touch /opt/venv or the source trees).
"""
import importlib
import sys
import types

_SHIMS = {
    "aiter.gemm_a4w4": ["gemm_a4w4"],
    "aiter.per_1x32_f4_quant_hip": ["per_1x32_f4_quant_hip"],
    "aiter.ops.shuffle.shuffle_weight": ["shuffle_weight"],
    "aiter.ops.triton.quant.dynamic_mxfp4_quant": ["dynamic_mxfp4_quant"],
    "aiter.ops.triton.gemm.fused.fused_gemm_afp4wfp4_split_cat": [
        "fused_gemm_afp4wfp4_split_cat"
    ],
}


def _install() -> None:
    for modname, attrs in _SHIMS.items():
        try:
            importlib.import_module(modname)
            continue  # real module available; nothing to do
        except ImportError:
            pass
        mod = types.ModuleType(modname)
        mod.__doc__ = "aiter compat shim (validation campaign); raises on use"
        for attr in attrs:
            def _raiser(*args, _n=modname, _a=attr, **kwargs):
                raise NotImplementedError(
                    f"aiter shim: {_n}.{_a} is not available in this environment "
                    "(host aiter is older than sglang's import); this path is "
                    "unused by dense bf16 GQA serving."
                )
            setattr(mod, attr, _raiser)
        sys.modules[modname] = mod
        parent, _, leaf = modname.rpartition(".")
        if parent:
            try:
                pmod = importlib.import_module(parent)
            except ImportError:
                pmod = types.ModuleType(parent)
                sys.modules[parent] = pmod
            setattr(pmod, leaf, mod)


_install()
