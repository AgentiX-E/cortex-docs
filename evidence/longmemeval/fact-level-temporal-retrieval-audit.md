# 事实级时序检索 — 深度审计 + 分阶段计划

**目标：** 通过复刻 Hindsight 的 Tempr——事实级发生区间 + 日期范围检索通道 + 图检索
——来填补 6.3pp 的 TR 缺口（cortex 73.43% vs Hindsight 20B 79.7%）。

## 1. 缺口精确地在于接线与一个缺失的"发生"概念，不在于发明

cortex-core **已经**拥有 Hindsight 的核心原语，只是基准未加以使用：

| Hindsight Tempr | cortex-core（是否拥有？） | 基准 TR 路径（是否使用？） |
|---|---|---|
| 事实级发生区间 [τ_s, τ_e] | **Fact.validFrom/validUntil** ✅ | ❌ 仅原始轮次 |
| 图检索（扩散激活） | **MemoryGraph.spreadingActivation** ✅ | ❌ |
| 时序边 | **EdgeKind.temporal** ✅ | ❌ |
| 交叉编码器重排 | ❌ | ❌ |

所以这是一个*接线*缺口。基准中缺失两个概念：

1. **发生日期 vs 提及日期。** `ExtractedFact.date`（KU）与 `TemporalEvent.date`（TR）
   都复制**轮次日期**——即事实被*写下*的日期。Hindsight 提取的是**发生区间**——事件
   *发生*的日期（"yesterday" → 轮次日期 − 1）。这正是我们测到的失败：
   "baking class I took … yesterday" 拿到的是提及日期，而不是事件日期。
2. **日期范围检索通道。** 我们加了 `resolveTimeRange`（问题时间限定词 → [start, end]），
   但只把它喂给事件查找*提示词*，而没有喂给一个按日期过滤/加权的*召回通道*。

## 2. 约束：在线逐题架构，无 Retain 阶段

Hindsight 的 Retain 步骤*离线*预提取带发生区间的叙事性事实，之后 Recall 只需匹配区间。
cortex 从原始会话在线回答每一道题，因此任何事实级区间都只能逐题提取（LLM 成本）或经由
新的索引步骤（架构变更）提取。

## 3. 分阶段计划（增量 → 系统化），每阶段均有 go/no-go

### P1 — 提取发生日期，而非提及日期（TR 确定性路径）

`buildTemporalEventExtractionPrompt` 目前写着"copy that turn's date"。改为报告**事件的日期**，
以轮次日期为基准解析相对时间（"yesterday"、"last week"）——确定性地，而非靠 LLM 做算术。

- **为何优先：** 它修的是根信号，且是改动最小的一处。
- **成本：** 零额外 LLM 调用（同样的提取，不同的指令）。
- **TDD：** 提示词契约断言该指令要求事件日期并解析相对指代；对 `computeTemporalAnswer`
  做单元测试，传入日期为 "yesterday" 的事件 → 确定性偏移。
- **机制 A/B：** TR 的 relative/interval/ordering 端点。
- **go/no-go：** 无论如何都推进到 P2（这是一处纯粹的修正）；直接度量事件日期的增量。

### P2 — 日期范围召回通道（过滤，而非重排）

为 TR 召回增加一个时序实验臂：放宽候选轮次，然后**过滤**到其头部日期落在
`resolveTimeRange` 窗口内的轮次（为提及 vs 发生的偏差留出余量）。用 RRF 融合——绝不
用重排，那正是此前的负面结果。

- **为何在 P1 之后：** P1 让*提取出*的日期正确；P2 让*召回到*的集合日期正确。
- **成本：** 零额外 LLM 调用（头部日期解析是确定性的）。
- **TDD：** 日期范围过滤单元测试 + 阴性对照（非 TR 路径不变）+ 变异测试（移除过滤器
  → 测试失败）。
- **机制 A/B：** TR 的 eventLookup + relative 端点；IE/MR/KU/ABS 守卫。
- **go/no-go：** 若 TR 准确率不动，就停止——缺口便在阅读器侧，而非召回侧。

### P3 — 把 cortex-core 的 Fact + MemoryGraph 接入 TR（系统化）

增加一个轻量的逐基准**索引步骤**（Retain 的等价物）：提取带发生区间的
`ExtractedFact` 式事实，构建 `MemoryGraph`（实体链接 + 时序边），并通过
`spreadingActivation` + 日期范围匹配 + 语义 + BM25，经 RRF 融合来召回 TR 问题。

- **为何最后：** 它是最大的改动，只有在 P1/P2 表明时序轴是承重结构时才值得做。
- **成本：** 对会话做一次索引遍历（以某个样本为界）。
- **TDD：** 索引器 + 图构建 + 扩散激活召回的单元测试；覆盖率 ≥95%。
- **机制 A/B：** TR 总体 + MR（图可能有助于多跳）；守卫。

## 4. 诚实的 ROI 解读

P1/P2 便宜且瞄准实测的根信号，但单一的确定性补丁已屡次落在噪声底之下。P3 是唯一有望
收回 Hindsight 那 6.3pp 大部分的改动，因为它提供了在线路径无法廉价推导出的事实级区间
与图遍历。
