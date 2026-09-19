# 弱读取器竞争对手差距分析 — Hindsight 20B

**问题：** 哪些竞争对手以*更弱的*读取器击败了 cortex，该差距的根因是什么 — 我们能否复现？

## 1. 唯一明确的案例：Hindsight 20B（而 cortex 已略胜一筹）

| 系统 | 读取器 | LongMemEval-S |
|---|---|---|
| Hindsight（OSS-120B） | 120B 开源 | 89.0% |
| **Hindsight（OSS-20B）** | **20B 开源** | **83.6%** |
| **cortex（我们的）** | **DeepSeek V4-Flash（13B 激活量）** | **83.95%** |

因此严格来说，**没有任何弱读取器竞争对手在总体上击败 cortex** — Hindsight 20B 是最接近的，而 cortex 现在比它高出约 0.35pp。但逐类别拆解揭示了 Hindsight 的架构在何处赢得了 cortex 未赢得的领先。

## 2. 真正的差距在 TR（时间推理），而非总体

Hindsight 20B 逐类别（论文表 2）vs cortex（RRF 基线）：

| 能力 | Hindsight 20B | cortex | Δ |
|---|---|---|---|
| 多会话（MR） | 79.7% | 79.55% | ~0（打平） |
| 时间（TR） | **79.7%** | **73.43%** | **−6.3pp** |
| 知识更新（KU） | 84.6% | 81.25% | −3.4pp |

MR 是势均力敌。唯一最大的可复现差距是 **TR：Hindsight 从 20B 模型上榨取到 79.7% 的时间准确率，cortex 仅 73.43%** — 一个 6.3pp 的缺口，仅凭读取器强度无法解释（两者使用的都是中等规模的读取器）。

## 3. 根因：事实级时间区间 + 日期范围检索通道

Hindsight 的 Tempr 并不按日期对轮次重新排序（这一点我们测试过并否决了）。它做两件 cortex 未做的事：

**保留时间（写入路径）。** LLM 抽取*叙事事实*，并将每个事实的相对时间（“last week”、“in March”）规范化为一个 **绝对发生区间 [τ_s, τ_e]** — 即*事件发生*的日期，而非*轮次被写入*的日期。这消灭了我们测得的确切失败：“baking class I took … yesterday” 被赋予事件日期（yesterday）而非轮次的提及日期，于是 `12:32` 时间戳以及提及与事件的歧义根本不会出现。

**召回时间（读取路径）。** 一个混合解析器（快速 dateparser + Flan-T5-small 回退）将查询的时间表达式（“two weeks ago”、“last Saturday”）转换为一个 **日期范围 [τ_start, τ_end]**，然后以 `[τ_s, τ_e] ∩ [τ_start, τ_end] ≠ ∅` 作为 **第四条独立检索通道**（语义 + BM25 + 图 + 时间）进行匹配，由 RRF 融合并由交叉编码器重排。

这是对事实区间的一个*过滤*通道，而非对原始轮次的*重排序*。

## 4. 为何我们早先的 TR 尝试是负面结果（以及缺失了什么）

我们实现了 `reorderByDateProximity` — 从问题中解析出单个锚点日期，并按日期接近度对*原始轮次*重新排序。它被否决了（TR 不显著，−0.75/次运行），原因是：

1. 它按轮次的 **提及日期** 重新排序，而这是错误的信号 — 事件日期存在于轮次文本*内部*（“yesterday”），而非轮次头部。
2. 它没有 **发生区间** 抽取：没有事实级 [τ_s, τ_e] 可用于与查询范围匹配。

Hindsight 的设计修复了这两点，而它正是我们未曾构建的部分。

## 5. cortex 已具备什么（因此修复是增量式的，而非重写）

cortex 的 `temporal-engine.ts` 已包含这些构件：
- `buildTemporalEventExtractionPrompt`（LLM 从轮次中抽取事件日期），
- `resolveTemporalDate` / `parseRelativeOffset`（相对时间 → 绝对日期）。

缺失的是 Hindsight 所具有的*检索*接线：

| 组成部分 | cortex | Hindsight |
|---|---|---|
| 事实级事件日期抽取 | 部分（TemporalEvent） | 完整叙事 + 区间 |
| 相对时间 → 发生区间 [τ_s, τ_e] | 部分（`parseRelativeOffset` 缺少 "yesterday"/"last week"/"next month"） | 完整 |
| TR 召回上的日期范围**过滤通道** | **缺失** | **存在（第 4 个通道）** |
| 该通道的 RRF 融合 | 时间维度上缺失 | 存在 |

## 6. 可复现计划（P0，确定性，可 TDD）

仿照 Hindsight 的时间通道，适配 cortex 的在线逐题流程：

1. **扩展 `parseRelativeOffset`**，覆盖 `yesterday`、`last week/weekend`、
   `next month/year`、`N weeks/months ago`、`in February` — 锚定到
   *问题日期*（已作为 `question_date` 可用）。
2. **`resolveTimeRange`**：问题时间表达式 → `[τ_start, τ_end]` 日期范围
   （而非单个锚点）。
3. **TR 召回过滤**：对于具有可解析范围的题目，扩大召回并提升/过滤那些
   **抽取出的事件日期** 落在该范围内的轮次 — 使用 `answerTemporal` 中已有的
   LLM 事件日期抽取，而非轮次头部日期。

先前的负面结果是 *按提及日期重排序* 的设计。这是 *按抽取的事件区间过滤* 的设计 — 正是它赋予 Hindsight +6.3pp 的 TR 领先。它值得在 TR 端点上做一次全新的、机制范围限定的 A/B。
