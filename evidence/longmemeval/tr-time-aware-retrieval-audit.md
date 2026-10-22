# TR 时间感知检索 —— 深度审计（P0）

**日期：** 2026-09-06
**目标：** 判定将时间感知/图检索接入 TR 路径能否弥合 73-75% 对 HydraDB-90.97% 的
差距，以及若能，如何实现。

---

## 1. 架构差距（已测量）

cortex-core 提供了这些原语 —— `temporal/bitemporal.ts`（`currentFacts`、
`currentValue`、`findContradictions`）、`graph/memory-graph.ts`（`MemoryGraph`、
`spreadingActivation`、`EdgeKind` temporal/causal/semantic）、`domain/fact.ts`
（双时态 `Fact`）—— 但**基准系统并未使用它们**。
`NaturalLanguageMemorySystem` 仅从 cortex-core 导入 `EmbeddingModel, JsonSchema, LLM`，
并运行其自有的 `temporal-engine.ts`（决定性日期算术）+ 嵌入/词法检索。这两层彼此
脱节。

## 2. TR 失败普查（RRF 落地处理，34 道不同的错题）

三种模式，对时间感知检索的敏感性差异很大：

| 模式 | ~数量 | 例子 | 时间感知检索有帮助？ |
| --- | --- | --- | --- |
| **事件排序**（order/earliest/latest/first） | ~13 | "order of the three trips"、"order of six museums"、"who did I meet first"、"Rachel or Alex first" | ✅ **是** —— 需要时间窗口召回 + 日期有序上下文，而非语义召回 |
| **事件识别**（时间锚点 → 哪个事件） | ~9 | "gardening activity two weeks ago"、"Met museum two weeks ago"、"road bike vs mountain bike last weekend" | ✅ **是** —— 需要召回*锚点日期*上的轮次，而非语义最近的轮次 |
| **时长算术**（天/周/月） | ~12 | "38 days"、"21 days"、"15 weeks"、"7 days" | ⚠️ **部分** —— 已由确定性引擎服务；残余是日期提取歧义（"received feedback" 03/17 vs 03/18），而非检索 |

因此 34 道错题中约 22 道（排序 + 识别）确实是检索形态的，而非 LLM 语义形态的。
这与 MR 和 cross-encoder 的发现相反 —— **在此，时间感知检索正是正确的杠杆。**

## 3. 根因

TR 路径按**语义 + 词法相似度**检索，然后交给 LLM 一个**分数排序**的轮次窗口。
但事件排序和事件识别题需要一个横跨锚点区间的**时间排序**窗口：

- "order of three trips in the past three months" → 必须召回*全部三次*旅行并以
  **时间顺序**呈现它们；语义召回可能遗漏其中一次或以错误顺序呈现它们。
- "gardening activity two weeks ago" → 必须召回**question_date − 14d** 处的轮次，
  而非关于园艺的语义最近轮次（其可能是另一日期）。

cortex 已为每个轮次加上 `[YYYY/MM/DD]` 前缀，因此日期就在上下文中 —— 问题在于
*排序和开窗*，它们当前由嵌入分数驱动，而非时间驱动。

## 4. 具体修复（决定性，可 TDD）

对于时间题，在召回之后，按**日期与题目时间锚点的接近程度**而非（或附加于）嵌入
分数对检索到的轮次重排序，并且对于事件排序题，按**日期**排序注入的上下文。

三个决定性构件（无新模型，无图运行时）：

1. **时间锚点解析器** —— 从题目中提取锚点（"two weeks ago"、"last Saturday"、
   "past three months"、"in February"）为相对于 `question_date` 的日期窗口
   `[from, to]`。复用/扩展 `temporal-engine.ts` 中现有的 `parseRelativeOffset`。
2. **时间窗口召回** —— 当 TR 题有锚点时，优先召回日期落在窗口内的轮次（或对其
   加权提升），使锚点日期轮次胜过语义最近但日期错误的轮次。
3. **时间顺序上下文** —— 对于 `order/earliest/latest/first` 题，在截断之前按日期
   排序注入的证据轮次。

这些都是作用于 `(question, question_date, turns-with-dates)` → 有序轮次的纯函数 ——
与 `computeTemporalAnswer` 相同的决定性哲学，且它们作用于 cortex 已提取的日期。

## 5. 计划（P0 → P2）

| # | 举措 | 范围 |
| --- | --- | --- |
| **P0** | 向 TR 检索路径添加决定性的**日期锚定重排序**：解析时间锚点，按日期接近度对检索到的轮次排序/加权提升，并按时间顺序呈现事件排序证据 | 约 22 道排序/识别题 |
| P1 | 将 cortex-core 的 `MemoryGraph` 时间边接入为 TR 的*可选*召回通道（仅在 P0 通过 A/B 验证之后） | 时间边上的图扩散激活 |
| P2 | 重新审视时长算术提取（轮次内部的 "yesterday"/"next year" 相对偏移） | 约 12 道时长题，ROI 较低 |

## 6. TDD 规格（P0）

- 时间锚点解析器：针对 "N weeks ago"、"last <weekday>"、"past N months"、
  "in <month>"、"a couple of days ago" → `[from, to]` 的单元测试。
- 日期锚定重排序：锚点日期处的轮次排序高于不同日期处的语义接近轮次；
  事件排序题返回日期升序的轮次。
- 阴性对照：非时间题不变（无日期重排序）。
- 变异测试：删除日期重排序必须使某项区分性测试失败。
- 覆盖率 ≥95% 四个维度；`pnpm check` 绿色；在 TR 机制端点上进行同瞬间 4v4 A/B
  （排序/识别准确率 + 弃权），精确置换 p≤0.05，IE/MR/KU/ABS 守卫 n.s.。
