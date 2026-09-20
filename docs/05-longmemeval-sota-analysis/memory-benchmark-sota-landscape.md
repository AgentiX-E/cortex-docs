# 长期 / 智能体记忆 — 权威基准与 SOTA 格局

**日期：** 2026-09-06
**范围：** 长期 / 智能体记忆的每一个权威基准、各基准上的 SOTA 竞品得分，以及 cortex 的
位置与它通过复刻竞品架构所能填补的缺口。

> **部分内容已过期（2026-09-20 注）。** §6 与 §7 写于 2026-09-06，此后有两项状态发生变化：
> **RRF 融合已被接受**（`rrf-retrieval-fusion-verdict.md`，`afd5dd5`，MR +5.25/轮，
> p = 0.0143），**图扩散激活已实测并回滚**（`p3b-graph-verdict.md`，TR 77.95% → 70.87%，
> p = 0.039，`7780071`）。请以
> [07 SOTA 推进计划](../07-sota-roadmap.md) 为当前权威路线；本文件保留其历史价值。

---

## 1. 基准格局

三大族系值得关注，它们的评测目标各不相同。只有第一族与 cortex（面向 LongMemEval-S）
可直接比较。

### A. 智能体记忆基准（核心领域）

| 基准 | 会议 / 年份 | 衡量什么 | 规模 |
| --- | --- | --- | --- |
| **LongMemEval-S / M / L** | ICLR 2025（Wu 等） | 六项技能：单会话用户/助手/偏好、多会话、时序、知识更新 | S=115K tok/500 Q · M=1.5M · L=更大 |
| **LoCoMo** | 2024（Maharana 等） | 多会话对话上的单跳 / 多跳 / 时序 / 开放域 | 1,540 Q，约 35 个会话 |
| **BEAM** | 2025（Tavakoli 等） | 100K / 500K / 1M / 10M token 单对话规模下的记忆 | 2,000 Q，10 种类型 |
| **AMB**（Agent Memory Benchmark） | 2026，中立测试台 | 跨厂商、同一答题器 + 判分器；LoCoMo/LongMemEval/PersonaMem/BEAM | 多数据集 |
| **AML**（Agent Memory Leaderboard） | 2026-08，清华/北大支持 | 7 个维度：事实召回、多跳、时序、治理、个性化、上下文学习、安全 | 文本 + 代码赛道 |
| **MemBench / PersonaMem** | 2024-2025 | 记忆写入/读取保真度、人设一致性 | — |

### B. 长上下文理解（相邻，目标不同）

这些测的是*单个*模型阅读一份长输入，而不是跨会话的记忆层 —— 因此与 cortex
**不可直接比较**，但它们界定了阅读器模型的原生长上下文能力。

| 基准 | SOTA | 备注 |
| --- | --- | --- |
| **LongBench v2**（清华/智谱） | Gemini 2.5 Pro **63.3%** | DeepSeek-R1 **58.3%**（与 Qwen3-235B 持平）；GPT-4o 51.4%；人类 53.7% |
| **InfiniteBench** | 前沿约顶级水平 | 长文本上的检索/计算/推理 |
| **BABILong** | — | 最长 1M token 的 haystack 找针问答 |
| **RULER** | — | 合成长上下文压力测试 |

**关键阅读器数据**：DeepSeek-R1 的 LongBench v2 得分（58.3%）接近 Gemini 2.5 Pro
（63.3%），因此 DeepSeek 的原生长上下文能力**并非**约束瓶颈 —— 记忆架构才是。

---

## 2. LongMemEval-S — 权威排行榜

### 2.1 高阅读器档（Claude / GPT-5 / Gemini）

| 排名 | 系统 | QA 准确率 | 阅读器 | 每题成本 |
| --- | --- | --- | --- | --- |
| 1 | agentmemory V4 | **96.2%** | Claude Opus 4.6 | ~$0.170 |
| 2 | PwC Chronos (high) | 95.6% | 增强 | $0.10–0.54 |
| 3 | Mastra OM (high) | 94.87% | GPT-5-mini | $0.130 |
| 4 | Backboard | 93.4% | GPT-4.1 | ~$0.070 |
| 5 | Ensue / OMEGA | 93.2% | GPT-5-mini / GPT-4.1 | ~$0.003–0.022 |
| 6 | MemMachine | 93.0% | GPT-5-mini | $0.005 |
| 7 | Hindsight | 91.4% | Gemini 3 Pro | ~$0.650 |
| 8 | Memax | 91.2% | Claude Sonnet | $0.046 |

### 2.2 GPT-4o 阅读器档（同口径对比）

| 系统 | QA 准确率 | 阅读器 |
| --- | --- | --- |
| Emergence（闭源 SaaS） | **86.0%** | GPT-4o |
| AgentOS（Apache-2.0） | **85.6%** | GPT-4o |
| Supermemory（单遍） | 85.86% | GPT-4o |
| Mastra OM (base) | 84.23% | GPT-4o |
| **cortex** | **83.55%** | **DeepSeek** |
| Emergence Simple | 82.4% / 80.6% | GPT-4o |
| Zep / Graphiti | 71.2% | GPT-4o |
| Mem0（独立评测） | 49.0% | — |

### 2.3 GPT-4o-mini 阅读器档（sota2.com 标准化，隔离架构）

| 系统 | QA 准确率 |
| --- | --- |
| MemCoT | **88.0** |
| Mnemis | 87.2 |
| EMem-G | 77.9 |
| Mem0 | 71.1 |
| RAG | 67.2 |
| Zep | 63.2 |
| Full-context | 55.0 |

### 2.4 决定性的跨阅读器锚点：Hindsight

Hindsight 公开了该领域最重要的单一数据点：

| 骨干模型 | LongMemEval-S |
| --- | --- |
| 20B 开源模型 + Hindsight | **83.6%** |
| full-context GPT-4o（无记忆） | 60.2% |
| Gemini 3 Pro + Hindsight | **91.4%** |

**"20B 模型 + 好架构胜过 full-context GPT-4o"** 是该领域最清晰的证据，表明在此基准上
*架构胜过参数规模*。

---

## 3. LoCoMo — 长程对话记忆

| 系统 | 准确率 | 备注 |
| --- | --- | --- |
| HyperMem（超图） | **92.73%** | GPT-4o-mini 判分 |
| Mem0（2026 算法） | 92.5% | 单遍分层 + 多信号 |
| MIRIX | 85.38% | 多智能体记忆 |
| MemMachine | 84.87% | — |
| Hindsight (20B) | 83.18% | — |
| Hindsight (Gemini 3) | 89.61% | — |
| VAC | 80.1% | MCA + FAISS + BM25 + 交叉编码器 |
| Memobase | 75.78% | — |
| Letta (MemGPT) | 74.0% | 文件系统智能体 |
| Zep | 66.0% | — |
| Mem0（旧版） | 66.9% | — |

## 4. BEAM — 百万至 10M token 规模

| 系统 | 1M nugget | 10M nugget |
| --- | --- | --- |
| Hindsight | **75.0** | **64.1** |
| Mem0 | 64.1 | 48.6 |
| AutoMem | — | 57.4 |
| Honcho | — | 40.6 |
| （多数其他） | 58–70 | 47–56 |

---

## 5. cortex 的位置 — 精确解读

cortex 在 LongMemEval-S 上为 **83.55%**，使用 **DeepSeek 阅读器**。

| 比较 | 数字 | 结论 |
| --- | --- | --- |
| vs Mastra（GPT-4o）84.23% | **−0.68pp** | cortex（阅读器更弱）基本处于 GPT-4o-Mastra 水平 |
| vs AgentOS（GPT-4o）85.6% | −2.05pp | 接近，且阅读器更弱 |
| vs Emergence（GPT-4o）86.0% | −2.45pp | 接近，且阅读器更弱 |
| vs **Hindsight（20B 模型）** 83.6% | **−0.05pp** | **cortex 的架构实质性弱于 Hindsight** |
| vs Hindsight（Gemini 3）91.4% | −7.85pp | 阅读器 + 架构缺口叠加 |

**最具诊断价值的单一数字：** Hindsight 用一个*远比 DeepSeek 弱*的 20B 开源模型达到
83.6%，而 cortex 用 DeepSeek 达到 83.55%。同为阅读器比较，cortex 的架构表现不如一个
20B+Hindsight 栈所能达到的水平 —— 也就是说，**cortex 在其当前阅读器下还有约 2–4pp 的
纯架构余量。**

> **2026-09-20 修正：上述「2–4pp 纯架构余量」严重低估。** 该估计仍以「阅读器是主要约束」
> 为前提，而这一前提已被证伪：同档阅读器（GPT-5-mini）已达 **94.87%**，更小的阅读器
> （Gemini 3 Flash）达 **96.4%** 并登顶；固定阅读器的架构极差 **37.0pp** 是阅读器差异
> **7.8pp** 的 **4.7 倍**。余量应按 **11–13pp** 计。完整归因见
> [08 阅读器判断再研究](../../08-reader-parity-analysis.md)。

---

## 6. cortex 已有什么 vs 前沿有什么

| 组件 | cortex | Emergence/AgentOS | Hindsight | HydraDB |
| --- | --- | --- | --- | --- |
| 稠密 + BM25 混合 | ✅ | ✅ | ✅（4 路） | ✅ |
| 轮次级粒度召回 | ✅ | ✅ | ✅（episode） | ✅（时序图） |
| 查询扩展 | ✅（面向操作数） | ✅ | ✅（时间增强） | ✅ |
| 双时态事实 | ✅（cortex-core） | 部分 | ✅（τ_s/τ_e/τ_m） | ✅（有效时间+事务时间） |
| **交叉编码器重排** | ❌ | ✅ Cohere rerank-v3.5 | ✅ LLM 重排器 | ✅ |
| **RRF 融合** | ✅（`afd5dd5` 已接受） | ✅ | ✅ | ✅ |
| **图扩散激活** | 已回滚（`7780071`） | ✅ ACT-R | ✅ 因果/实体/语义 | ✅ |
| **事实/观点分离** | ❌ | ❌ | ✅（4 个网络） | 部分 |
| **时间增强嵌入** | ❌ | ✅ | ✅ | ✅ |
| **按类别的阅读器路由** | ❌ | ✅ ReaderRouter | — | — |
| **DCG 会话打分** | 已试 → 拒绝 | — | — | — |

前沿共有的配方而 cortex 所缺失的：**交叉编码器重排 + RRF 融合 + 时间增强（或时序图）
检索 + 事实/观点分离。** cortex 已拥有最难的部分（cortex-core 中的双时态事实）；它尚未
把图/重排/时序图路径接入 MR/TR 检索栈。

---

## 7. 通往 SOTA 的路径 — 量化

### 7.1 在仅限 DeepSeek 的约束下（当前）

| 举措 | 预期增益 | 依据 |
| --- | --- | --- |
| 混合召回之后的交叉编码器重排（Cohere 级或本地） | +1.0–2.0pp | 前沿消融：重排是"最承重的信号" |
| ~~BM25 + 稠密 + 轮次召回的 RRF 融合~~ | ~~+0.5–1.5pp~~ | **已完成**：`afd5dd5` 接受，MR +5.25/轮，p = 0.0143 |
| ~~把 cortex-core 的关联图（扩散激活）接入 MR/TR 检索~~ | ~~+1.0–2.0pp~~ | **已回滚**：TR 77.95% → 70.87%（p = 0.039，`7780071`），路线关闭 |
| 面向 TR 的时间增强嵌入 / 时序图检索 | +1.0–2.0pp（TR） | HydraDB TR 90.97%；cortex TR 75.79% 是最大的单项技能缺口 |
| 事实/观点分离（4 网络） | +0.5–1.0pp | Hindsight 的认知清晰度 |

**合计上限（DeepSeek 阅读器）：约 85.5–88%** —— 达到/超越在 GPT-4o 下的 Emergence
（86%）与 AgentOS（85.6%），也就是说 **cortex 有可能成为其自身阅读器下第一名的开源记忆
系统**，以及公开记录中 DeepSeek 阅读器的最强结果。

### 7.2 如果解除阅读器约束

| 阅读器替换 | 预期上限 | 依据 |
| --- | --- | --- |
| DeepSeek → GPT-4o | ~88–90% | 裸 GPT-4o 92.6% 减去架构损失；Emergence 86% 是一个配方弱于 Hindsight 的 GPT-4o 系统 |
| DeepSeek → Claude Opus 4.6 | ~92–95% | agentmemory 96.2%，Hindsight 级架构 + Opus |
| DeepSeek → Gemini 3 Pro | ~91–93% | Hindsight 91.4% |

### 7.3 诚实的 ROI 排序

> **2026-09-20 更新**：以下排序为原始版本，其中第 2 项已被实测否定。当前权威排序见
> [07 SOTA 推进计划](../07-sota-roadmap.md) §2。

1. **交叉编码器重排 + RRF 融合**（P0）：纯检索，可 TDD，直接做 MR/TR 机制端点 A/B。
   每单位风险的增益最高。**注：RRF 部分已完成（`afd5dd5`）。**
2. ~~**把已有的图 + 双时态接入 TR 检索**（P0/P1）：cortex 已在 cortex-core 中拥有这些
   原语；工作是集成，而非发明。~~ **此建议已被实测否定**：图召回臂使 TR 从 77.95% 降至
   70.87%（Δ −7.09pp，15 破 / 6 修，one-sided 精确 McNemar p = 0.039），已回滚（`7780071`），
   且这是该方向连续第三次被拒。**该项不应再被分配预算。**
3. **时间增强嵌入**（P1）：小、机械、面向 TR。
4. **事实/观点分离 + 按类别路由**（P2）：更大的重构；只在 1–3 验证之后再做。

---

## 8. 判决

cortex 在 83.55%（DeepSeek）下**已经能与 GPT-4o 阅读器系统（Mastra 84.23%、AgentOS
85.6%、Emergence 86.0%）相竞争，尽管阅读器更弱**，并且**高于原论文的 Oracle（82.4%）**。
约束瓶颈不是阅读器的长上下文能力（DeepSeek-R1 ≈ 58.3% LongBench v2，接近 Gemini 2.5
Pro）—— 而是 cortex 尚未采用前沿的检索配方（交叉编码器重排 + RRF + 时序图/时间增强检索
+ 事实/观点分离）。

**不更换阅读器的可行目标：85.5–88%**，使 cortex 成为其自身阅读器下最强的开源记忆系统
以及公开记录中 DeepSeek 阅读器 LongMemEval-S 的最强结果。**SOTA（91–96%）需要更强的
阅读器**，其中每提升约 1 代阅读器大致买到 +6–9pp。
