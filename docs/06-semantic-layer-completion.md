# 语义层完成度与修复状态（2026-11-14 · master `f83f2318`）

**触发**：用户要求「结合项目目前的实现情况审查送审报告的陈述与建议，给出语义层在产品册的完成度汇报与问题修复情况说明；只有语义层完全修复以后才继续追 SOTA」。

**判定口径**：全部用**调用链**（call-chain）而不是关键字检索；每一行给出 `文件:行` 或命令；不引用任何未在本 checkout 复核的二手结论。三个「完成度」数字分别对应三种不同的定义，混用会得到互相矛盾的结论，所以它们分开列。

**本轮复核命令**（可重跑，结果见各表）：

```bash
grep -rn "KnowledgeFact\|reviseLedger\|resolveContradiction\|consolidate\|MemoryGraph\|renderBlocks" packages/cortex-memory/src --include="*.ts" | grep -v __tests__
grep -rn "'semantic'" packages/cortex-memory/src --include="*.ts"
grep -rn "type: 'episodic'" packages/cortex-memory/src/admission.ts
python3 -m pytest tools/__tests__ -q          # 2,712 passed / 19 skipped
pnpm check                                    # 绿
```

---

## 0. 一页结论

| 问题 | 答案 |
| --- | --- |
| 语义层在**产品册**（白皮书 §4 功能清单）的完成度 | 语义层 10 行：**交付口径 1/10**（能改变一次已发表 artifact 的字节）、**实现口径 7/10**（有代码有单测）、**可表示口径 0/10**（类型层写不出一个 `semantic`） |
| 语义内核（19 行可达表）现状 | **P 5 / E 5 / I 8 / T 1**；其中语义相关只有 **2 行 P**（answer-side supersession、aggregation），store-side 语义 **0 行 P** |
| 送审报告的 5 条建议 | **2 条已关闭**（T1 部分、T2 的结构阻塞）、**3 条未动**（T3/T4/T5） |
| 报告自身陈述 | **6 处需要修正**：2 处已被本项目改掉、1 处算术不可满足、3 处计数/状态漂移 |
| 是否可解禁 SOTA | **否**。语义层 7 条 exit criteria（§5）一条都未满足；S10/S9 与全部 SOTA 队列本轮**冻结** |

一句话：**产品册上的「语义记忆」这一格，代码里写不出来、产品读不到、测量没测过；报告把它定位为「缺一个 fact source」，这个定位是对的，但它给出的修法与判据里有 3 处会把人带到错的地方。**

---

## 1. 语义层在产品册的完成度

### 1.1 口径定义（先定义，再报数）

| 口径 | 定义 | 为什么需要它 |
| --- | --- | --- |
| **交付**（delivered） | 改动它会让一次**已发布 artifact 的字节**发生变化 | 这是「产品真的会因它而不同」的唯一硬证据；不含「有代码」 |
| **实现**（implemented） | `cortex-core`/`cortex-memory` 里有实现且有单元测试 | 区分「设计了」与「写了」 |
| **可表示**（representable） | 类型层能写进一个值、并且有代码读它 | `MemoryType` 那一类：写不出 = 连「未接线」都不成立 |

### 1.2 产品册的语义层 10 行（白皮书 §4）

| # | 功能（白皮书原文照抄） | 白皮书标注 | 现在的实际状态 | 证据 |
| --- | --- | --- | --- | --- |
| 3 | 价值驱动写入（VoI） | ⚠️ 已实现、**不在评测路径** | **已改变**：闸门在测量路径上，且自 `abe5bf6` 起 artifact 可观测；**收益仍未测** | `admission.ts`、`memory.ts#admissionOptions`、`admission=` 配置行 |
| 4b | 弃权的**效用决策**版本 | ⚠️ 实现未接线 | 未变 | 阈值式弃权在路径上（ABS 29.25/30），效用版无调用者 |
| 5 | 异步巩固（Hebbian + FSRS） | ⚠️ 实现未接线 | 未变：`consolidate` **0 调用者** | `grep consolidate` 仅定义/导出/注释 |
| 6 | 检索即巩固（TD(λ)） | ⚠️ 实现未接线 | 未变：TD(λ) **全仓不存在**；`sinkhorn` 已导出**从未被调用** | `math/ot.ts`、`ARCHITECTURE.md:245` |
| 7 | 双时态事实 | ⚠️ 实现未接线 | 未变：`Fact` 类型 **零构造器** | `domain/fact.ts`；全仓无 `Fact = {` |
| 8 | 冲突消解（贝叶斯融合） | ⚠️ 实现未接线 | 未变：`resolveContradiction` **0 调用者** | `contradiction/resolve.ts:21` |
| 9 | 多跳 / 关联图 | ⚠️ 实现未接线；已实测回滚 | 未变：`MemoryGraph` **0 调用者** | `graph/memory-graph.ts` |
| 10 | 抽取保真（IB） | ❌ 未实现 | 未变 | — |
| 11 | 选择性遗忘 + 遗忘权 | ❌ 未实现 | **部分成立**：遗忘权有实测（erasure 0 residual，`disclosure/session.ts`）；`consolidate` 的遗忘时钟在今天仍存量纲缺陷史（04 §4 #14） | `erasure:census` 在 `pnpm check` 内 |
| 12 | 投毒防御 + provenance DAG | ❌ 未实现 | 未变（`KnowledgeFact.references` 是 derivation 边，但无产品调用者） | `ARCHITECTURE.md:247` |

### 1.3 三个数

| 口径 | 计数 | 完成度 | 说明 |
| --- | --- | --- | --- |
| 交付 | 1 / 10（第 3 行，且仅「闸门生效」这半） | **10%** | 其余 9 行对已发表字节零影响 |
| 实现 | 7 / 10（3、4b、5、6、7、8、9） | **70%** | 11 行部分实现，10/12 未实现 |
| 可表示 | 0 / 10 | **0%** | `'semantic'` 在产品包出现 **0 次**（7 处 `semantic` 全是英文散文注释）；`admission.ts:449` 每次准入都 `type: 'episodic'` |

### 1.4 语义内核可达表（19 行）现状

`docs/AUDIT-SEMANTIC-REACH.md §3` 在 `b0fe73f` 记的是 **P 5 / E 5 / I 8 / T 1**。本轮复核未变：

- 产品包对 `SEMANTIC_KERNEL` 的 import = **0**（`semantic-reach.test.ts` 的执行式断言仍在守，本轮 `pnpm check` 绿）；
- `consolidate` / `resolveContradiction` / `MemoryGraph` / `sinkhorn` 的调用者仍为 **0**；
- 全仓唯一的非测试 `KnowledgeFact` 构造点在 **arm**：`cortex-eval/src/assumption-ablation.ts:176`。

**语义相关的 P 只有 2 行**（#18 answer-side supersession、#19 aggregation；#14 disclosure 是治理不是语义）。也就是说：**产品有 answer-side 语义，没有 store-side 语义**——这句话到今天仍然准确。

---

## 2. 送审报告的陈述复核

| # | 报告陈述 | 现在是否成立 | 证据 / 影响 |
| --- | --- | --- | --- |
| 1 | `benchmark-cortex-memory.yml:475` 把 `CORTEX_MEMORY_CONFIDENCE` **固定为 `'none'`**，闸门在结构上不可达 | **已不成立** | `f83f2318`：两个轴改为 `${{ vars.* \|\| 注册值 }}`，调度脚本每次派发无条件写。**且没有消耗输入槽**（仍 24/25，有断言）——报告只想到「交换输入槽」与「新开 workflow」两条路，第三条（变量通道）更省 |
| 2 | `report.ts` / `types.ts` / `bench-memory-arm.ts` 中**没有 `valueDistribution` 类字段** | **已不成立** | `abe5bf6`：`memoryArmConfig.admission` 带 `candidates / admitted / rejected / min / max / mean / distinct / distinctSaturated / threshold` |
| 3 | `T2 Step 2.2` 的验收判据：`distinct >= 2 && belowThreshold > 0 && aboveThreshold > 0`，按 **admitted turn** 统计 | **算术不可满足** | 接纳条件是 `value >= threshold`，所以每条被接纳的轮按构造都在阈值之上，`belowThreshold ≡ 0`。已改为**对候选轮计数**、判据 `rejected > 0 && distinct >= 2`（缺陷登记簿 #21）。照报告实现会得到一个恒为 0 的字段，然后被读成「闸门没切过东西」 |
| 4 | `CortexMemoryOptions`（`types.ts:134`）**26 个字段无一为 store** | **数字过时** | 现为 **27** 个字段（`index` 是新增的那个），仍然无一为 store。`ARCHITECTURE.md:237` 的「26 fields」同步需要改 |
| 5 | 产品自排序「**capability, not quality**」，尚无 dispatch 测过（§9.5） | **成立，但可更精确** | `self-index` 已是 arm 的注册信号（`RELEVANCE_SIGNALS['self-index']`），`buildsProductIndex()` 在 `bench-memory-arm.ts:2670`，索引由 `retrieval/search-index.ts` 构建；缺的是**一次运行**（就是验收矩阵的 `S9`，状态 `unrun`） |
| 6 | 四象限（刻意边界 / 文档-代码落差 / 测量缺口 / 交付缺口）与 T0–T5 排序 | **成立，仍然可用** | 本轮没有推翻任何一条象限判定；只是 T2 的阻塞点与判据被换掉了 |

---

## 3. 问题修复状态（按 Tracks）

| Track | 报告状态 | 现在 | 证据 |
| --- | --- | --- | --- |
| **T0 不做清单** | 待落盘 | **未落盘** | 无 `CONTRIBUTING` 条目、无 ADR；五条「不做」仍散落在审计文档里 |
| **T1 文档口径** | P0，未做 | **部分完成** | `README.md` 每条能力带 `live / library / absent` 标签 + Status 段（`abe5bf6`）；`RETRACTIONS` 新增 18/19。**未完成**：白皮书 §4 的「#3 不在评测路径」已与代码不符；`AUDIT-SEMANTIC-REACH §3` 未随 `admission` 更新；`ARCHITECTURE.md:237` 的 26→27 |
| **T2 让 A/B 可解读** | P0，结构性阻塞 | **结构阻塞已关闭，读数未取** | ① 配置：`f83f2318`（两轴可设、默认逐字节不变、输入数不变）② 可观测：`abe5bf6`（`admission` 普查）③ 判据：报告那条被证伪，已替换为候选轮口径（#21）④ 新注册：`§13.373` + `§13.373.7` 事后更正 ⑤ 派发：`43465626013`（200×2，2.85 元）**artifact 未读** |
| **T3 交付完整性** | P1 | **未动** | `cortex-memory/package.json` `files: ['dist']`、`exports: ['.']`，无 known-good assembly；`docs/USER-MANUAL.md` 存在但未写「不注入 `index` → lexical-only」的显式段；`self-index` 的质量读数 = `S9` 未跑 |
| **T4 语义层决策门** | P1，先决策 | **未动** | 无 ADR；`AUDIT-SEMANTIC-REACH §7` 的 P0-1 仍是 **Blocked, re-sequenced**，不是 Declined；`MemoryType` 的 `'semantic'` 仍不可表示 |
| **T5 corpus ownership 双模式** | P2 | **未动** | 无 `store` / `mode` 选项；字段数 27→（若加则 29） |

**结论**：报告把最紧迫的事判断为「让一次 A/B 可解读」，这个判断正确，且**那件事的代码侧已经做完**（配置 + 可观测 + 注册），只剩读 artifact。真正**一行未动**的是语义层本身（T4）与交付完整性（T3）。

---

## 4. 报告的三处「会把人带错」的地方

1. **判据 3**：`belowThreshold > 0` 按 admitted turn 统计——算术不可满足（见 §2 第 3 行）。这是本轮唯一一处「照做会得到一个恒为 0 的字段」的建议。
2. **`sourceTrust: 1` 当作「注册值」**：arm 的注册表里是 **0.5**。值域因此是 `[0, 0.5]`，`threshold=0.25` 要求「新写入的轮约 1,000 字符」；10.9 的 479/500 弃答正是同一算术的失败面。已在 `§13.373.7` 记更正。
3. **判据集合可被「把 arm 掏空」的闸门全部满足**：`rejected > 0` 与 `distinct >= 2` 在拒掉 98% 时同样成立。已补第四条 `admitted / candidates >= 0.5`，其失败读作「按现状不可判」而非「机制无效」（缺陷 #23）。

---

## 5. 「语义层完全修复」的可验证定义

只有下列 **7 条全部成立**，才解禁 SOTA 队列。每条都给了可执行判据，不用「看起来修好了」。

| # | 判据 | 验证方式 | 现状 |
| --- | --- | --- | --- |
| **E1** | **fact source 存在且 additive**：产品能构造 `KnowledgeFact`，来源是**已计算的** supersession 状态（不新增模型调用、不替换原文） | 存在非测试构造点，且其输入来自 `supersede.ts`/`memory.ts:1603` 的计算结果；一条行为级测试证明同语料下 prompt 字节**因该事实而变** | ❌ 唯一构造点在 arm |
| **E2** | **消费者接线**：`assemble` → `reviseLedger` → `resolveContradiction` 在产品路径被调用 | `semantic-reach.test.ts` 的命中清单**非空**且打印出符号；reach table 对应行改 **P** | ❌ 命中 = 0 |
| **E3** | **可表示**：`MemoryType` 的 `'semantic'` 有写有读（读 = 影响 selection/渲染/调度之一）**或**两个不可达值被删除且文档同步撤回 | 一条「写入 semantic → 读回并改变行为」的测试；或删除后的类型快照 | ❌ 0 次写入、0 次读取 |
| **E4** | **charter 四机制结清**：`consolidate` / `resolveContradiction` 从 0 调用变为**有产品调用者**，或由 ADR 显式 **Declined** 并给出理由与代价 | `grep` 出调用点（非测试）；或 ADR 文件存在且被 `ARCHITECTURE.md` 引用 | ❌ 两者皆 0，无 ADR |
| **E5** | **三表同步**：哨兵测试、`AUDIT-SEMANTIC-REACH §3`、`ARCHITECTURE.md` 状态表**同一提交**内一致 | `pnpm check` 绿 + 三处 diff 在同一 commit | ❌ 未开始 |
| **E6** | **语义层自身有测量**：至少一次 paired 读数或离线 trace 指标（FEB-30 四项），且**不伤准确率**（判据 `deltaQuestions ≥ −5`，与 S10 同口径） | artifact 有 run id 与配置行；McNemar 双侧 | ❌ 无 |
| **E7** | **对外口径一致**：README、白皮书 §4、`ARCHITECTURE.md` 中语义层行与代码一致 | `pnpm docs:crosscheck` + 人工对表 | ⚠️ README 已改，白皮书/ARCHITECTURE 未改 |

> **E3 是这一套里最容易被跳过的一条**，也是「语义层」这个词配不配用的分界线：一个写不出来的 `MemoryType` 值意味着连「未接线」都不成立——它不是「功能没开」，是「功能无法被表达」。

---

## 6. 修复顺序（P0 → P2）与每步验收

| 步 | 内容 | 验收 | 回滚 |
| --- | --- | --- | --- |
| **P0-1** | 写 ADR：语义层走 **B（接线）**，因为用户要求「完全修复」；同时记录 A 路径的代价，供未来推翻时复用 | ADR 落盘并被 `ARCHITECTURE.md` 引用 | 纯文档 |
| **P0-2** | fact source：从 `supersede.ts` 的 span+date 授权状态派生 `KnowledgeFact`（additive，0 新模型调用） | 行为级测试：同语料下 prompt 字节因事实而变；`promptDigest` 对照 | 删除生产者，回到当前字节 |
| **P0-3** | 接线 `assemble` → `reviseLedger` → `resolveContradiction`，逐个子句接，每接一个跑一次 `semantic-reach.test.ts` 看它点名 | 哨兵命中清单非空；reach table 改 P；E5 同提交 | 逐条 revert |
| **P0-4** | `MemoryType`：写入 `'semantic'`（E1 的事实）+ 一个读取点（渲染块选择或调度） | 「写入→读回→行为变化」测试 | 删读取点 |
| **P0-5** | `consolidate` / `resolveContradiction` 结清（接线或 Declined） | E4 判据 | — |
| **P1-1** | 语义层测量（E6）：离线 trace + 一次 paired | `deltaQuestions ≥ −5` | 测量不改产品 |
| **P1-2** | 三表 + 白皮书 + `ARCHITECTURE.md:237` 的 26→27 | `pnpm check` + `docs:crosscheck` | revert |
| **P2** | T3 交付完整性（assembly 导出、默认配置显式化）、T5 双模式 | `manual:check`、`reuse:census`、`erasure:census` | 新增可选字段 |

**冻结**：`S10`（500×4）、`S9`（500×4）与一切「刷分」派发在 E1–E7 全绿前**不派发**。已派出的 `43465626013` 是**仪器验证**（200×2，2.85 元），不属于 SOTA 队列，其 `admission=` 行照读，但其分数**不进任何产品表**。

---

## 7. 与 SOTA 的关系（写在此处，防止误读）

当前注册值 91.25%，已发表最高 96.4%（Exabase M-1，top-50）/ 95.6%（Maximem Synap，全 500，7.4K tok/题）；成本 9,201 tok/题，比 Synap 贵 24%。差距 −4.35 至 −5.15 点。

**这些数字不因语义层修好而自动改善**：语义层是「产品配不配叫记忆层」的问题，SOTA 是「同样的题答得更准/更便宜」的问题。两者的交集只有一个——E6 的语义层读数若为负，它就不该进 SOTA 队列，而应作为一次负结果入 `RETRACTIONS`。所以顺序只能是：**先把语义层变成真的（E1–E7），再谈分数**。
