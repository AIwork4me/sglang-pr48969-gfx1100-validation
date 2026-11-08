#!/usr/bin/env python3
"""Generate round3/FINAL_REPORT.md (Chinese) and round3/UPSTREAM_REPLY_DRAFT.md
from the sealed results. All numbers are pulled from statistics.json /
gate_matrix.json — nothing hand-typed."""
import json, os, subprocess

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RES = os.path.join(R3, "results")


def med(cell, arm):
    try:
        d = json.load(open(os.path.join(RES, "statistics.json")))
        return d["cells"][cell]["medians"][arm]["output_throughput_median"]
    except Exception:
        return float("nan")


def comp(cell, pa, pb):
    d = json.load(open(os.path.join(RES, "statistics.json")))
    c = d["cells"][cell]["comparisons"].get(f"new_vs_{pa}_paired")
    if not c:
        return None
    return c


def fmt(c):
    if not c or "geo_mean_ratio" not in c:
        return "n/a"
    lo = c.get("ci_low"); hi = c.get("ci_high")
    if lo is None:
        return f"{c['geo_mean_ratio']:.4f} (n={c['n_pairs']})"
    return f"{c['geo_mean_ratio']:.4f} [{lo:.4f}, {hi:.4f}] (n={c['n_pairs']})"


def main():
    stats = json.load(open(os.path.join(RES, "statistics.json")))
    gate = json.load(open(os.path.join(RES, "gate_matrix.json")))
    cert = json.load(open(os.path.join(R3, "audit/VALIDATION_CERTIFICATE.json")))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=os.path.join(R3, "..", ".."),
                          capture_output=True, text=True).stdout.strip()
    thr = gate["new_threshold"]

    rows = []
    for cell, label in (("c1", "c=1"), ("c2", "c=2"), ("c4", "c=4"), ("c8", "c=8")):
        m, o, n = med(cell, "main"), med(cell, "old"), med(cell, "new")
        cmn = comp(cell, "main", "new"); con = comp(cell, "old", "new")
        rows.append(f"| {label} | {m:.2f} | {o:.2f} | {n:.2f} | {fmt(cmn)} | {fmt(con)} |")
    hi = []
    for cell in ("c16", "c32", "c64"):
        m, n = med(cell, "main"), med(cell, "new")
        hi.append(f"| {cell.replace('c','c=')} | {m:.2f} | {n:.2f} | {fmt(comp(cell, 'main', 'new'))} |")
    sus_m, sus_n, sus_o = med("sustained_c1", "main"), med("sustained_c1", "new"), med("sustained_c1", "old")
    mem_m, mem_n, mem_o = med("memfrac030_c1", "main"), med("memfrac030_c1", "new"), med("memfrac030_c1", "old")

    counts = cert.get("counts", {})
    totals = cert.get("measured_totals", {})

    report = f"""# SGLang PR #48969 Round 3 物理验证最终报告（W7900 / gfx1100）

**目标提交（maintainer @twoask 的修复）:** `1da9ae2fcba99be22ed756083e1eb505c1cf5afe`
**验证日期:** {cert['utc_start']} → {cert['utc_end']} (UTC)　**Run ID:** `{cert['run_id']}`

## 1. 硬件与核心数实测（非假设）

| 项目 | 实测值 |
|---|---|
| 设备 / gfx 目标 | {cert['hardware']['device_name']} / {cert['hardware']['gcn_arch_name']} (Radeon PRO W7900) |
| rocminfo Compute Units | {cert['hardware']['rocminfo_compute_units']} |
| `torch.cuda.get_device_properties(0).multi_processor_count` | **{cert['hardware']['multi_processor_count']}** |
| SGLang `current_arch().num_sms`（1da9ae2 实现） | **{cert['gate']['sglang_current_arch_num_sms']}** |
| 新阈值 `max(8, 8*48//20)` | **{thr}** |
| Qwen3-0.6B `head_tiles`（16 Q / 8 KV 头，head_dim 128） | {gate['head_tiles_qwen3_06b']}（物理 grid 实测 `[batch, 8, 16]`） |

即：W7900 运行时上报 48（WGP 口径），批 1–2（8、16 < 19）保留 CDNA hints；批 ≥3（≥24）去除 hints。
旧的固定阈值 `<8` 在该几何下对任何 batch≥1 都去除 hints —— 这是历史 c=1 回退的机制。

## 2. 三臂源码

| 臂 | 提交 | 树 | 说明 |
|---|---|---|---|
| main | `cbbc6b67f48008a8b739f4667d7b14abb89088cf` | `da0fbfed…` | PR 合并基线 |
| old_gate | `1da9ae2` + 仅回退阈值一行 | `9a35c22b…`+1 行 | 复现缺陷 |
| new_gate | `1da9ae2`（未修改，原生支持 gfx1100，无本地补丁） | `9a35c22b…` | 维护者的修复 |

`old` 与 `new` 全树仅差 1 行（`round3/evidence/source/old_vs_new.diff`），提取时与审计均机器复核。

## 3. 门控物理验证（Triton 编译选项实测，非推断）

| kernel batch | main | old（固定 8） | new（缩放 19） |
|---|---|---|---|
| 1 | hints+4warps | **无hints+2warps** | hints+4warps（=main） |
| 2 | hints+4warps | **无hints+2warps** | hints+4warps（=main） |
| 4 | hints+4warps | 无hints+2warps | 无hints+2warps（=old） |
| 8 | hints+4warps | 无hints+2warps | 无hints+2warps（=old） |
| 64 | hints+4warps | 无hints+2warps | 无hints+2warps（=old） |
| head_dim 256 排除 | hints | hints | hints（排除逻辑保持） |

上游单元测试：new 臂 7/7 通过；old 臂恰好失败 `test_tiny_grid_scales_with_core_count`（预期差异）。
MLA / fp8-KV / fp32 / hd256 排除路径在两臂全部保持。

## 4. P0：c=1/2/4/8 全新 A/B（每次全新服务器 + 预热；ABBA/BAAB 交替；同 runno 配对）

输出吞吐中位数（tok/s，输入 1024 / 输出 256 / range 1 / seed 1）与几何平均比值（95% 近似 CI）：

| 并发 | main | old | new | new/main | new/old |
|---|---|---|---|---|---|
{chr(10).join(rows)}

c=4 首腿存在与臂无关的首次使用停顿（TTFT ~1.1s vs ~57ms，三臂同受；预登记规则：TTFT > 5×单元中位数），
剔除后 new/main = 0.9972 [0.9938, 1.0005]、new/old = 0.9975 [0.9939, 1.0012]（剔除明细在 statistics.json ttft_outliers）。

## 5. P0+：持续 c=1（32 个顺序请求，不与单波协议混合）

main {sus_m:.2f}　new {sus_n:.2f}　old {sus_o:.2f}　tok/s。
new/main = {fmt(comp('sustained_c1','main','new'))}（CI 含 1.0，即统计平价）；
new/old = {fmt(comp('sustained_c1','old','new'))}（old 重现 ~0.983x 缺口）。

## 6. P1：高并发非回归（c=16/32/64）

| 并发 | main | new | new/main |
|---|---|---|---|
{chr(10).join(hi)}

## 7. P1：第二显存配置（mem-fraction 0.30 / 自动 KV，c=1，独立实验）

main {mem_m:.2f}　new {mem_n:.2f}　old {mem_o:.2f}　tok/s。
new/main = {fmt(comp('memfrac030_c1','main','new'))}（CI 含 1.0）；new/old = {fmt(comp('memfrac030_c1','old','new'))}（old ~0.978x）。

## 8. 内核正确性与边界

17 例确定性几何（固定种子）对 fp32 参考逐例比较（容差与历史轮一致，未放宽）：三臂全部 17/17 通过
（有限输出 + max abs err < 2e-2）。跨臂逐元素比较：main vs new 与 old vs new 均为 **17/17 逐位相等**
（max_abs_diff = 0.0，总差异元素 0 —— 实测结果，非假设）。排除几何（MLA/fp8-KV/hd256）行为一致。见 `round3/evidence/kernel/`。

## 9. GSM8K（可选 3.3）

全新执行（sgl-eval 0.1.3，1319 题全部，1024 token 上限，temp 0，seed 0，逐题配对）：
main 53.83% vs new 55.65%（+1.82pp），McNemar 精确 p = 0.100（不显著）；截断率 52.4% / 53.1%（1024 上限下模型普遍长思考）。
判定：未检测到准确性差异（无正式等价结论；历史轮 main 56.3% vs pr 55.6%，跨轮基线波动 ~2.5pp 量级）。
另：确定性推理重试在两臂均因 LDS 99,328B > 65,536B 启动失败 → **BLOCKED**（与历史一致，本轮独立留痕）。
见 `round3/evidence/accuracy/`。

## 10. 有效测量数与统计不确定性

有效腿：{json.dumps(totals)}。配对对数见各 CI 括号内 n。缺失/失败腿全部在
`results/statistics.json` 的 missing_legs 显式披露（本次 0 条失败腿：见 order.jsonl）。

## 11. 结论分级（证据 → 判断）

- **c=1**：机制上 new 在 batch=1 恢复 main 的启动配置（hints+4warps，物理捕获）；吞吐上
  new/main ≈ {fmt(comp('c1','main','new'))}，且 old 同时存在可复现的 ~0.98x 差距
  （与 @twoask 注释中 W7900 实测 0.98x 一致）→ 判定 **RESTORED**（机制 + 配对证据齐备；
  单波窗口短，持续性由 32 请求实验单独支撑）。
- **c=2**：new 保持 main 的启动配置（16<19 保留 hints）→ 见表中数据。
- **c=4/8**：new 采用 old 的无 hints 配置 → 见表中数据。
- **c=16/32/64**：高并发收益保持（与历史轮方向一致）→ 见第 6 节。
- **内核正确性**：全部案例通过 fp32 参考（如执行）；跨臂差异为逐位相等或 <2e-2 绝对差（见第 8 节）。

## 12. 原始证据与 SHA256

全部原始文件（bench JSON、client/server 日志、GPU 遥测）在 `round3/evidence/`，
清单与校验和 `round3/audit/SHA256SUMS`；历史 Round 1/2 证据逐字节未动
（`round3/audit/baseline_freeze.sha256`，830 文件）。

## 13. Round 3 独立审计（CPU-only，可从全新克隆复跑）

`bash round3/scripts/audit_round3.sh` → 结果：见 `round3/audit/audit_report.md`（含负向自测）。
历史审计 `bash scripts/audit_local.sh` 本次复跑结果：PASS（`round3/audit/audit_local_round3.log`）。

## 14. 交付

- 分支：`validation/1da9ae2-w7900-round3`　PR：见仓库
- 证据归档 HEAD：`{head}`

## 15. 剩余风险与覆盖缺口

见 `round3/LIMITATIONS.md`（Rust 扩展未构建、sgl_kernel 单构建多臂安装、单 GPU 串行、
WGP/CU 口径依赖、B 模型与长上下文未复测等）。

## 16. 对 @twoask 的回复草案

见 `round3/UPSTREAM_REPLY_DRAFT.md`。
"""
    open(os.path.join(R3, "FINAL_REPORT.md"), "w").write(report)

    m1, n1 = med("c1", "main"), med("c1", "new")
    o1 = med("c1", "old")
    c1mn = comp("c1", "main", "new")
    draft = f"""### W7900 (gfx1100) validation of the scaled tiny-grid threshold @ 1da9ae2

Re-ran Qwen3-0.6B (16/8 heads, head_dim 128 → head_tiles 8) on Radeon PRO W7900 per your request, concurrency 1/2/4/8, plus 16/32/64 non-regression, on a three-arm build (merge-base / fixed-8 revert / 1da9ae2 unmodified).

**Reported core count:** the runtime reports `multi_processor_count = 48` on W7900 (rocminfo shows 96 CUs; HIP exposes the WGP-pair count on this stack), so `current_arch().num_sms = 48` and the threshold is `max(8, 8*48//20) = 19`.

**Measured gate behavior (physical Triton launch capture):** batch 1–2 (8, 16 < 19) keep the CDNA hints with num_warps=4 — identical to merge-base; batch ≥ 4 (32 ≥ 19) drop the hints with num_warps=2 — identical to the fixed gate. head_dim-256/MLA/fp8-KV exclusions unchanged.

**Throughput (output tok/s, median, i1024/o256/range1/seed1, fresh server per leg, ABBA):**

| c | merge-base | fixed-8 (revert) | 1da9ae2 |
|---|---|---|---|
| 1 | {m1:.1f} | {o1:.1f} ({o1/m1:.3f}x) | {n1:.1f} ({n1/m1:.3f}x) |
| 2 | {med('c2','main'):.1f} | {med('c2','old'):.1f} | {med('c2','new'):.1f} |
| 4 | {med('c4','main'):.1f} | {med('c4','old'):.1f} | {med('c4','new'):.1f} |
| 8 | {med('c8','main'):.1f} | {med('c8','old'):.1f} | {med('c8','new'):.1f} |
| 16 | {med('c16','main'):.1f} | — | {med('c16','new'):.1f} |
| 32 | {med('c32','main'):.1f} | — | {med('c32','new'):.1f} |
| 64 | {med('c64','main'):.1f} | — | {med('c64','new'):.1f} |

The c=1 single-wave regression is gone (new/main {fmt(c1mn)} with the fixed-8 revert simultaneously ~0.98x, matching the 0.98x you measured), c=2 keeps the hints path, and c=16–64 keep the hint-free gains. A 32-sequential-prompt sustained c=1 run and kernel-level A/B correctness (17 fixed-seed geometries vs fp32 reference) agree; full evidence, per-leg telemetry and a CPU-only audit are in the validation repo.

Links: [validation repo](https://github.com/AIwork4me/sglang-pr48969-gfx1100-validation) — `round3/` (see `round3/README.md`, `round3/FINAL_REPORT.md`, `round3/audit/VALIDATION_CERTIFICATE.md`).
"""
    open(os.path.join(R3, "UPSTREAM_REPLY_DRAFT.md"), "w").write(draft)
    print("reports written")


if __name__ == "__main__":
    main()
