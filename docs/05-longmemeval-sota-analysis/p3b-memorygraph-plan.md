# P3b — MemoryGraph 扩散激活召回实验臂：缺口分析 + 计划

**状态：** 研究完成；待批准实施
**前身：** P3a 发生日期召回 —— 已拒绝（确定性净负面）

## 1. 判决先行 —— 诚实的 ROI 解读

P3b 是一个**接线缺口，而非一项发明**：`cortex-core` 已经交付了
`MemoryGraph.spreadingActivation`（Hebbian 权重 + logistic 显著性 +
多跳扩散 + `EdgeKind.temporal/causal/cooccurrence/semantic`），且
`cortex-eval` 已经依赖 `@agentix-e/cortex-core` —— 但基准召回路径一点都没用到它。
因此机械成本很低。

**然而**，对当前 TR/MR 未命中项的一次数据驱动归因显示，上行空间是有限的，且大多在别处：

| 能力码 | 错误 | 召回缺失（答案回合不在场） | 读者错误（答案在场，LLM 算错） |
|---|---|---|---|
| TR (127) | 31 | **6–10** | **18** |
| MR (121) | 23 | 非图形态（聚合/枚举） | — |

- TR 的主导失败是**读者侧**的（18/31：答案已在检索窗口内，但 LLM 算错了经过时间 / 顺序）。
  召回实验臂碰不到这些。
- 召回缺失的 TR 题分为**事件查找**（时间锚点定位 —— 正是 P3a 已经回退的那块领地）
  与**类别→实例缺口**（“kitchen appliance” → “a smoker”），后者是*共现*图所
  无法跨越的（它需要字面共现，而非语义上下位关系）。
- MR 的未命中是数值聚合/枚举题，而非“答案实体距问题实体一跳”。

因此预注册的预期必须克制：P3b 有可能恢复**少数几道**事件查找题，
条件是答案实体与问题实体字面共现（“jewelry” ↔ “aunt”、“music event” ↔ “parents”），
且它可能再次落在精确置换 p≤0.05 门槛之下。下面的 go/no-go 把“信号是真的但低于噪声”
当作一个被记录的负面结果，正如 P3/P3a 所做的那样。

## 2. 接线缺口（已经存在、尚未使用的东西）

`packages/cortex-core/src/graph/memory-graph.ts`：

- `MemoryGraph.strengthen(a, b, kind)` —— Hebbian 共激活，`significanceOf`
  logistic 门，权重在 (0,1]。
- `MemoryGraph.spreadingActivation(seeds, maxDepth=3, threshold=0.01)` —— 返回
  `Map<entity, activation>`，每跳 `act * weight`，每层衰减 0.5。
- `EdgeKind.cooccurrence | temporal | causal | semantic`。

`packages/cortex-eval` 已经导入 `@agentix-e/cortex-core`（binomialCdf、
welchTTest、wilsonScoreInterval、类型）。接入 `MemoryGraph` 是零依赖的。

## 3. 领先实现（网络研究）

| 系统 | 机制 | 对 P3b 的启示 |
|---|---|---|
| SPRIG (arXiv 2602.23372) | NER + 共现图 + Personalized PageRank | **零 token** 的 NER+共现+PPR 匹敌或超越基于 LLM 的图构建，快 28% |
| MemGraph | spaCy NER + 共现 + PPR，`α·vector + (1−α)·ppr` 融合，2 跳 | 混合融合公式；别名解析 |
| A-MEM | 动态笔记图（Zettelkasten） | 多跳 +27.44pp |
| HippoRAG | 面向 RAG 在 KG 上做 PPR | PPR 作为图检索原语 |
| Zep Graphiti | 双时间知识图 | 时间边是与 TR 相关的轴 |

决定性的洞见：**NER + 共现 + 扩散激活能以零 token 成本匹敌基于 LLM 的图构建** ——
这直接回应了 P3a 的失效模式（LLM 抽取既增加了成本*又*引入了干扰项）。
P3b 在抽取侧必须是零-LLM 的。

## 4. 拟定设计（零-LLM 抽取，仅追加，RRF）

### 4.1 实体抽取（确定性，无 LLM）

复用现有的 `extractLexicalKeywords` 稀有关键词通道，外加对*问题*与每个被召回的
*回合*做大写 token / `[A-Z][a-z]+` 专名扫描。这样无需结构化 LLM 调用，即可产出
候选种子实体与每回合的实体集合。（类别→实例题被明确排除在范围之外 ——
它们需要上下位关系，而非共现。）

### 4.2 图构建（逐题，确定性）

针对当前问题的上下文，构建一个 `MemoryGraph`：

- 为每一个抽取出的实体 id（规范化表面形式的哈希）执行 `ensureNode`。
- 对同一回合中的每一对实体执行 `strengthen(e1, e2, 'cooccurrence')`
  （限制在前 k 个被召回的回合，使图小而确定）。

### 4.3 扩散激活召回实验臂

- 种子 = 从问题中抽取的实体。
- `spreadingActivation(seeds, maxDepth=2, threshold=0.01)` → 邻居实体。
- 将激活的实体映射回提及它们的回合（实体→回合索引），
  产出一个按图排序的回合列表（激活分数，最优优先）。
- **仅追加 + RRF**：通过现有的 `reciprocalRankFusion` 融合
  `[semanticHits, lexicalHits, graphHits]`。绝不重排语义通道，以使
  弃权信号（`hits[0]` 语义匹配）保持稳定 —— 正是这一契约让 P3a 保持可度量。

### 4.4 范围守卫

该实验臂只为 TR `eventLookup` 题以及问题实体与答案实体字面共现的 MR 题
扩宽*回合*池。IE/KU/ABS 路径不被触及。一个 `guard` 测试断言非图路径逐字节相同。

## 5. 验收标准（科学性）

1. **TDD 先行**：为实体抽取、图构建（strengthen/significance）、
   激活→回合映射编写单元测试，以及一个**有判别力的集成测试** ——
   一道图可恢复的题（“jewelry … from whom”，`aunt` 共现）只有在图实验臂开启时
   才被追加（变异移除该实验臂会使该测试失败）。
2. **覆盖率 ≥95%**，四个维度全满足（语句/分支/函数/行）。
3. **同瞬 4v4 A/B**，在 TR `eventLookup` + MR 机制端点上，
   精确置换 + Welch + McNemar。
   - **接受**仅当目标端点以精确置换 **p ≤ 0.05** 移动，且全部 IE/MR/KU/ABS
     守卫保持平坦（无回归）。
   - 否则 **回退**并记录“真实但低于噪声”为负面结果，与
     P2/P3a 的纪律一致。
4. 以 `Lambertyan` 提交，英文注释/文档/提交信息。

## 6. 留给你的决策点

| # | 决策 | 选项 |
|---|---|---|
| D1 | 尽管上行有限仍推进 P3b？ | **A** 推进（接受低于噪声的风险）/ **B** 先转向读者侧 |
| D2 | 实体来源 | 零-LLM（稀有关键词 + 专名）—— 推荐，对 LLM 事实抽取 |

我的建议：**在零-LLM 路径上推进 P3b（D1=A，D2=零-LLM）**，
因为这是最便宜的完整 Tempr 接线步骤，也是唯一能为召回路径提供图遍历的步骤；
读者侧那 18 道题的 TR 缺口是一个*独立的、更大的*目标，召回实验臂在结构上
无法解决它，值得此后作为自己的迭代。
