# Cortex SOTA 推进计划（可执行版）

> 版本：v1.0 · 2026-09-20
> 基线文档：[06 代码与文档一致性审计](06-code-docs-consistency-audit.md)
> 竞品格局：[05 memory-benchmark-sota-landscape](05-longmemeval-sota-analysis/memory-benchmark-sota-landscape.md)
> 目标基准：**LongMemEval-S（ICLR 2025，Wu 等）**，全量 N=500

本文档给出把 cortex 推到权威测评 SOTA 的**可执行**路径。它替代
`05/memory-benchmark-sota-landscape.md` §7 中已失效的建议（该节仍把「图扩散激活接入 MR/TR」
列为 P0/P1，而该方向已实测并回滚，见 §2.3）。

---

## 0. 结论先行

1. **当前状态无法作为起点。** 发布的 83.55% 测于 `a52628f`，落后 `master` 55 个提交；
   在该点之后评测仪器被改写 8,326 行。**第一步必须是重测，而不是优化。**
2. **最重的瓶颈不是检索配方，而是产品路径与评测路径的分离。** 认知层（价值写入、弃权、
   巩固、冲突消解、双时态）在评测路径上调用点为零。任何在未接线的基础上继续叠加能力的
   方案，都会重复本次审计记录的同一个错误。
3. **真实可达区间：DeepSeek 阅读器下 85.5–88%**；**SOTA（91–96%）需要更换阅读器**，
   每提升约一代阅读器大致买到 +6–9pp。这不是悲观判断，而是
   Hindsight 跨阅读器数据（20B 83.6% → Gemini 3 Pro 91.4%）的直接推论。
4. **ROI 最高的单一动作是交叉编码器重排**：纯检索侧、可 TDD、机制端点明确、每单位风险
   增益最高，且前沿四家（Emergence/AgentOS/Hindsight/HydraDB）全部配备。

---

## 1. 前置契约：在被测量之前，先定义「被测对象」

### 1.1 必须新建的组合层 `cortex-memory`

审计 §6 已证明：`cortex-core` 是已验证的算法库，但没有任何包把它组合成可运行系统。
这是「认知层不在评测路径上」的根因。因此**在优化之前必须补齐这个 seam**。

| 层次 | 包 | 职责 | 状态 |
|---|---|---|---|
| 契约 + 纯算法 | `cortex-core` | `decideWrite`、`decideRetrieval`、`resolveContradiction`、`consolidate`、`MemoryGraph`、`sinkhorn`、FSRS、双时态 | ✅ 存在 ❌ 无人调用 |
| **组合层** | **`cortex-memory`（新建）** | 组合成满足 core 契约的 `MemorySystem` | ❌ **缺失** |
| 后端 | `cortex-node` | `SqliteStorage`、`PgStorage` | ✅ 存在（仅存储） |
| 提供方 | `cortex-llm` | LLM / embedding 适配器 | ✅ 存在 |
| 仪器 | `cortex-eval` | 测量任何满足 `MemorySystem` 的实现 | ✅ 存在 |

依赖方向无环：

```
cortex-core  ←  cortex-memory  →  cortex-node
                     ↑                （注入 Storage）
                     └── cortex-llm   （注入 LLM / Embedding）
                              ↑
                        cortex-eval     （依赖 cortex-memory 并测量它）
```

`cortex-eval` 自有的 `natural-language-memory.ts` **保留为对照臂**，使基准同时报告参考管线
与认知组合层——这是把「库」变成「被测系统」的关键一步，且不牺牲仪器的独立性。

### 1.2 前置件清单

| # | 前置件 | 验收判据 | 优先级 |
|---|---|---|---|
| A1 | 消解 83.55% vs 83.50% 的数字冲突 | 两份文档引用同一版本、同一分项表 | **P0** |
| A2 | 在 `31a3371` 全量重测 LongMemEval-S | 发布 N=500、4 轮、Wilson 区间、run id | **P0** |
| A3 | 评测路径说明文档 | 明确 `natural-language-memory` + `retrieval` 是当前被测对象，及其与 core 的关系 | **P0** |
| A4 | `vitest.config.ts` 强制覆盖率阈值 | 故意降覆盖的提交必须 CI 失败 | **P1** |
| A5 | 文档能力表加状态列 | 每项标注「已接线 / 已实现未接线 / 未实现」 | **P1** |

> **A4 的必要性**：当前 ≥95% 只是约定。审计确认**没有任何 `vitest.config.ts` 设置
> `thresholds`**，即规则可以被静默违反而不触发任何信号。

---

## 2. 优先序表

依赖关系：**A2 → B1 → {B2, B3} → C1 → C2**。B1 之后的每一项都必须以 B1 产出的
当前基线为对照，并遵守 §4 的预注册纪律。

### B 级：检索配方（DeepSeek 阅读器内，目标 85.5–88%）

| # | 举措 | 预期增益 | 依据 | 优先级 |
|---|---|---|---|---|
| B1 | **交叉编码器重排**（`bge-reranker-v2-m3` 或 Cohere rerank） | **+1.0–2.0pp** | 前沿四家全部配备；消融显示重排是"最承重的信号" | **P0** |
| ~~B2~~ | ~~**RRF 融合**（BM25 + 稠密 + 轮次召回）~~ — **已完成**，见 §3 | — | `rrf-retrieval-fusion-verdict.md`：ACCEPTED（`afd5dd5`），MR +5.25/轮，p = 0.0143 | ✅ |
| B3 | **时间增强 / 时序图检索**（面向 TR） | +1.0–2.0pp（TR） | HydraDB TR 90.97% vs cortex TR 75.79%——最大单项缺口 | **P1** |
| B4 | **事实 / 观点分离**（4 网络） | +0.5–1.0pp | Hindsight 的认知清晰度设计 | P2 |
| B5 | 按类别阅读器路由 | — | 依赖更换阅读器，与 C 级合并评估 | P2 |

> **B1 / B3 的排序理由**：两者都是纯检索侧、可 TDD、有明确的机制端点，
> 且不需要更换阅读器。B3 依赖 B1（重排是时序召回的放大器，顺序反了会把噪声一起放大）。

### C 级：阅读器与规模化（目标 91–96%）

| # | 举措 | 预期上限 | 依据 | 优先级 |
|---|---|---|---|---|
| C1 | 阅读器替换 DeepSeek → GPT-4o / Claude Opus 4.6 | ~88–95% | 裸 GPT-4o 92.6%；agentmemory 96.2%（Opus） | P1 |
| C2 | provider-agnostic 阅读器抽象固化 | — | 防止单点锁定；已由 `cortex-llm` 部分承担 | **P1** |
| C3 | 成本优化（每题成本对标） | — | agentmemory ~$0.170、MemMachine $0.005 | P2 |

> **C1 的量化依据**：Hindsight 用 20B 开源模型得 83.6%，换 Gemini 3 Pro 得 91.4%——
> 阅读器换代买到 **+7.8pp**。因此 91–96% 的 SOTA 区间**不可能**靠检索侧优化在 DeepSeek
> 上达成。

### D 级：完整评测覆盖（跨基准泛化）

| # | 基准 | 衡量什么 | 优先级 |
|---|---|---|---|
| D1 | BEAM-1M / 10M | 百万级 token 规模下的记忆 | P2 |
| D2 | LoCoMo | 多会话对话的单跳/多跳/时序 | P2 |
| D3 | MemoryAgentBench | 智能体记忆 | P3 |
| D4 | MemSecBench | 记忆安全（投毒防御，审计确认未实现） | P3 |
| D5 | AMB / AML | 中立测试台、跨厂商同口径 | P3 |

> **D 级的纪律**：每个基准上线前必须**自建基线复现**。当前文档中的竞品分数（Mem0 92.5
> LoCoMo、Zep 94.7 LoCoMo 等）**全部是厂商自报值**，`01` 白皮书 §5 已正确指出不能直接
> 采信——这一纪律必须贯彻到 D 级。

---

## 3. 各举措的实施与验收判据

### B1 — 交叉编码器重排

| 项 | 内容 |
|---|---|
| 落点 | `cortex-core` 新增抽象（若为纯函数）或 `cortex-llm`（若为远程调用） |
| 契约 | `Reranker { rerank(query: string, candidates: string[]): Promise<number[]> }` |
| 理由 | 保持 provider-agnostic：本地 `bge-reranker-v2-m3` 与远程 Cohere 均须可插拔 |
| 验收 | MR 与 TR 的分项准确率在配对 A/B 下同向提升；one-sided p < 0.05 |
| 反证条件 | 若 MR 提升但 TR 下降超过 MR 增益，判定为**没有净收益**并回滚 |

**为什么必须写反证条件**：`p3b-graph-verdict.md` 记录了一次 TR 召回扩展，表面合理，
实测 77.95% → 70.87%（Δ −7.09pp，15 破 / 6 修，one-sided 精确 McNemar p = 0.039）。
**同一个检索栈上的扩展会互相干扰**，因此每项都必须有单侧反证阈值。

### B2 — RRF 融合（已完成，仅需确认）

| 项 | 内容 |
|---|---|
| 现状 | `reciprocalRankFusion` **已在 `cortex-eval/src/retrieval.ts` 中实现并接线** |
| 证据 | `rrf-retrieval-fusion-verdict.md`：**ACCEPTED**（v2 `afd5dd5`），MR **+5.25/轮**，p = 0.0143 |
| 已知回归与根因 | v1（`e50c554`）被拒：RRF 重排后 `hits[0]` 不再是 cosine 最强回合，而单会话路径把 `hits[0].score` 读作弃权置信度，导致 IE 准确率 95.0% → 87.5%。修复是把两者**解耦**：RRF 决定顺序，`maxHitScore(hits)` 决定置信度 |
| 剩余工作 | 确认当前 `master` 仍启用该臂；把增益计入重测基线 |

> **修正说明**：landscape §6 把「RRF 融合」列为 cortex 缺失项（❌），这与
> `rrf-retrieval-fusion-verdict.md` 的 ACCEPTED 判决冲突。以判决文档为准——**B2 已完成**，
> 本表据此降级为「确认 + 计入基线」，不再重复投入。
>
> **可迁移的教训**：v1 的回归不是被掩盖而是被根因定位的。当一个检索栈里有两处读取
> 同一个字段（`hits[0].score`）时，改动排序语义就会静默改变置信度语义。
> **B1 重排会改排序，因此必须审计同一字段的其他读取点**——这是 B1 最主要的集成风险。

### B3 — 时间增强 / 时序图检索

| 项 | 内容 |
|---|---|
| 目标 | TR 75.79% → 80%+（HydraDB 为 90.97%，是天花板参照） |
| 已知失败路径 | 图扩散激活（`1ce76aa` → 回滚 `7780071`）：**已闭合，不再尝试** |
| 已知正确路径 | `tr-daterange-verdict.md`、`tr-occurrence-verdict.md`、`tr-turnanchor-verdict.md` 记录的臂 |
| 验收 | TR 分项 +≥1.0pp 且 overall 不回退 |

> **B3 的最大风险是被"再试一次图路径"的直觉带偏。** 该方向已连续三次被拒
> （`p3b-graph-verdict.md` 明确写 "the third consecutive rejection of a TR recall-expansion
> arm, so the line of work is closed"）。本计划**不再为它分配任何预算**。

---

## 4. 预注册纪律（不可协商）

每一项 B 级及以上举措在**派发之前**必须登记：

1. 它必须超越的**点估计**；
2. 算作成功的**效应量**；
3. **停止规则**（何时判定无效并回滚）。

**为什么这不是形式主义**：本次审计发现文档仍在推荐一条已经实测失败并回滚的路线。
没有事先登记的判据，失败的结果就会被事后合理化。预注册是防止这一点的唯一机制。

配套要求：

- **同刻 A/B**：4-vs-4 交错运行，避免时间漂移混入效应（`same-instant-ab-report.md` 的方法）；
- **配对统计**：优先精确 McNemar（配对）而非 Welch t（独立），因为问题是同一集合；
- **最小/中位/最大**：报告尾部而不只是均值；
- **Wilson 区间**：比例型指标必须给区间；
- **run id 归档**：每次派发写入 `05/run-ids/`，可复现。

---

## 5. 消融设计

每一项能力必须能回答「单独拿掉它，掉多少」。模板：

| 消融臂 | 控制变量 | 观测 | 通过条件 |
|---|---|---|---|
| `+rerank` vs `−rerank` | 同刻、同问题集、同阅读器 | MR/TR/overall 分项 Δ | 目标维度 +≥1.0pp，其他维度不回退 |
| `+RRF` vs `−RRF` | 同上 | 同上 | 已 ACCEPTED（+5.25/轮 MR） |
| `cortex-memory` vs `natural-language-memory` | 同上 | overall Δ | 认知组合层**必须**不劣于参考管线 |
| `+temporal` vs `−temporal` | 同上 | TR Δ | TR +≥1.0pp 且 overall 不回退 |

> **关键消融**：`cortex-memory` vs `natural-language-memory` 是本次审计的直接产物。
> 它的结果决定认知层的真实价值，也决定后续预算应投向认知层还是检索层。
> **在该消融出结果之前，不应再向认知层追加新能力。**

---

## 6. 里程碑

| 里程碑 | 内容 | 可证伪验收 |
|---|---|---|
| N0 | 前置件 A1–A5 完成 | `master` 当前基线公布；覆盖率阈值成为 CI 门禁 |
| N1 | `cortex-memory` 落地并接入评测 | 通过既有 `MemorySystem` 契约测试；≥95% 覆盖率、无 mock |
| N2 | 认知层消融出结果 | `cortex-memory` vs 参考管线的配对判决（可正可负） |
| N3 | B1 重排上线 | MR 或 TR +≥1.0pp，单侧 p < 0.05 |
| N4 | B3 时序检索达到 TR ≥80% | 分项复现 |
| N5 | 总成绩 85.5–88% | 全量 N=500、4 轮、区间公布 |
| N6 | 阅读器替换（C1） | 91%+ |

---

## 7. 风险与诚实边界

1. **85.5–88% 的区间是估计，不是承诺。** 它的依据是前沿系统的消融差距，而非 cortex 的
   实测增量。N3/N4 的实际结果才是证据。
2. **SOTA 需要换阅读器。** 在 DeepSeek 约束下，91%+ **不可达**——这是
   Hindsight 20B→Gemini 数据（+7.8pp）的直接推论。把「不换阅读器的 SOTA」写进任何目标
   文档都是不诚实的。
3. **换阅读器不是免费的**：每题成本、延迟、provider 可用性都会变化，且
   `02` 文档的 provider-agnostic 抽象必须能真正承载替换，而不是纸面支持。
4. **竞品分数多为自报。** 所有对标必须自建基线，不得直接引用。
5. **一次只动一个变量。** 本次审计的直接教训：同一检索栈上的多个扩展会互相干扰，
   合并上线会让归因失效。
6. **认知层可能被证伪。** N2 的结果可能是「认知组合层不优于参考管线」。若如此，
   §6.1 的 `cortex-memory` 仍是必要的（它让产品路径存在），但后续预算应全部转向检索侧。

---

## 8. 与既有文档的关系

| 既有文档 | 本计划对其的处理 |
|---|---|
| `05/memory-benchmark-sota-landscape.md` §7 | **取代**：该节 P0/P1 排序含已回滚方向（图扩散激活）与已完成项（RRF） |
| `05/memory-benchmark-sota-landscape.md` §6 | **修正**：RRF 行应标 ✅（`afd5dd5` 已 ACCEPTED），图激活行应标「已回滚」而非 ⚠️ |
| `05/longmemeval-sota-research.md` | **待消解**：83.50% 与 `SOTA-BASELINE.md` 的 83.55% 冲突（前置件 A1） |
| `03-implementation-and-acceptance-plan.md` | **对齐**：M1–M7 需标注实际完成状态 |
| cortex `SOTA-BASELINE.md` | **已修正**：加注其测点为历史锚点，非当前 `master` |
