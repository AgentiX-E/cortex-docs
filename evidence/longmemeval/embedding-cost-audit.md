# 嵌入 API 成本审计

**复核状态（2026-09-06）**

本次审计中提出的三项发现，其实施状态均已核验：

| # | 发现 | 状态 | 证据 |
|---|---|---|---|
| P0 | 派发切换到 `diagnostics_limit=100` | ✅ 已实施 | 所有 `dispatch_ab_*.sh` 均使用 `diagnostics_limit=100` |
| P1 | 诊断过滤掉 assistant 轮次 | ✅ 已实施 | `2c47c92 perf(eval): stop embedding assistant turns in retrieval diagnostics`；`retrieval-diagnostics.ts` 中有两处 `role === 'assistant'` 过滤 |
| P2 | 诊断改为混合检索（与生产对齐） | ⚠️ 部分 | 查询扩展已镜像，但诊断仍使用 `retrieveTopKByQueries`（无词法回退），而生产使用 `retrieveTopKByQueriesHybrid`；且 `recommendedThreshold` 从未被消费（`abstainThreshold` 仍通过环境变量硬编码为 0.5） |

**复核结论**：嵌入成本已被优化到极限，没有新的优化空间。缓存在多次运行间持久化
（模块级 `Map` + GitHub Actions 缓存文件），主 QA 的 500 题用户轮次是正确性所必需的
**理论下界**，且各消融与诊断共享同一模块级缓存（每段文本只嵌入一次）。剩余的 P2 缺口
是正确性问题——"诊断的召回度量的是弱检索"——而非成本问题，且因其影响可忽略，因为
`recommendedThreshold` 从未被消费。**本轮无需改动任何代码。**

---

**结论先行**

嵌入缓存已经做得很好（跨运行持久化、文本级去重、float32 序列化），**重复运行的成本
已接近零**。但发现了三处真实的浪费，其中两处可直接节省约 **40–50%** 的嵌入调用：

1. **`diagnostics_limit=0` 是成本放大器**（派发层，无需改代码）：召回诊断把全部 500 题
   对整份 haystack 做嵌入，只为计算一个**不影响评分的召回统计量**。改回默认抽样 100
   可节省约 40%。
2. **召回诊断不过滤 assistant 轮次**（代码层）：主检索路径会过滤掉 assistant 轮次，但
   诊断不加区分地嵌入一切。assistant 轮次约占 haystack 的 **50%**，且**从不被主检索使用**
   ——纯属浪费。
3. **（顺带发现的正确性缺陷）** 召回诊断所用的检索路径与系统实际使用的路径**不一致**：
   诊断走 `retrieveTopK`（无过滤、无扩展、无混合），而系统使用
   `retrieveTopKByQueriesHybrid` + `filter(isUserTurn)` + 查询扩展。因此
   `benchmark-diagnostics.json` 中的 `recall@k` 与 `recommendedThreshold` 反映的是一种
   系统**根本不使用**的检索。

---

## 1. 成本模型：一次完整运行实际嵌入了什么

| 阶段 | 调用 | 是否过滤 assistant？ | 是否命中缓存？ |
|---|---|---|---|
| `checkEmbeddingDeterminism` | 4 段短文本 | — | 可忽略 |
| `computeRetrievalDiagnostics`（轮次级召回） | **整份 haystack**（当 `diagnostics_limit=0`） | **否** | 冷（第一轮） |
| `computeSessionRetrievalDiagnostics`（会话级召回） | 相同文本 | **否** | 命中缓存（新增 0） |
| `runNaturalLanguageBenchmark`（主 QA） | 用户轮次（`filter(isUserTurn)` / MR `filter(!isAssistantTurn)`） | **是** | 命中缓存（新增 0） |
| MR / TR / KU 三项消融 | 相同 haystack | 是 | 命中缓存（新增 0） |

**要点**：主检索路径（`retrieveTurns` 第 473 行、`answerSessions` 第 505 行）在嵌入**之前**
过滤掉 assistant 轮次，但两项召回诊断却通过 `turnText` 嵌入了用户 + assistant 的**全部**内容。

## 2. 量化

MR 证据会话的实测轮次构成（121 题 × 全部证据会话）：

| 轮次类型 | 数量 | 占比 |
|---|---|---|
| user | 1832 | 50.0% |
| assistant | 1832 | **50.0%** |

也就是说，haystack 中约一半是 assistant 轮次，而主检索**从不使用**它们。缓存日志也佐证了
这一点：一次完整运行缓存了 **170,095** 个向量，其中约一半是从未被使用的 assistant 轮次。

### 这能省多少

| 方案 | 每次完整运行的嵌入量 | 节省 |
|---|---|---|
| 当前（`diagnostics_limit=0` + 不过滤） | U + A ≈ 170k | — |
| ① `diagnostics_limit=100`（派发层） | A(100) + U(500) ≈ 102k | **~40%** |
| ① + ② 诊断也过滤 assistant（代码层） | U(500) ≈ 85k | **~50%** |

> 注：主 QA 本身必须嵌入全部 500 题的用户轮次（正确性所需），因此 **~85k 用户轮次是理论下界**，无法进一步降低。①② 向该下界逼近。

## 3. 顺带发现：诊断与真实检索不一致（正确性缺陷）

`computeRetrievalDiagnostics` 使用 `retrieveTopK`（无过滤、无查询扩展、无混合词法召回），
但系统实际使用 `retrieveTopKByQueriesHybrid`（过滤用户轮次 + 查询扩展 + 词法回退）。后果：

- `benchmark-diagnostics.json` 中的 `recallAt1/recallAt5` 偏低（它们度量的是弱检索）；
- `recommendedThreshold`（命中分数的第 25 百分位）基于错误的检索分布。

这解释了为何 `ABSTAIN_THRESHOLD` 一直通过环境变量硬编码为 0.5，而非采用诊断推荐的阈值
——诊断本身度量的就是错误的东西。

## 4. 建议（按 ROI 排序）

| # | 变更 | 层级 | 节省/修复 | 风险 |
|---|---|---|---|---|
| **P0** | 后续 A/B 派发使用 `diagnostics_limit=100`（默认值）而非 `=0` | 派发命令 | 节省 ~40% | 无（逐题的 `llmRaw` 走主运行的 `limit=0`，不受影响） |
| **P1** | `computeRetrievalDiagnostics` / `computeSessionRetrievalDiagnostics` 过滤 assistant 轮次（与主路径对齐） | 代码 | 再省 ~10% + 修复一致性 | 低（需要锁定测试） |
| **P2** | 让诊断使用与系统相同的 `retrieveTopKByQueriesHybrid`（带扩展 + 混合），使召回/阈值反映真实检索 | 代码 | 修复正确性 | 中（改变诊断语义；报告字段语义需一并更新） |

---

**关于当前的 A/B**：补量后，我以 `diagnostics_limit=0` 重新派发了一个 4+4 同一时刻 A/B
（进行中）。**下一批派发我将改用 `diagnostics_limit=100`。**

P1/P2 属于代码改动，需要 TDD + 本地回归 + 提交（Lambertyan）。是否现在就实施 P1
（诊断过滤 assistant 轮次）？它既省成本又修复一致性，且改动小、风险低。
