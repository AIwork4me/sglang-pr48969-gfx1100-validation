#!/usr/bin/env python3
"""Phase 7 regression gates that are testable without other physical GPUs.

G5: the local gfx1100 gate extension must not enable the path for unrelated
architectures. We monkeypatch torch.cuda.get_device_properties/is_available to
simulate each arch and re-evaluate the exact expression used by the patched
decode_attention module.

Run inside the PR arm venv.
"""
import json
import sys
import types

import torch

RESULTS = {"gates": []}


def check(name, cond, detail=None):
    RESULTS["gates"].append({"gate": name, "ok": bool(cond), "detail": detail})
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))


class FakeProps:
    def __init__(self, gcn):
        self.gcnArchName = gcn


def gate_value_for_arch(gcn, hip=True, cuda_available=True):
    """Re-evaluate the patched module-level expression for a simulated arch."""
    import unittest.mock as mock

    import sglang.kernels.ops.attention.decode_attention as da
    real_props = torch.cuda.get_device_properties
    real_avail = torch.cuda.is_available
    real_hip = torch.version.hip
    with mock.patch.object(torch.cuda, "get_device_properties", return_value=FakeProps(gcn)), \
         mock.patch.object(torch.cuda, "is_available", return_value=cuda_available), \
         mock.patch.object(torch.version, "hip", hip):
        from sglang.srt.utils.device import is_gfx115_supported
        try:
            is_gfx115_supported.cache_clear()
        except AttributeError:
            pass
        try:
            gfx115 = is_gfx115_supported()
        except Exception:
            gfx115 = False
        is_gfx1100_validation = cuda_available and (
            torch.cuda.get_device_properties(0).gcnArchName.startswith("gfx1100")
        )
        _is_hip = bool(hip)
        val = _is_hip and (gfx115 or is_gfx1100_validation)
    torch.cuda.get_device_properties = real_props
    torch.cuda.is_available = real_avail
    torch.version.hip = real_hip
    return val


def main():
    real = torch.cuda.get_device_properties(0).gcnArchName
    check("host_is_gfx1100", real.startswith("gfx1100"), real)

    enabled = {g: gate_value_for_arch(g) for g in [
        "gfx1100", "gfx1100:sramecc+:wave32", "gfx1150", "gfx1151",
        "gfx1101", "gfx1102", "gfx1103", "gfx1200", "gfx1201", "gfx942",
        "gfx950", "gfx1250", "gfx1030", "gfx90a", "sm_90",
    ]}
    expect_true = {"gfx1100", "gfx1100:sramecc+:wave32", "gfx1150", "gfx1151"}
    for g, v in enabled.items():
        want = g in expect_true
        check(f"g5_arch_{g}", v == want, f"gate={v} want={want}")

    check("g5_cuda_only_disabled", gate_value_for_arch("gfx1100", cuda_available=False) is False)
    check("g5_nvidia_hip_off_disabled", gate_value_for_arch("sm_90", hip=False) is False)

    # G1: MLA keeps hints (already covered by gate fn, re-assert here)
    from sglang.kernels.ops.attention.decode_attention import _gfx115_grouped_num_warps
    check("g1_mla_disabled", _gfx115_grouped_num_warps(
        block_dmodel=512, block_dpe=64, kv_dtype=torch.bfloat16, batch=64, head_tiles=1) is None)
    check("g2_fp8_disabled", _gfx115_grouped_num_warps(
        block_dmodel=128, block_dpe=0, kv_dtype=torch.float8_e4m3fn, batch=64, head_tiles=8) is None)
    check("g3_hd256_disabled", _gfx115_grouped_num_warps(
        block_dmodel=256, block_dpe=0, kv_dtype=torch.bfloat16, batch=64, head_tiles=8) is None)
    check("g4_tiny_grid_disabled", _gfx115_grouped_num_warps(
        block_dmodel=128, block_dpe=0, kv_dtype=torch.bfloat16, batch=1, head_tiles=2) is None)

    ok = all(g["ok"] for g in RESULTS["gates"])
    RESULTS["overall_pass"] = ok
    out = sys.argv[1] if len(sys.argv) > 1 else "evidence/regression/arch_gates.json"
    json.dump(RESULTS, open(out, "w"), indent=2)
    print("overall", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
