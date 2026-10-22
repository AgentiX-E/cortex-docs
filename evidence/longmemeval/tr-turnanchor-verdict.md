# TR turnDate 锚点 A/B 判决 — ACCEPT（弱，方向正确）

**迭代：** P1 事实级发生日期（Hindsight Tempr step 1）
**提交：** `02bdd2d`（`c4bef6c` P1 + 畸形事件容忍）
**读取器：** deepseek-v4-flash, non-thinking（稳定基线）
**设计：** 4v4 交错、同瞬、精确置换检验

## 结果（8/8 次运行 `success`，`questionCount=500`）

| 端点 | control（aebd65a） | treatment（02bdd2d） | 判决 |
|---|---|---|---|
| **TR 准确率** | `[94,96,95,95]` = 95.00/次运行（74.80%） | `[93,95,95,96]` = 94.75/次运行（74.61%） | **−0.25/次运行，p=0.74（不显著）** |
| 总体 | 422.00/次运行（84.40%） | 423.00/次运行（84.60%） | +0.20pp，不显著 |

TR 总数没有变化 — 正如预注册所言，单个确定性补丁落在约 3 道题/次运行的实验臂内噪声底噪以下。

## 子类归因（真正重要的信号）

`turnDate` 只触及确定性路径（`computeTemporalAnswer`），即相对/区间/排序。eventLookup/其他保持不变，分析所显示的正是如此：

| TR 子类 | 题目数 | control | treatment | Δ | 受影响？ |
|---|---|---|---|---|---|
| **relative** | 25 | 83/100 | **88/100** | **+5** | ✅ 是 |
| interval | 26 | 95/104 | 92/104 | −3 | ✅ 是 |
| ordering | 40 | 118/160 | 115/160 | −3 | ✅ 是 |
| eventLookup | 20 | 48/80 | 48/80 | 0 | 否（正确） |
| other | 16 | 36/64 | 36/64 | 0 | 否（正确） |

## 逐题归因（决定性证据）

**relative +5** 是两次干净、真实的恢复，且零副作用：

| 题目 | control | treatment | 根因 |
|---|---|---|---|
| “……friends and family sale at Nordstrom？” | 0/4 | **4/4** ✅ | 相对锚点已修复 |
| “……attend a baking class……？” | 0/4 | **1/4** ✅ | 相对锚点已修复（部分） |

**interval −3** 是 **评判器噪声，而非真实回归**：

| 题目 | control | treatment | 实际发生了什么 |
|---|---|---|---|
| “……bird watching when I attended the workshop？” | 4/4 | 0/4 | control 的 `answer='30'` 被 **对照金标 `'Two months'` 判为正确** — 一次评判器假阳性（30 天 ≠ 2 个月）。上下文只陈述“attended workshop a month ago”，从未陈述 bird watching 是*何时开始*的，因此该题在检索上是有缺陷的。treatment 同样的 `'30'` 被正确判为错误。 |
| “……stand-up comedy specials……？” | 3/4 | 4/4 | 真实的 +1 改善 |

**ordering −3** 是 **采样/评判器漂移，而非确定性回归**：

| 题目 | Δ | 证据 |
|---|---|---|
| “……order of concerts……？” | c1/4→t0/4 | 两个实验臂的引擎答案几乎相同；评判器从 1/4 翻转为 0/4 |
| “……coffee maker or malfunction first？” | c2/4→t1/4 | LLM 回退路径（存在 llmRaw），turnDate 未参与 |
| “……fixing fence or trimming hooves first？” | c4/4→t3/4 | 3/4 相同；有一次运行的 LLM 抽取不同（temperature-0 浮点抖动） |

## 尽管总体不显著，为何仍 ACCEPT

1. **方向正确** — 将 `"yesterday"`/`"a month ago"` 锚定到陈述它的*轮次*（而非问题日期）正是 Hindsight 发生日期概念的本意；被恢复的两道题正是预审时为该失败模式标出的题。
2. **零真实回归** — interval/ordering 的 −3 可分解为评判器假阳性和采样漂移，而非确定性计算的变化。
3. **畸形事件崩溃修复是强制性的** — 第一个 P1 版本以 `undefined.trim()` 中止了全部 4 次 treatment 运行；容忍过滤器（附回归测试）是对提示变更首次暴露的潜在崩溃的正确根因修复。

## 诚实的结论

这与 **timeRange 迭代是同一模式**：单个确定性补丁恢复了几道机制级问题，但落在噪声底噪以下，因此总体准确率无法对其作出判定。`relative +5` 是真实且干净的；剩余的 Hindsight 差距需要 **事实级发生区间 + 日期范围检索通道**（P2/P3），而不是又一个孤立的提示补丁。

## 护栏

IE 563→566，MR 392→389，KU 234→239，ABS 119→119 — 全部在采样噪声范围内；`turnDate` 只进入 TR 路径，因此这些并非由该变更导致。
