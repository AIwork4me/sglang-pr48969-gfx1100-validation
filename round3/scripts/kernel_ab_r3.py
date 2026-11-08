#!/usr/bin/env python3
"""Round 3 kernel-level A/B correctness for the grouped GQA decode attention.

Modes:
  reference <outdir> <cases.json>  - run deterministic cases, compare against an
        fp32 torch reference, save outputs (.pt) for cross-arm comparison
  compare <refA> <refB> <out.json> - compare two arms' saved outputs per case
        (max abs/rel error, bitwise equality)
  gate     - (subsumed by gate_verify_r3.py, kept for parity)

All tensors are generated from fixed per-case seeds, so every arm sees
bit-identical inputs. Numerical tolerances are NOT weakened vs Rounds 1-2.
"""
import hashlib, json, math, os, sys

import torch

MAX_KV_SPLITS = 16  # sglang default on HIP


def case_seed(name: str) -> int:
    h = hashlib.sha256(name.encode()).digest()
    return int.from_bytes(h[:4], "little") & 0x7FFFFFFF


def build_case(name, B, HQ, HKV, D, VLens, dtype, page_size=1, kv_dtype=None):
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
    kv_indices = torch.arange(total, dtype=torch.int32)
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
    lens = case["seq_lens"].to(torch.int64)
    mx, mn = int(lens.max()), int(lens.min())
    eff_min = mx if mx * 8 < mn * 10 else mn
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
        logit_cap=logit_cap, page_size=case["page_size"],
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
        kk = k[s:e]
        vv = v[s:e]
        for h in range(HQ):
            kh = (h * HKV) // HQ
            scores = (q[b, h] @ kk[:, kh].T) * sm
            if logit_cap > 0:
                scores = logit_cap * torch.tanh(scores / logit_cap)
            p = torch.softmax(scores, dim=-1)
            out[b, h] = p @ vv[:, kh]
    return out


def main():
    mode = sys.argv[1]
    if mode == "reference":
        outdir, cases_file = sys.argv[2], sys.argv[3]
        os.makedirs(outdir, exist_ok=True)
        cases = json.load(open(cases_file))
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
                rows.append({"name": nm, "finite": finite, "max_abs_err": mae,
                             "max_rel_err": mre, "ok": finite and mae < 2e-2})
                torch.save({"o": o.cpu(), "case": {k: v for k, v in c.items()}},
                           os.path.join(outdir, nm + ".pt"))
            except Exception as e:  # noqa: BLE001
                rows.append({"name": nm, "error": repr(e), "ok": False})
            print(rows[-1])
        json.dump(rows, open(os.path.join(outdir, "reference_results.json"), "w"), indent=2)
        ok = all(r.get("ok") for r in rows)
        print("REFERENCE", "PASS" if ok else "FAIL", len(rows), "cases")
        return 0 if ok else 1
    if mode == "compare":
        refA, refB, out = sys.argv[2], sys.argv[3], sys.argv[4]
        rows = []
        for f in sorted(os.listdir(refA)):
            if not f.endswith(".pt"):
                continue
            fb = os.path.join(refB, f)
            if not os.path.exists(fb):
                rows.append({"name": f, "error": "missing in B"})
                continue
            a = torch.load(os.path.join(refA, f), weights_only=True)["o"]
            b = torch.load(fb, weights_only=True)["o"]
            if a.dtype != b.dtype or a.shape != b.shape:
                rows.append({"name": f, "error": "shape/dtype mismatch"})
                continue
            a32, b32 = a.to(torch.float32), b.to(torch.float32)
            diff = (a32 - b32).abs()
            bitwise = bool(torch.equal(a, b))
            rows.append({"name": f, "bitwise_equal": bitwise,
                         "max_abs_diff": float(diff.max()),
                         "n_diff_elements": int((a32 != b32).sum())})
            print(rows[-1])
        json.dump(rows, open(out, "w"), indent=2)
        print("COMPARE done", len(rows), "cases")
        return 0
    print("unknown mode")
    return 2


if __name__ == "__main__":
    sys.exit(main())
