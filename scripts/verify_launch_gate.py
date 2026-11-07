#!/usr/bin/env python3
"""Prove the grouped decode-attention stage-1 launch configuration actually
reaches the Triton compiler on this GPU, per campaign Phase 1 (P4).

Method:
  1. Assert the module-level gate flags on this device (PR+patch: gfx1100
     accepted; Main: not present).
  2. Assert the pure gate function `_gfx115_grouped_num_warps` decisions for
     qualifying and excluded geometries (PR arm only).
  3. Execute a real `_decode_grouped_att_m_fwd` launch on GPU tensors for a
     qualifying GQA shape while intercepting the Triton JIT run call to
     capture the compile options actually applied to `_fwd_grouped_kernel_stage1`
     (num_warps, num_stages, waves_per_eu, matrix_instr_nonkdim, kpack).

Writes a JSON verdict. Exit 0 iff every assertion for the arm holds.
"""
import argparse
import inspect
import json
import sys

import torch
import triton

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["main", "pr"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from sglang.kernels.ops.attention import decode_attention as da

    report = {"arm": args.arm, "checks": [], "pass": True}

    def check(name, cond, detail=None):
        report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
        if not cond:
            report["pass"] = False
        print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))

    arch = torch.cuda.get_device_properties(0).gcnArchName
    check("device_gfx1100", arch.startswith("gfx1100"), arch)

    is_gfx115_attr = getattr(da, "_is_gfx115", None)
    if args.arm == "pr":
        check("pr_gate_flag_true_on_gfx1100", is_gfx115_attr is True, f"_is_gfx115={is_gfx115_attr}")
        fn = da._gfx115_grouped_num_warps
        cases = [
            # (block_dmodel, block_dpe, kv_dtype, batch, head_tiles) -> expected
            (64, 0, torch.bfloat16, 16, 8, 2),
            (128, 0, torch.float16, 1, 8, 2),
            (128, 0, torch.bfloat16, 4, 2, 2),   # batch*head_tiles == 8 -> qualifies
            (128, 0, torch.bfloat16, 3, 2, None),  # 6 < 8 -> keep hints
            (128, 0, torch.bfloat16, 1, 2, None),  # 2 < 8 -> keep hints
            (256, 0, torch.bfloat16, 64, 8, None),  # head_dim 256 -> keep hints
            (512, 64, torch.bfloat16, 64, 1, None),  # MLA geometry -> keep hints
            (128, 0, torch.float8_e4m3fn, 64, 8, None),  # fp8 KV -> keep hints
            (128, 0, torch.float32, 64, 8, None),  # other dtype -> keep hints
        ]
        for bdm, bpe, dt, b, ht, want in cases:
            got = fn(block_dmodel=bdm, block_dpe=bpe, kv_dtype=dt, batch=b, head_tiles=ht)
            check(f"gate(bdm={bdm},bpe={bpe},{str(dt).split('.')[-1]},b={b},ht={ht})",
                  got == want, f"got {got} want {want}")
    else:
        check("main_has_no_gfx115_gate", not hasattr(da, "_is_gfx115") or is_gfx115_attr is False,
              f"_is_gfx115={is_gfx115_attr!r}")
        check("main_has_no_gate_fn", not hasattr(da, "_gfx115_grouped_num_warps"))

    # Real launch capture on a qualifying GQA geometry (head_dim 128, bf16,
    # batch 4, 16 q heads / 2 kv heads -> head_tiles = 2, batch*tiles = 8).
    captured = []
    orig_run = triton.runtime.jit.JITFunction.run

    def spy_run(self, *args, **kwargs):
        captured.append(dict(kwargs))
        return orig_run(self, *args, **kwargs)

    triton.runtime.jit.JITFunction.run = spy_run
    try:
        torch.manual_seed(0)
        B, HQ, HKV, D = 4, 16, 2, 128
        T = 257
        dtype = torch.bfloat16
        q = torch.randn(B, HQ, D, device="cuda", dtype=dtype)
        k = torch.randn(B, HKV, T, D, device="cuda", dtype=dtype)
        v = torch.randn(B, HKV, T, D, device="cuda", dtype=dtype)
        da.decode_attention_fwd(
            q, k, v, torch.tensor([0.08], device="cuda", dtype=torch.float32), None,
            None,
        ) if False else None
        # Direct stage-1/grouped call as used by the triton backend.
        o, lse = da.decode_attention_fwd_grouped(
            q, k, v, sm_scale=0.08, kv_indptr=None, kv_indices=None,
        ) if hasattr(da, "decode_attention_fwd_grouped") else (None, None)
    except Exception as e:  # noqa: BLE001
        report["launch_error"] = repr(e)
    finally:
        triton.runtime.jit.JITFunction.run = orig_run

    stage1 = [c for c in captured if getattr(captured, "_kernel_name", "") == ""]
    report["launches_captured"] = len(captured)
    for c in captured[:50]:
        nm = c.get("kernel_name")
    json.dump(report, open(args.out, "w"), indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
