#!/usr/bin/env python3
"""Phase 2 kernel-level A/B correctness + launch-config proof for SGLang PR
#48969 grouped GQA decode attention on gfx1100.

Modes (first arg):
  gate      - pure gate-function + flag assertions (PR arm)
  reference - run deterministic cases, compare kernel output to fp32 torch
              reference, save outputs (.pt) for cross-arm bitwise comparison
  compare   - load two arms' saved outputs and report per-case max abs/rel
              error and bitwise equality
  capture   - launch-config capture: record Triton compile opts reaching
              _fwd_grouped_kernel_stage1 for qualifying + excluded shapes

All tensors are generated from fixed seeds per case, so both arms see
bit-identical inputs.
"""
import hashlib
import json
import math
import os
import sys

import torch
import triton

MAX_KV_SPLITS = 16  # sglang default on HIP (platform_hook: amd -> 16)


def case_seed(name: str) -> int:
    h = hashlib.sha256(name.encode()).digest()
    return int.from_bytes(h[:4], "little") & 0x7FFFFFFF


def build_case(name, B, HQ, HKV, D, VLens, dtype, page_size=1, kv_dtype=None):
    """Deterministic decode-attention problem. q:[B,HQ,D]; token KV pool."""
    seed = case_seed(name)
    gen = torch.Generator(device="cpu").manual_seed(seed)
    total = int(sum(VLens))
    kdt = kv_dtype or dtype
    k_cpu = (0.1 + 0.2 * torch.randn(total, HKV, D, generator=gen)).to(kdt)
    v_cpu = (0.1 + 0.2 * torch.randn(total, HKV, D, generator=gen)).to(kdt)
    q_cpu = (0.1 + 0.2 * torch.randn(B, HQ, D, generator=gen)).to(dtype)
    lens = torch.tensor(VLens, dtype=torch.int32)
    kv_indptr = torch.zeros(B + 1, dtype=torch.int32)
    kv_indptr[1:] = torch.cumsum(lens, 0)
    kv_indices = torch.zeros(total, dtype=torch.int32)
    off = 0
    for i, L in enumerate(VLens):
        kv_indices[off : off + L] = torch.arange(off, off + L, dtype=torch.int32)
        off += L
    return dict(
        name=name, B=B, HQ=HQ, HKV=HKV, D=D, dtype=dtype, kv_dtype=kdt,
        page_size=page_size,
        q=q_cpu.cuda(), k=k_cpu.cuda(), v=v_cpu.cuda(),
        kv_indptr=kv_indptr.cuda(), kv_indices=kv_indices.cuda(),
        seq_lens=lens.cuda(),
    )


def run_case(case, logit_cap=0.0):
    from sglang.kernels.ops.attention.decode_attention import (
        decode_attention_fwd_grouped,
    )
    B, HQ, D = case["B"], case["HQ"], case["D"]
    o = torch.empty(B, HQ, D, dtype=case["dtype"], device="cuda")
    logits = torch.empty(B, HQ, MAX_KV_SPLITS, D, dtype=torch.float32, device="cuda")
    lse = torch.empty(B, HQ, MAX_KV_SPLITS, dtype=torch.float32, device="cuda")
    num_kv_splits = torch.empty(B, dtype=torch.int32, device="cuda")
    # mimic get_num_kv_splits: proportional to length, capped at max
    lens = case["seq_lens"].to(torch.int64)
    mx, mn = int(lens.max()), int(lens.min())
    if mx * 8 < mn * 10:
        eff_min = mx
    else:
        eff_min = mn
    m1 = min(max(1, (mx + eff_min - 1) // eff_min), MAX_KV_SPLITS)
    chunk = (mx + m1 - 1) // m1
    ns = (lens + chunk - 1) // chunk
    ns = torch.clamp(ns.to(torch.int32), min=1)
    ns = torch.minimum(ns, torch.full_like(ns, MAX_KV_SPLITS))
    num_kv_splits.copy_(ns)
    sm_scale = 1.0 / math.sqrt(D)
    decode_attention_fwd_grouped(
        case["q"], case["k"], case["v"], o,
        case["kv_indptr"], case["kv_indices"], logits, lse,
        num_kv_splits, MAX_KV_SPLITS, sm_scale, 1.0,
        logit_cap=logit_cap,
        page_size=case["page_size"],
    )
    return o


def reference(case, logit_cap=0.0):
    B, HQ, HKV, D = case["B"], case["HQ"], case["HKV"], case["D"]
    q = case["q"].to(torch.float32)
    k = case["k"].to(torch.float32)
    v = case["v"].to(torch.float32)
    sm = 1.0 / math.sqrt(D)
    out = torch.empty(B, HQ, D, dtype=torch.float32, device="cuda")
    for b in range(B):
        s, e = int(case["kv_indptr"][b]), int(case["kv_indptr"][b + 1])
        kk = k[s:e]  # [L,HKV,D]
        vv = v[s:e]
        for h in range(HQ):
            kh = (h * HKV) // HQ
            scores = (q[b, h] @ kk[:, kh].T) * sm  # [L]
            if logit_cap > 0:
                scores = logit_cap * torch.tanh(scores / logit_cap)
            p = torch.softmax(scores, dim=-1)
            out[b, h] = p @ vv[:, kh]
    return out


def gate():
    from sglang.kernels.ops.attention import decode_attention as da
    arch = torch.cuda.get_device_properties(0).gcnArchName
    res = {"arch": arch, "checks": [], "pass": True}
    def ck(n, c, d=None):
        res["checks"].append({"name": n, "ok": bool(c), "detail": d})
        res["pass"] &= bool(c)
        print(("PASS " if c else "FAIL ") + n + (f" :: {d}" if d else ""))
    ck("device_is_gfx1100", arch.startswith("gfx1100"), arch)
    ck("pr_gate_flag_true", getattr(da, "_is_gfx115", None) is True,
       f"_is_gfx115={getattr(da, '_is_gfx115', None)!r}")
    fn = getattr(da, "_gfx115_grouped_num_warps", None)
    ck("gate_fn_present", fn is not None)
    if fn:
        cases = [
            (64, 0, torch.bfloat16, 16, 8, 2),
            (128, 0, torch.bfloat16, 16, 8, 2),
            (128, 0, torch.float16, 1, 8, 2),
            (128, 0, torch.bfloat16, 4, 2, 2),    # == 8 boundary qualifies
            (128, 0, torch.bfloat16, 3, 2, None),  # 6 < 8
            (128, 0, torch.bfloat16, 1, 2, None),  # 2 < 8
            (128, 0, torch.bfloat16, 7, 1, None),  # 7 < 8
            (128, 0, torch.bfloat16, 8, 1, 2),     # == 8
            (256, 0, torch.bfloat16, 64, 8, None),
            (512, 64, torch.bfloat16, 64, 1, None),
            (256, 32, torch.bfloat16, 64, 1, None),
            (128, 0, torch.float8_e4m3fn, 64, 8, None),
            (128, 0, torch.float8_e5m2, 64, 8, None),
            (128, 0, torch.float32, 64, 8, None),
            (128, 0, torch.uint8, 64, 8, None),
        ]
        for bdm, bpe, dt, b, ht, want in cases:
            got = fn(block_dmodel=bdm, block_dpe=bpe, kv_dtype=dt, batch=b, head_tiles=ht)
            ck(f"gate({bdm},{bpe},{dt},{b},{ht})", got == want, f"got={got} want={want}")
    print(json.dumps(res, indent=2, default=str))
    return 0 if res["pass"] else 1


def capture():
    from sglang.kernels.ops.attention import decode_attention as da
    recs = []
    orig = triton.runtime.jit.JITFunction.run
    stage1 = da._fwd_grouped_kernel_stage1
    def spy(self, *a, **kw):
        try:
            name = getattr(self, "__name__", None) or getattr(getattr(self, "fn", None), "__name__", "?")
        except Exception:  # noqa: BLE001
            name = "?"
        if self is stage1 or name == "_fwd_grouped_kernel_stage1":
            recs.append({"kernel": name,
                         **{k: v for k, v in kw.items()
                            if k in ("num_warps", "num_stages", "waves_per_eu",
                                     "matrix_instr_nonkdim", "kpack", "launch_pdl")}})
        return orig(self, *a, **kw)
    triton.runtime.jit.JITFunction.run = spy
    shapes = [
        ("qualifying_b16_h16_kv8_d128_bf16", 16, 16, 8, 128, [1024] * 16, torch.bfloat16),
        ("boundary_b1_h16_kv8_d128_bf16", 1, 16, 8, 128, [4096], torch.bfloat16),
        ("tiny_grid_b1_h16_kv2_d128_bf16", 1, 16, 2, 128, [4096], torch.bfloat16),
        ("tiny_grid_b3_h16_kv2_d128_bf16", 3, 16, 2, 128, [4096, 2048, 17], torch.bfloat16),
        ("hd256_b4_h16_kv8_d256_bf16", 4, 16, 8, 256, [512] * 4, torch.bfloat16),
    ]
    out = {"records": {}, "pass": True}
    for nm, B, HQ, HKV, D, lens, dt in shapes:
        try:
            c = build_case(nm, B, HQ, HKV, D, lens, dt)
            recs.clear()
            run_case(c)
            torch.cuda.synchronize()
            out["records"][nm] = list(recs)
        except Exception as e:  # noqa: BLE001
            out["records"][nm] = {"error": repr(e)}
            out["pass"] = False
        finally:
            recs.clear()
    triton.runtime.jit.JITFunction.run = orig
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["pass"] else 1


def main():
    mode = sys.argv[1]
    if mode == "gate":
        return gate()
    if mode == "capture":
        return capture()
    if mode == "reference":
        outdir = sys.argv[2]
        os.makedirs(outdir, exist_ok=True)
        cases = json.load(open(os.path.join(os.path.dirname(__file__),
                                            "..", "configs", "kernel_cases.json")))
        rows = []
        for c in cases:
            nm = c["name"]
            dt = getattr(torch, c["dtype"])
            kdt = getattr(torch, c.get("kv_dtype", c["dtype"]))
            cs = build_case(nm, c["B"], c["HQ"], c["HKV"], c["D"], c["lens"], dt, kv_dtype=kdt)
            try:
                o = run_case(cs, logit_cap=c.get("logit_cap", 0.0))
                torch.cuda.synchronize()
                ref = reference(cs, logit_cap=c.get("logit_cap", 0.0))
                o32 = o.to(torch.float32)
                finite = bool(torch.isfinite(o32).all())
                diff = (o32 - ref).abs()
                mae = float(diff.max()) if finite else float("nan")
                den = ref.abs().clamp_min(1e-6)
                mre = float((diff / den).max()) if finite else float("nan")
                torch.save(o.to(torch.float32).cpu(), os.path.join(outdir, nm + ".pt"))
                rows.append({"name": nm, "finite": finite, "max_abs_err": mae,
                             "max_rel_err": mre, "ok": True,
                             "dtype": c["dtype"], "B": c["B"], "HQ": c["HQ"],
                             "HKV": c["HKV"], "D": c["D"],
                             "max_len": max(c["lens"])})
            except Exception as e:  # noqa: BLE001
                rows.append({"name": nm, "ok": False, "error": repr(e)})
        json.dump(rows, open(os.path.join(outdir, "reference_rows.json"), "w"),
                  indent=2, default=str)
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if mode == "compare":
        dmain, dpr, outj = sys.argv[2], sys.argv[3], sys.argv[4]
        rows = []
        for f in sorted(os.listdir(dmain)):
            if not f.endswith(".pt"):
                continue
            a = torch.load(os.path.join(dmain, f))
            b = torch.load(os.path.join(dpr, f))
            same = bool(torch.equal(a, b))
            d = (a.float() - b.float()).abs()
            rows.append({"name": f[:-3], "bitwise_equal": same,
                         "cross_arm_max_abs": float(d.max())})
        json.dump(rows, open(outj, "w"), indent=2)
        print(json.dumps(rows, indent=2))
        return 0
    print("unknown mode", mode)
    return 2


if __name__ == "__main__":
    sys.exit(main())
