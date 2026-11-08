#!/usr/bin/env python3
"""Round 3 gate verification: source-level decisions + physical launch capture.

Per arm (main | old | new):
  1. Device identity: gfx1100, runtime multi_processor_count, SGLang
     current_arch().num_sms, computed threshold, Qwen3-0.6B head_tiles.
  2. Pure gate-function decision matrix on the ACTUAL hardware core count
     (old/new arms; main has no gate function).
  3. Physical _decode_grouped_att_m_fwd launches with the Triton JIT run
     intercepted, capturing num_warps/num_stages/CDNA hints + grid, for
     Qwen3-0.6B geometry batches 1,2,4,8,16,32,64 and exclusion shapes.

Writes JSON; exit 0 iff all expectations for the arm hold.
"""
import argparse, inspect, json, math, sys

import torch
import triton


def gate_matrix(fn, core_count, threshold):
    rows = []
    for b in (1, 2, 4, 8, 16, 32, 64):
        for ht in (8, 2, 1):
            got = fn(block_dmodel=128, block_dpe=0, kv_dtype=torch.bfloat16,
                     batch=b, head_tiles=ht, core_count=core_count)
            rows.append({"batch": b, "head_tiles": ht, "core_count": core_count,
                         "threshold": threshold,
                         "programs": b * ht,
                         "decision": "hints_kept" if got is None else f"num_warps={got}"})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["main", "old", "new"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from sglang.kernels.arch import current_arch
    from sglang.kernels.ops.attention import decode_attention as da

    report = {"arm": args.arm, "checks": [], "pass": True}

    def check(name, cond, detail=None):
        report["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})
        if not cond:
            report["pass"] = False
        print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail is not None else ""))

    props = torch.cuda.get_device_properties(0)
    arch = current_arch()
    report["device"] = {
        "name": props.name, "gcnArchName": props.gcnArchName,
        "torch_multi_processor_count": props.multi_processor_count,
        "sglang_num_sms": arch.num_sms,
        "torch_version": torch.__version__, "torch_hip": torch.version.hip,
        "triton_version": triton.__version__,
    }
    cc = arch.num_sms
    threshold = max(8, 8 * cc // 20)
    report["computed_threshold"] = {"core_count": cc, "threshold": threshold}
    # Qwen3-0.6B geometry: 16 Q heads / 8 KV heads, head_dim 128
    head_tiles = triton.cdiv(16, min(16, 16 // 8))
    report["qwen3_06b_geometry"] = {"head_tiles": head_tiles}
    check("device_is_gfx1100", props.gcnArchName.startswith("gfx1100"), props.gcnArchName)
    check("head_tiles_is_8", head_tiles == 8, head_tiles)

    fn = getattr(da, "_rdna_grouped_num_warps", None)
    if args.arm == "main":
        check("main_has_no_rdna_gate", fn is None and not getattr(da, "_is_rdna", False))
    else:
        check("gate_fn_present", fn is not None)
        check("rdna_flag_true_on_gfx1100", getattr(da, "_is_rdna", None) is True,
              repr(getattr(da, "_is_rdna", None)))
        # expected decisions per arm on the ACTUAL core count
        def expect(arm, b, ht):
            if arm == "old":
                return None if b * ht < 8 else 2
            return None if b * ht < threshold else 2
        okall = True
        for b in (1, 2, 4, 8, 16, 32, 64):
            for ht in (8, 2, 1):
                got = fn(block_dmodel=128, block_dpe=0, kv_dtype=torch.bfloat16,
                         batch=b, head_tiles=ht, core_count=cc)
                want = expect(args.arm, b, ht)
                ok = got == want
                okall &= ok
                if not ok:
                    print(f"  mismatch b={b} ht={ht}: got {got} want {want}")
        check(f"gate_matrix_matches_expectation(core_count={cc},threshold={threshold})", okall)
        # exclusion geometries (arm-independent expectations)
        excl = [
            ("hd256_keeps_hints", dict(block_dmodel=256, block_dpe=0, kv_dtype=torch.bfloat16, batch=64, head_tiles=8), None),
            ("mla_576_keeps_hints", dict(block_dmodel=512, block_dpe=64, kv_dtype=torch.bfloat16, batch=64, head_tiles=1), None),
            ("mla_288_keeps_hints", dict(block_dmodel=256, block_dpe=32, kv_dtype=torch.bfloat16, batch=64, head_tiles=1), None),
            ("fp8_kv_keeps_hints", dict(block_dmodel=128, block_dpe=0, kv_dtype=torch.float8_e4m3fn, batch=64, head_tiles=8), None),
            ("fp8_e5m2_keeps_hints", dict(block_dmodel=128, block_dpe=0, kv_dtype=torch.float8_e5m2, batch=64, head_tiles=8), None),
            ("fp32_kv_keeps_hints", dict(block_dmodel=128, block_dpe=0, kv_dtype=torch.float32, batch=64, head_tiles=8), None),
        ]
        for name, kw, want in excl:
            kw.setdefault("block_dmodel", 128)
            kw.setdefault("block_dpe", 0)
            kw.setdefault("kv_dtype", torch.bfloat16)
            kw.setdefault("batch", 64)
            kw.setdefault("head_tiles", 8)
            kw.setdefault("core_count", cc)
            got = fn(**kw)
            check(f"excl_{name}", got == want, f"got={got}")
        report["gate_matrix"] = gate_matrix(fn, cc, threshold)

    # ---- physical launch capture on Qwen3-0.6B geometry + exclusions ----
    captured = []
    orig_run = triton.runtime.jit.JITFunction.run
    stage1 = getattr(da, "_fwd_grouped_kernel_stage1", None)

    def spy_run(self, *a, **kw):
        try:
            nm = getattr(self, "__name__", None) or getattr(getattr(self, "fn", None), "__name__", "?")
        except Exception:
            nm = "?"
        if nm == "_fwd_grouped_kernel_stage1":
            rec = {k: v for k, v in kw.items()
                   if k in ("num_warps", "num_stages", "waves_per_eu",
                            "matrix_instr_nonkdim", "kpack")}
            grid = kw.get("grid")
            try:
                rec["grid"] = [int(x) for x in (grid() if callable(grid) else grid)]
            except Exception:
                rec["grid"] = str(grid)
            captured.append(dict(rec))
        return orig_run(self, *a, **kw)

    def build_case(B, HQ, HKV, D, lens, dtype):
        gen = torch.Generator(device="cpu").manual_seed(1234 + B * 7 + D)
        total = sum(lens)
        k = (0.1 + 0.2 * torch.randn(total, HKV, D, generator=gen)).to(dtype)
        v = (0.1 + 0.2 * torch.randn(total, HKV, D, generator=gen)).to(dtype)
        q = (0.1 + 0.2 * torch.randn(B, HQ, D, generator=gen)).to(dtype)
        return q.cuda(), k.cuda(), v.cuda()

    def launch(B, HQ, HKV, D, lens, dtype):
        q, k, v = build_case(B, HQ, HKV, D, lens, dtype)
        o = torch.empty(B, HQ, D, dtype=dtype, device="cuda")
        MAX_SPLITS = 16
        logits = torch.empty(B, HQ, MAX_SPLITS, D, dtype=torch.float32, device="cuda")
        lse = torch.empty(B, HQ, MAX_SPLITS, dtype=torch.float32, device="cuda")
        ns = torch.full((B,), 1, dtype=torch.int32, device="cuda")
        indptr = torch.zeros(B + 1, dtype=torch.int32, device="cuda")
        tot = 0
        for i, L in enumerate(lens):
            tot += L
            indptr[i + 1] = tot
        idx = torch.arange(total := int(sum(lens)), dtype=torch.int32, device="cuda")
        da.decode_attention_fwd_grouped(
            q, k, v, o, indptr, idx, logits, lse, ns, MAX_SPLITS,
            1.0 / math.sqrt(D), 1.0, page_size=1)

    triton.runtime.jit.JITFunction.run = spy_run
    report["launch_captures"] = {}
    try:
        cases = []
        for B in (1, 2, 4, 8, 16, 32, 64):
            cases.append((f"qwen_b{B}", (B, 16, 8, 128, [512] * B, torch.bfloat16)))
        cases += [
            ("excl_hd256", (4, 16, 8, 256, [512] * 4, torch.bfloat16)),
            ("excl_kv2_ht8_b1", (1, 16, 2, 128, [4096], torch.bfloat16)),
        ]
        for nm, (B, HQ, HKV, D, lens, dt) in cases:
            captured.clear()
            try:
                launch(B, HQ, HKV, D, lens, dt)
                torch.cuda.synchronize()
                report["launch_captures"][nm] = list(captured)
            except Exception as e:
                report["launch_captures"][nm] = {"error": repr(e)}
                report["pass"] = False
    finally:
        triton.runtime.jit.JITFunction.run = orig_run

    # physical expectations: stage-1 launch kwargs per arm on Qwen3 geometry
    def launch_expect(arm, B):
        ht = 8
        if arm == "main":
            return {"num_warps": 4, "hints": True}
        use_new = (arm == "new")
        drop = not (B * ht < (threshold if use_new else 8))
        return {"num_warps": 2 if drop else 4, "hints": not drop}

    for B in (1, 2, 4, 8, 16, 32, 64):
        recs = report["launch_captures"].get(f"qwen_b{B}", [])
        if not recs or not isinstance(recs, list) or not recs:
            check(f"launch_qwen_b{B}_captured", False, str(recs)[:200])
            continue
        r0 = recs[0]
        exp = launch_expect(args.arm, B)
        has_hints = any(k in r0 for k in ("waves_per_eu", "matrix_instr_nonkdim", "kpack"))
        check(f"launch_qwen_b{B}_num_warps", r0.get("num_warps") == exp["num_warps"],
              f"got {r0.get('num_warps')} want {exp['num_warps']}")
        check(f"launch_qwen_b{B}_hints", has_hints == exp["hints"],
              f"got hints={has_hints} want {exp['hints']}")

    json.dump(report, open(args.out, "w"), indent=2, default=str)
    print(json.dumps(report.get("computed_threshold"), indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
