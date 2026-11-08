# SGLang PR #48969 Round 3 物理验证最终报告（W7900 / gfx1100）

**目标提交（maintainer @twoask 的修复）:** `1da9ae2fcba99be22ed756083e1eb505c1cf5afe`
**验证日期:** 2026-11-08T16:52:08Z → 2026-11-08T19:33:29Z (UTC)　**Run ID:** `round3-1da9ae2-w7900-20261108T1652`

## 1. 硬件与核心数实测（非假设）

| 项目 | 实测值 |
|---|---|
| 设备 / gfx 目标 | AMD Radeon Graphics / gfx1100 (Radeon PRO W7900) |
| rocminfo Compute Units | 96 |
| `torch.cuda.get_device_properties(0).multi_processor_count` | **48** |
| SGLang `current_arch().num_sms`（1da9ae2 实现） | **48** |
| 新阈值 `max(8, 8*48//20)` | **19** |
| Qwen3-0.6B `head_tiles`（16 Q / 8 KV 头，head_dim 128） | 8（物理 grid 实测 `[batch, 8, 16]`） |

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
| c=1 | 132.77 | 130.45 | 132.44 | 0.9961 [0.9932, 0.9991] (n=6) | 1.0173 [1.0125, 1.0221] (n=4) |
| c=2 | 240.90 | 240.92 | 239.97 | 0.9944 [0.9908, 0.9980] (n=6) | 0.9959 [0.9923, 0.9995] (n=4) |
| c=4 | 455.08 | 455.09 | 454.52 | 0.9856 [0.9633, 1.0085] (n=6) | 1.1021 [0.9065, 1.3398] (n=4) |
| c=8 | 801.74 | 839.26 | 838.59 | 1.0454 [1.0423, 1.0486] (n=6) | 0.9935 [0.9853, 1.0018] (n=4) |

c=4 首腿存在与臂无关的首次使用停顿（TTFT ~1.1s vs ~57ms，三臂同受；预登记规则：TTFT > 5×单元中位数），
剔除后 new/main = 0.9972 [0.9938, 1.0005]、new/old = 0.9975 [0.9939, 1.0012]（剔除明细在 statistics.json ttft_outliers）。

## 5. P0+：持续 c=1（32 个顺序请求，不与单波协议混合）

main 133.27　new 133.31　old 131.02　tok/s。
new/main = 0.9992 [0.9969, 1.0016] (n=4)（CI 含 1.0，接近持平；非数学等价证明）；
new/old = 1.0188 [1.0142, 1.0235] (n=2)（old 重现 ~0.983x 缺口）。

## 6. P1：高并发非回归（c=16/32/64）

| 并发 | main | new | new/main |
|---|---|---|---|
| c=16 | 1182.15 | 1310.53 | 1.1085 [1.0855, 1.1320] (n=2) |
| c=32 | 1635.93 | 1902.29 | 1.1628 [1.1544, 1.1712] (n=2) |
| c=64 | 1715.63 | 2256.99 | 1.3155 [1.3043, 1.3269] (n=2) |

注：以上为端到端输出吞吐量（含 serving 全链路），非纯 Kernel speedup。

## 7. P1：第二显存配置（mem-fraction 0.30 / 自动 KV，c=1，独立实验）

main 132.53　new 132.75　old 129.64　tok/s。
new/main = 1.0011 [0.9964, 1.0059] (n=4)（CI 含 1.0，接近持平）；new/old = 1.0239 [1.0173, 1.0306] (n=4)（old ~0.978x）。

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

有效腿：{"main": 38, "old": 22, "new": 56}。配对对数见各 CI 括号内 n。缺失/失败腿全部在
`results/statistics.json` 的 missing_legs 显式披露（本次 0 条失败腿：见 order.jsonl）。

## 11. 结论分级（证据 → 判断）

- **c=1**：机制上 new 在 batch=1 恢复 main 的启动配置（hints+4warps，物理捕获）；吞吐上
  new/main 单波 ≈ 0.9961 [0.9932, 0.9991] (n=6)、持续 32 请求 ≈ 0.9992 [0.9969, 1.0016]、
  第二显存配置 ≈ 1.0011 [0.9964, 1.0059]，且 old 同时存在可复现的 ~0.98x 差距
  （与 @twoask 注释中 W7900 实测 0.98x 一致）→ 判定 **RESTORED**（机制 + 配对证据齐备）。
  推荐表述（英文）：*The previously observed ~2% c=1 regression is substantially
  mitigated. The sustained c=1 workload is near parity, with the original launch
  configuration restored.*
  不得宣称数学上完全等价、绝对零回退或已证明不存在任何性能损失；单波点估计 0.9961 的
  CI 上限 0.9991 仍略低于 1.0。
- **c=2**：new 保持 main 的启动配置（16<19 保留 hints），new/main = 0.9944 [0.9908, 0.9980]
  —— 存在约 0.56% 的残余回退（CI 不含 1.0），不能表述为完全持平。
- **c=4**：new 采用 old 的无 hints 配置。未剔除异常值 new/main = 0.9856 [0.9633, 1.0085]；
  按预登记规则（TTFT > 5×单元中位数，三臂同受的首次使用停顿，剔除 3 腿，明细见
  statistics.json ttft_outliers）剔除后 = 0.9972 [0.9938, 1.0005]。两组数字必须同时披露。
- **c=8**：new/main = 1.0454 [1.0423, 1.0486]（端到端输出吞吐，非纯 Kernel speedup）。
- **c=16/32/64**：高并发收益保持（与历史轮方向一致；端到端输出吞吐量）→ 见第 6 节。
- **内核正确性**：全部案例通过 fp32 参考（如执行）；跨臂差异为逐位相等或 <2e-2 绝对差（见第 8 节）。
- **GSM8K**：53.83% vs 55.65%，McNemar p≈0.100 —— 未检测到统计显著差异，但这不构成等价证明。
- **确定性推理重试**：两臂均因 LDS 99,328B > 65,536B BLOCKED（状态为标准 `BLOCKED`，
  `BLOCKED_LDS_LIMIT` 为原因/子状态，不计入 PASS）。

## 12. 原始证据与 SHA256

全部原始文件（bench JSON、client/server 日志、GPU 遥测）在 `round3/evidence/`，
清单与校验和 `round3/audit/SHA256SUMS`；历史 Round 1/2 证据逐字节未动
（`round3/audit/baseline_freeze.sha256`，830 文件）。

## 13. Round 3 独立审计（CPU-only，可从全新克隆复跑）

`bash round3/scripts/audit_round3.sh` → 结果：见 `round3/audit/audit_report.md`（含负向自测）。
历史审计 `bash scripts/audit_local.sh` 本次复跑结果：PASS（`round3/audit/audit_local_round3.log`）。

## 14. 交付

- 分支：`validation/1da9ae2-w7900-round3`　PR：见仓库
- 证据归档提交（evidence archive commit）：`5a6cee126160cde47ac708efb81e32ae95d49194`

## 15. 剩余风险与覆盖缺口

见 `round3/LIMITATIONS.md`（Rust 扩展未构建、sgl_kernel 单构建多臂安装、单 GPU 串行、
WGP/CU 口径依赖、B 模型与长上下文未复测等）。

## 16. 对 @twoask 的回复草案

见 `round3/UPSTREAM_REPLY_DRAFT.md`。
