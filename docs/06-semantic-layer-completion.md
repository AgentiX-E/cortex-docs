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
| 语义层在**产品册**（白皮书 §4 功能清单）的完成度 | 语义层 10 行：**交付口径 1/10**（能改变一次已发表 artifact 的字节）、**实现口径 7/10**（有代码有单测）、**可表示口径 1/10**（第 98 轮起：`MemoryType` 的 `'semantic'` 有处写、有处读，见 §13） |
| 语义内核（19 行可达表）现状 | **P 5 / E 5 / I 8 / T 1**（送审时快照；第 98 轮为 **P 11 / E 2 / I 5 / T 1**，见 §13 读数表）；送审时语义相关只有 **2 行 P**（answer-side supersession、aggregation），store-side 语义 **0 行 P** |
| 送审报告的 5 条建议 | **2 条已关闭**（T1 部分、T2 的结构阻塞）、**3 条未动**（T3/T4/T5） |
| 报告自身陈述 | **6 处需要修正**：2 处已被本项目改掉、1 处算术不可满足、3 处计数/状态漂移 |
| 是否可解禁 SOTA | **否**。8 条 exit criteria（§5）现为 **7 关闭（E1 / E2 / E3 / E4 / E5 / E7 / E8）、1 全红（E6）**；E6 是唯一需要派发的一条，也正是 S10/S9 的解禁条件，本轮**冻结** |

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
| 可表示 | 1 / 10 | **10%** | 送审时是 0：`'semantic'` 在产品包出现 **0 次**，`admission.ts:449` 每次准入都 `type: 'episodic'`。第 98 轮起 `semantic-facts.ts` 的 `memoryForUpdate` 写出 `type: 'semantic'`，`retention.ts` 读它并据此决定有界 store 先丢哪一条；普查同时报出 `cortex-core: MemoryType` **离开**孤儿账本 |

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
| **T2 让 A/B 可解读** | P0，结构性阻塞 | **有读数，但有缺陷**（§8） | ① 配置：`f83f2318`（两轴可设、默认逐字节不变、输入数不变）② 可观测：`abe5bf6`（`admission` 普查）③ 判据：报告那条被证伪，已替换为候选轮口径（#21）④ 新注册：`§13.373` + `§13.373.7` 事后更正 ⑤ 派发：`43465626013` 已读——**普查四个判据前三个通过、第四个失败（0.397 < 0.5）**，且 run 自审抓到 **#24（一个字段两个含义）** |
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

只有下列 **8 条全部成立**，才解禁 SOTA 队列。每条都给了可执行判据，不用「看起来修好了」。（第 8 条 E8 由 §8 补充；此句原写「7 条」，是补 E8 时漏改的一处计数。）

| # | 判据 | 验证方式 | 现状 |
| --- | --- | --- | --- |
| **E1** | **fact source 存在且 additive**：产品能构造 `KnowledgeFact`，来源是**已计算的** supersession 状态（不新增模型调用、不替换原文） | 存在非测试构造点，且其输入来自 `supersede.ts`/`memory.ts:1603` 的计算结果；一条行为级测试证明同语料下 prompt 字节**因该事实而变** | ✅ **关闭**（§11）：构造点在 `memory.ts` → `semantic-facts.ts`，输入是 `supersede.ts` 的 verdict；`semantic-carry.test.ts` 三条件字节对照（空 store / 开关关 / 两者都有）；0 新模型调用（开与关各 3 次调用） |
| **E2** | **消费者接线**：`assemble` → `reviseLedger` → `resolveContradiction` 在产品路径被调用 | `semantic-reach.test.ts` 的命中清单**非空**且打印出符号；reach table 对应行改 **P** | ✅ **关闭**（§12）：白名单 5 → 7，且每个值符号都要求**调用点**而非 import；reach 表行 3/6/8/10/11 同提交改 **P**（P 从 5/19 到 11/19）。**2 接 / 1 结清**：`assemble` 与 `reviseLedger` 已接，`resolveContradiction` 由 ADR §6.1 实测 Declined——喂它可以给出的唯一输入，胜者是账本刚驳掉的那个值 |
| **E3** | **可表示**：`MemoryType` 的 `'semantic'` 有写有读（读 = 影响 selection/渲染/调度之一）**或**两个不可达值被删除且文档同步撤回 | 一条「写入 semantic → 读回并改变行为」的测试；或删除后的类型快照 | ✅ **关闭**（§13）：写 = `memoryForUpdate`，读 = `retention.ts` 的 `Record<MemoryType, RetentionRule>`（影响淘汰）；判据是一对——同样 9 次吸收、只差「一个窗口读过 record 0」，对照丢掉 record 0、机制保住它并丢掉 record 1；8 个变异全杀，其中两个只杀机制测试、对照保持绿 |
| **E4** | **charter 四机制结清**：`consolidate` / `resolveContradiction` 从 0 调用变为**有产品调用者**，或由 ADR 显式 **Declined** 并给出理由与代价 | `grep` 出调用点（非测试）；或 ADR 文件存在且被 `ARCHITECTURE.md` 引用 | ✅ **关闭**（§14）：四个机制全部结清——`consolidate` 为 **Declined + 算术**（ADR §6.2：一个 store 只有一个时钟 ⇒ 它测到的流逝为 0；它写的状态在产品包里**零读取**；它的动作方向正是 `not-later` 要防的），`resolveContradiction` 为 Declined + 算术（§6.1），`MemoryGraph` 为**带读数的 Declined**（77.95% → 70.87%，McNemar p = 0.039），`sinkhorn` 为 inert Declined；`Fact.derivedFrom` 作为第二套机制被拒。判据的「或」被用到了，但用的是算术而不是沉默 |
| **E5** | **三表同步**：哨兵测试、`AUDIT-SEMANTIC-REACH §3`、`ARCHITECTURE.md` 状态表**同一提交**内一致 | `pnpm check` 绿 + 三处 diff 在同一 commit | ✅ **关闭**（§12）：哨兵（白名单 7 项 + 调用点断言）、reach 表六行、`ARCHITECTURE.md` 两行、`USER-MANUAL.md` 选项表与示例、`PREREGISTRATION` §13.376 全部同一提交 |
| **E6** | **语义层自身有测量**：至少一次 paired 读数或离线 trace 指标（FEB-30 四项），且**不伤准确率**（判据 `deltaQuestions ≥ −5`，与 S10 同口径） | artifact 有 run id 与配置行；McNemar 双侧 | ❌ 无 |
| **E7** | **对外口径一致**：README、白皮书 §4、`ARCHITECTURE.md` 中语义层行与代码一致 | `pnpm docs:crosscheck` + 人工对表 | ✅ **关闭**（§11）：`USER-MANUAL.md` 新增 `semanticCarry` 行与可编译示例，`manual:check` 强制（34/34 选项有示例）；`ARCHITECTURE.md` 新增「Semantic update carry」行 |
| **E8** | **证据组装正确**（§8 新增）：artifact 字段自述语义（每题实际路由 + 交付窗口角色直方图）+ `unclassified` 计数；一条行为级测试证明「声明 `evidenceRoles=['user']` 的窗口不含被排除角色」 | 审计读 `route` 而不是从 `capability` 反推；角色对照读产品自己的 `lastRoleCensus()` 而不是 eval 侧正则 | ✅ **关闭**（§10）：`#resetPerQuestion`（6 测试 6 变异）+ `lastRoute()` / `lastRoleCensus()` 贯通到 artifact（9 测试 9 变异），两层合计 15 变异全杀 |

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

---

## 8. 筛查读到了：判据 4 失败，而 run 的自审抓到一个更重要的缺陷

`43465626013`（200 题 × 2 次，2.85 元，head `f83f2318`）在 16:57 结束，**conclusion = failure**，失败在 `Audit the artifact against itself` 这一步，不在测量本身（测量步骤 success，产物已上传）。

### 8.1 普查第一次给出了数

```
admission=candidates:198582+admitted:78884+rejected:119698+min:0.008+max:0.500+mean:0.220+distinct:64+
```

| # | 判据 | 读数 | 判定 |
| --- | --- | --- | --- |
| 1 | `candidates > 0` | 198,582 | **通过** |
| 2 | `rejected > 0` | 119,698（占候选 60.3%） | **通过**——闸门真的切了，而且切是**数**出来的 |
| 3 | `distinct >= 2` | 64（饱和标记 `+`） | **通过（作为下限）** |
| 4 | `admitted / candidates >= 0.5` | **0.397** | **失败** |

判据 4 的失败按预注册读作「**按现状不可判**」，不是「闸门无效」。而分布说明了阈值为什么是猜的：`mean 0.220`、`max 0.500`。`sourceTrust=0.5` 把天花板压到 0.5，于是 `0.25` 是**区间的中点**而不是**总体的中点**——可达区间的一半落在语料实际产出的均值之上。下一个阈值从这份分布取（`0.10–0.15`），并且下一次筛查必须自己报出 `admitted / candidates > 0.5`。

### 8.2 这份 artifact 的分数不可引用

200 题样本里 `IE` 占 86 题，参考管线在其中 72 题弃答、只对 2 题（2.3%），因此参考读数 38.50%、本臂 51.00%（+12.50pp，McNemar p = 2.61e-2）。`§13.361.3` 已记录「200 题总体与 500 题反号」；这不是新发现，也不进任何产品表。

### 8.3 新的缺陷（登记 #24）：一个字段两个含义

| | |
| --- | --- |
| 审计行 | `FAIL roles evidenceRoles=['user'] on ['multi-session','temporal']; 4 window(s) carry an assistant turn, first 28dc39ac` |
| `28dc39ac` 实际交付 | **11 轮，11 轮全是 assistant**；`goldOverlap.carried = 0` / 30 条 gold user 轮 |
| 产品自己的正则会把它们当 assistant 吗 | **会**——11 条全部匹配 `^\[[^\]]+\]\s*(user|assistant)\s*:` |

两条路只有一条成立，而且都能被检验：

- 若 `turns` 是**交付集**：过滤器**没生效**（或该路径没接），这是产品缺陷；
- 若 `turns` 是**候选池**：审计在读一个过滤前的字段，却用「窗口」去描述它，**检查本身指向了错的集合**。

无论哪条，都是同一个病：**同一字段在两个组件里含义不同**——正是普查这一层刚刚修掉的病，往下一层又出现了一次。artifact 目前**没有任何字段**能区分这两条，因此修复的第一步是让字段自述语义，并补 `unknown`/`filtered` 计数：让「角色过滤生效了多少」是一个数，而不是从列表反推。

### 8.4 闸门与角色的交互，这一条不依赖上面的结论

`length` 是 `min(1, len/2000)`，而本语料里 **assistant 轮比 user 轮长**。所以长度闸门会**先淘汰 user 轮**。`28dc39ac` 就是它的极端形态：30 条 gold user 轮全被拒，剩下的是 assistant 文本，`goldOverlap.carried = 0`。这个交互没有任何人注册过，它是「先用筛查验仪器、再花 28.5 元买入场券」的顺序救回来的。

### 8.5 对修复状态与门槛的影响

| 项 | 变化 |
| --- | --- |
| T2（让 A/B 可解读） | **从「阻塞」变为「有读数但有缺陷」**：结构阻塞已闭、普查可用、判据 4 失败、且抓到一个字段二义缺陷。500 题对照对**仍然不派发** |
| 语义层 exit criteria | 新增 **E8**：证据组装正确性——`turns` 语义自述 + `unknown/filtered` 计数 + 一条「角色过滤后窗口不含被排除角色」的行为级测试 |
| 下一步顺序 | ① 字段语义与计数（E8）→ ② 从分布重定阈值并复筛（判据 4 > 0.5）→ ③ 才轮得到 E1–E7 的语义层接线 |
| SOTA 队列 | **仍冻结**。这份 artifact 不是分数，是两个缺陷 |

---

## 9. E8 第一步：那 4 个 `roles` FAIL 不是过滤器失效，是**整条记录错位**

`43465626013` 的审计报 `FAIL roles ... 4 window(s) carry an assistant turn`。§8.3 把它读成「要么过滤器没生效，要么审计读错了集合」，并把「长度闸门先砍 user 轮」当作 `goldOverlap.carried: 0` 的解释。**两个解读都错**，artifact 自己就带着反驳。

### 9.1 过滤器一直在工作

`evidenceRolesRoutes` 只覆盖 `multi-session` 与 `temporal`，也就是 57 道 MR/TR 题。其中 **53 道交付的窗口 100% 是 user 轮**。过滤器从来没有失效。

### 9.2 四个例外的共同点：它们是别人的记录

| 记录 | 交付首轮 | 与谁逐字相同 | 本题 gold |
| --- | --- | --- | --- |
| `28dc39ac` | `[2023/05/20 (Sat) 20:20] assistant: Based on your description ... Hwang's Kitchen's ...` | index 101（`38146c39`） | 30 条 user 轮，关于 open-world games |
| `gpt4_4fc4f797` | `[2023/04/24 (Mon) 19:17] assistant: New Orleans is an amazing city!` | index 169（`6aeb4375_abs`） | 11 轮，关于汽车悬挂 |
| `gpt4_7fce9456` | `[2023/05/20 (Sat) 02:16] assistant: I think there's been a misunderstanding!` | index 154（`6b168ec8`） | 30 轮，关于看房 |
| `gpt4_a1b77f9c` | `[2023/05/11 (Thu) 02:24] assistant: I'm happy to help! However, I'm a large language model` | index 124（`f9e8c073`） | 36 轮，关于阅读周数 |

`rawOutput` 一起被搬走：`28dc39ac` 的是 index 101 的 `1. [2023/05/27 (Sat) 07:11] Turbinado sugar ...`，`gpt4_7fce9456` 的是 index 154 的 `3`，`gpt4_4fc4f797` 的是 index 169 的 `INSUFFICIENT_EVIDENCE`。**被复制的是整条记录，不是一个字段。**

四者全部 `answer: null`，且是那份 artifact 里**唯一** `promptVariants: 2` 的四条。

### 9.3 机制：清零写了两处，漏了六处

`CortexMemory.#declinedEmpty` 清了 `#lastWidth` 与 `#lastIndex`，注释里给的理由对另外六个字段**逐字适用**：它们都是「每问一写、arm 每问读一次」的状态，留下的值是**错配**而不是陈旧读数。

| 字段 | 之前 | 现在 |
| --- | --- | --- |
| `#lastRawOutput` | 残留上一题的模型输出 | `null` |
| `#lastReview` / `#lastVote` | 残留 | `null` |
| `#lastRetrievedContext` | **残留上一题的窗口** | `null` |
| `#lastAdmittedEvidence` | **残留上一题的 offer** | `null` |
| `#lastPromptEvidenceChars` | 残留 | `null` |
| `#lastPromptText` | 残留（`promptDigest` 因此也错） | `null` |
| `#lastWidth` / `#lastIndex` | 已清 | 已清（并入同一方法） |

修法不是补六行，而是把规则**命名一次**：`#resetPerQuestion()`，由**两个** reader 之前的出口共用——`#declinedEmpty` 与 `answerAbstention` 的检索闸门。第二个出口此前也是直接 `return null`。

`null` 而不是 `[]`，契约写在字段自己的 docstring 里：`[]` = 「reader 被触达、什么也没带」，`null` = 「reader 未被触达」。offer 也一并清空——它确实在 abstention 路径上算过，但 artifact 把它与交付**成对**发布，而 `question-record.ts` 把 `turns.length < evidenceTurns` 定义为「预算砍掉了轮」；`turns: []` 配 `evidenceTurns: 5` 会被读成一次裁剪。

### 9.4 这次修复不动分数，动的是**归因**

四道题修前 `correct: false`、修后 `correct: false`（`answer` 本就是 `null`），所以 `43465626013` 的总分一字不变。改的是：这四行不再声称描述一个窗口；此后任何对 decline 题的 `goldOverlap` / `evidenceTurns` / `unscoredChars` / `promptDigest` 的读数，都是关于**那一题**的。

### 9.5 E8 状态

| E8 的三项要求 | 状态 |
| --- | --- |
| 一条行为级测试证明「decline 不继承上一题」 | ✅ `decline-resets-capture.test.ts`，6 条，6 个变异全杀 |
| 一条行为级测试证明「声明 `evidenceRoles=['user']` 的窗口不含被排除角色」 | ✅ 已有 `evidence-roles.test.ts`（11 条），本轮复核仍绿 |
| artifact 字段**自述**语义 + `unknown`/`filtered` **计数** | ❌ **仍缺**：`turns` 是交付集这一点只写在源码 docstring 里，artifact 本身没有 `route` 字段、也没有过滤计数 |

所以 **E8 从「红」变为「2/3」**，剩下的那一项是纯增量可观测性，不再是缺陷修复。

### 9.6 下一步（顺序未变）

1. **E8 收尾**：artifact 记录每题**实际执行的路由**（dispatch 在 `benchmark.ts` 里本来就知道，不必靠 capability 猜），并记录交付窗口的**角色直方图**（用产品自己的 `roleOf`，不是 eval 事后用正则反推）
2. 从 distribution 重定阈值复筛（判据 4 > 0.5）
3. E1–E7 的语义层接线

`S10` / `S9` 的 500×4 对照对**仍在冻结区**。

---

## 10. E8 关闭：artifact 现在自己说得清「走了哪条路、窗口里是什么角色」

第 9 节修的是「decline 不继承上一题的捕获」。E8 还剩两项，都在这轮做完：**每题实际执行的路由**，以及**交付窗口的角色直方图**——而且必须由**产品自己**报出，不是 eval 事后推。

### 10.1 为什么不能用 artifact 已有的两个字段

| 问题 | artifact 原来有的 | 为什么不算答案 |
| --- | --- | --- |
| 这题走了哪条路？ | `capability`（`IE`/`MR`/`TR`/`KU`/`ABS`） | 那是**数据集**的词，不是**臂**的词。`TR` 题在未声明 `answerTemporal` 的系统上会落到 flat 路径；`ABS` 可以带 `single-session-assistant` |
| 窗口里是什么角色？ | `memoryArmConfig.evidenceRoles`（`["user"]`） | 那是过滤器的**指令**，不是**结果**。指令分不清「过滤跑了并排除了 3 轮」与「过滤器根本没到达这条路由」 |

两处缺口在同一个 run 上合流：审计用 `capability` 推出该检查的路由，报了 4 个 FAIL，而 artifact 没有任何字段能说这 4 题实际走了哪条路——于是只能手工重建记录，而重建给出的答案是第三种：**那 4 条是 decline，带走了上一题的窗口**（§9）。

### 10.2 改动，按层

| 层 | 字段 | 它说什么 |
| --- | --- | --- |
| `cortex-memory` | `lastRoute(): TurnCapRoute \| null` | 这题**从哪个入口进来**，在任何闸门之前设置，**decline 不清** |
| `cortex-memory` | `lastRoleCensus(): RoleCensus \| null` | 交付窗口的角色构成，用**过滤器自己用的那个分类器**数 |
| `cortex-eval` | `RetrievalCapture.route` / `.roleCensus` | 每题捕获，与既有四项同一个开关 |
| `cortex-eval` | `RetrievalCaptureVectors` | `evaluateWithScorerDetailed` 返回、`ablation.ts` 转发的两个向量 |
| `cortex-eval` | `QuestionRecord.route` / `.roleCensus` | artifact 携带；系统不报时**缺席** |
| `cortex-eval` | `QuestionRecordInput.route` / `.roleCensus` | **required + nullable**，让 bound reducer 无法像当年丢掉 `featureConfig` / `promptChars` 那样把它们丢掉 |

捕获回调从六个位置参数改成一个对象。理由不是风格：新加的两项是**总是一起走的一对**，而只想要最后一项的调用方得为此写四个 `null`。

`lastRoute` 的「decline 不清」是与其它八个槽位**相反**的规则，所以写在了字段自己的注释里：其它槽位是 reader 侧读数，没到 reader 就没有读数；路由是入口归属，在任何闸门之前就知道——而「走了 multi-session 路径、在 reader 之前就关了」正是审计看 decline 时最需要的那句话。

### 10.3 三个状态，用算术而不是散文说清

| 状态 | `route` | `roleCensus` | 含义 |
| --- | --- | --- | --- |
| 报了 | `'flat'` / `'multi-session'` / … | `{counts, unclassified, total}` | 系统说了 |
| 报了「什么都没有」 | — | `{counts: {}, unclassified: n, total: n}` | 分类器一个角色都没读出来 |
| 缺席 | 字段不存在 | 字段不存在 | 系统没有这个 accessor |

直方图是封闭算术：`sum(counts) + unclassified === total`，而 `total` 是 artifact 的 `turns` **同一个窗口**的长度——不是 `evidenceTurns`（那是 offer）。在上一层取直方图会满足自己的加法却描述一个模型没看过的窗口，这正是 `§13.262` 在 prompt 字段上记过的 delivery/coverage 分裂。

`unclassified` 单独成桶而不是叫 `unknown`：分类器的词表属于调用方，它完全可以返回字符串 `"unknown"` 作为一个角色，那时叫 `unknown` 的字段就有两个含义。而过滤器契约说「角色读不出的轮**保留**」，所以 `unclassified > 0` 是逃生口在工作、`evidenceRoles: ["user"]` 下 `assistant > 0` 才是过滤器没工作——**这正是审计分不开的那两个读法**。

`evidence-bound` 与 `report-write` 各有一条测试断言它**穿过 reduction 不变**：直方图数的是 bound 之前的交付，bound 是 run 之后的 artifact 设置。

### 10.4 15 个变异，其中 4 个第一次活了下来

这一轮最值钱的部分不是实现，是**第一遍变异跑出 4 个存活**：

| 存活（第一遍） | 说明什么 |
| --- | --- |
| 循环收集了两个向量但不返回 | 测试只测了 `runBenchmark` 的 `onRetrieved`，没测 `evaluateWithScorerDetailed` 的返回值 |
| 捕获时把 route 写死成 `'flat'` | 同上：那条匿名回调根本没被任何测试走到 |
| bound reducer 丢掉 route | `evidence-bound.test.ts` 直接调 `buildQuestionRecords`，绕过了 `report-write.ts` 的私有 `withEvidenceBound` |
| arm 把读到的 route 写死成 `null` | 没有任何测试跑完整 arm 到 record |

四者都是「实现了但没有一条测试经过那一层」。补完后：**9 + 6 = 15 全杀**。

| 组 | 变异数 | 全杀 |
| --- | --- | --- |
| 产品侧（`cortex-memory`） | 9 | ✅ |
| eval 侧（捕获 / record / reducer / arm） | 6 | ✅ |

另外，导出普查在**当小时**抓到一个我自己写的孤儿：`RetrievalCapture`。它的消费者（回调类型）是模块私有的，所以外部也不需要命名它——于是撤回导出，而不是加进基线。这是两轮里第二次「门禁抓到同一轮写下的导出」。

### 10.5 读数

| 项 | 值 |
| --- | --- |
| `pnpm check` | **绿**（`test:tools` / `guard:*` / `census:check` / `coverage:gate` / `acceptance:check` / `docs:crosscheck` / `format`） |
| TS 测试 | **6,161**（+26：memory 1,358 / eval 3,423 / core 928 / ai 327 / storage 125） |
| 覆盖率 | 166 文件、16 豁免、**0 ratchet**；`report-write.ts` 与 `memory.ts` 均 100/100/100/100 |
| 导出普查 | 1,173 → **1,176** exports（+3，全有调用者）、465 orphan **不变**、0 新增 |
| 变异 | **15 / 15 红** |
| 派发花费 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 10.6 位置：语义层 8 条里的第 1 条关闭

| 判据 | 状态 |
| --- | --- |
| E1 fact source | ✅ **关闭**（第 96 轮，§11） |
| E2 消费者接线 | ❌ 命中 0 |
| E3 `MemoryType` 可表示 | ❌ 0 写 0 读 |
| E4 四机制结清 | ❌ 0 调用、无 ADR |
| E5 三表同步 | ⚠️ 半做（第 96 轮：哨兵 + reach 表 + ARCHITECTURE 同提交；`assemble` 行待 E2） |
| E6 语义层测量 | ❌ 无 |
| E7 对外口径 | ✅ **关闭**（第 96 轮，§11：`manual:check` 强制 34/34） |
| **E8 证据组装正确** | ✅ **关闭** |

**8 条里 1 条关闭、1 条部分、6 条全红。**（这是第 95 轮的读数。第 96 轮把 E1 与 E7 关掉、E5 做到一半，见 §11。）下一项是 **E1（fact source）**——它是 E2/E3/E4 的前置：没有事实就没有可装配的语义单元；有了事实，`assemble → reviseLedger → resolveContradiction` 才有输入，`MemoryType` 的 `'semantic'` 才有写入方。

`S10` / `S9` 的 500×4 对照对**仍在冻结区**。

### 10.7 一句必须写清的话

E8 让 artifact 说得清「走了哪条路、窗口里是什么角色」，但**它一个字也没让答案更准**。它的价值在下一轮：当 E1–E7 的接线真正改变 prompt 字节时，能分辨「字节变了因为语义层」与「字节变了因为别的原因」的，就是这两个字段。**仪器完备不等于测量完成**。

## 11. 第 96 轮：事实源落地，以及它逼出的「守卫从未生效」

### 11.1 三件独立的事，按落地顺序

| # | 事 | 判据 |
| ---: | --- | --- |
| 1 | `docs/DECISION-SEMANTIC-LAYER-ROUTE.md`（cortex 仓）：语义层走 **B 接线**，并把 A 路径逐项定价 | ADR 落盘并被 `ARCHITECTURE.md` 引用（P0-1） |
| 2 | `semantic-facts.ts`：把 `supersede.ts` 已算出的 span+date 授权铸成两个 `KnowledgeFact` + 一条 `supersedes` 边 | 非测试构造点、0 新模型调用、additive（E1） |
| 3 | `semanticCarry` 开关 + `UPDATES:` 段 + `semanticCarryCensus()` | 三条件字节对照（E1）；`manual:check` 强制文档（E7） |

**为什么这条路而不是「从语料推断 supersession」。** 后者已被 `docs/MEASURE-SUPERSEDE-REACH.md` §2 关闭三次：最紧的规则触碰 77 个窗口、删掉其中 36 个的 gold、对它注册的四道题**一个被取代的值都没移除**。前者的三道检查（逐字引文、日期同 record、record 更晚）比任何 token 启发式都强，而且**已经付过费**。

**为什么默认关。** 三条各自足够：默认开会改所有已发布 artifact 的字节、使其无法从代码复现；E6（paired 读数）`unrun`，默认开等于先给药后注册；而开关是让字节 delta **可断言**的唯一办法。

### 11.2 那个缺陷，因为它比功能本身重要

`evidenceRecords` 要求「行首第一个非空字符是 `[`」，而 `formatEvidence` 的默认标签是 `` `${index + 1}. ` ``。**真实 prompt 里没有一行以 `[` 开头**，所以它把整段 evidence 切成一条 record。

后果里最重的一条：`§13.371` 的 `not-later` 守卫——为「不要把正确答案换成被它取代的旧值」而写，并且在 `ed4ddc30` 上做过测量——**在生产路径上从未执行过**。测试没抓到，因为每个 fixture 都是无编号字符串：测试同意的是代码，不是系统。

### 11.3 位置

| 判据 | 第 95 轮 | 现在 |
| --- | --- | --- |
| E1 fact source | ❌ | ✅ |
| E2 消费者接线 | ❌ | ❌（`assemble` / `reviseLedger` / `resolveContradiction`；哨兵已从「零 import」改为「白名单 + 必须被调用」） |
| E3 `MemoryType` | ❌ | ❌ |
| E4 四机制结清 | ❌ | ❌（ADR 已落盘；`MemoryGraph` 记为有读数的 Declined，另三个仍「未决定」） |
| E5 三表同步 | ❌ | ⚠️ 半做 |
| E6 语义层测量 | ❌ | ❌（预测已注册：`deltaQuestions === 0`，非零即跨题泄漏） |
| E7 对外口径 | ⚠️ | ✅ |
| E8 证据组装 | ✅ | ✅ |

**3 关闭 / 1 半做 / 4 全红。** 下一步 **E2**——现在有事实可喂了。

### 11.4 一句必须写清的话

E1 证明了「产品会因为一个授权过的事实而改变 prompt 字节」，**它没有证明这让答案更准**。E6 是那个问题，而 §13.375.5 的预测说：在本题库上「更准」的空间是零，因为每道题自带语料、每个更新都到不了别的题的窗口——真正能检验机制的总体是**一次会话里多题共享一份语料**，而本活动还没有这样的总体。

## 12. 第 97 轮：账本接进块，被取代的值不再被当作事实呈上

### 12.1 一个只有接上才看得见的缺陷

第 96 轮的块长这样：

```
UPDATES:
fact:     30 dozen  [state]
status:   replaces "20 dozen"
fact:     20 dozen  [state]
status:   superseded by "30 dozen"
```

`20 dozen` 是**已被取代**的值。它以 `fact:` 行、与被取代它的值同等的权重出现，唯一区分两者的是读者必须自己解析的一条关系行。

问题不在 `renderBlocks`。问题在**整条路径上没有任何东西写过 `refuted`**：两个 fact 根本没有 assumptions，`reviseLedger` 的 `apply` 找不到 `persistence` 可改，原样返回——一个被 import、被调用、却完全惰性的机制，正是 `AUDIT-SEMANTIC-REACH.md` §4.3 标价为「43 次机制翻转换 46 次损害」的那种失败，由**接线的顺序错**造成。

### 12.2 四步，每一步都不能省

| 步 | 调用 | 省掉会怎样 |
| ---: | --- | --- |
| 1 | `deriveAssumptions(fact, frame)` | 没有账本条目就没有东西可驳，`apply` 原样返回 |
| 2 | `buildKnowledgeUnit(...)` | 先校验再改：反过来会让被拒的 unit 留下一个已改的 fact 集 |
| 3 | `reviseLedger(facts, { edges })` | 写出 `refuted` / `confirmed`，这是「边」与「驳斥」的差别 |
| 4 | `assemble({ …, omitFrame: true })` | 唯一的出口：拒绝被驳斥的 fact **并且**渲染块，所以不存在第二条渲染路径 |

`frame.at` = 较晚那条 record 的时刻，也就是每条 assumption 的 `openedAt`：两个 fact 是在**同一个瞬间**进入账本的——这次替换被授权的瞬间。块随后按同一时刻读账本，而不是按墙上的 now 读。省掉它，`deriveAssumptions` 把所有 assumption 记在 epoch 上，`assumptionPenalty` 会把这个模块能构造的**每一个** unit 都报成 `aged`——而这个数字是看不见的（`penalty.reason` 不进渲染），所以它只能被测试钉住，不能留给 artifact。

块现在是：

```
UPDATES:
fact:     30 dozen  [state]
status:   replaces "20 dozen"
assumed:  confirmed
```

**什么都没丢**：关系行仍然引用了被取代的值。变的只是它不再被**当作事实呈上**。

### 12.3 顺手补上的内核缺口

`renderBlocks` 从语义块第一天起就带 `omitFrame`，它自己的注释就点名了这个调用方；`assemble` 却没有办法把它传下去，于是「花在渲染结果上的预算」在替一行调用方印不出来的东西买单。`AssembleInput.omitFrame` 补上了它：加法、默认 `false`、试探渲染与交付渲染从此量同一件事。

另一条路——拿 `served` 自己渲染——被否掉了，因为它会丢掉 `assemble` 算出来的 conflict `flags`，而调用方自己的输出里看不出这个丢失。

### 12.4 `resolveContradiction` 结清为 Declined，理由是算术

不是「还没做」，是**实测**：把这一对按事实源的顺序喂进去，唯一站得住的输入（两根 fact 的 `confidence` 与 `sourceTrust` 相等，因为 `KnowledgeFact` 没有这两个字段）让后验在 0.999 打平，胜负由 `Map` 的第一个键决定，也就是数组顺序，也就是 **`20 dozen`**——账本刚驳掉的那个值。

| 喂入顺序 | 胜者 | 后验 |
| --- | --- | --- |
| `[before, after]`（产品的顺序） | **`20 dozen`** | 0.999 |
| `[after, before]` | `30 dozen` | 0.999 |

一个调用点会变成「改变答案、而且改坏」的装饰。落盘在 `DECISION-SEMANTIC-LAYER-ROUTE.md` §6.1。E2 因此是 **2 接 / 1 结清**，不是 3/3——把这条写清楚，比凑一个调用点重要。

### 12.5 读数

| 项 | 值 |
| --- | --- |
| `pnpm check` | **绿**（含 `manual:check`：31 示例、34/34 选项、2 张契约表） |
| TS 测试 | **6,212**（+7；memory 1,406、eval 3,423、core 931、ai 327、storage 125） |
| 覆盖率 | 167 文件、16 豁免、**0 ratchet**；memory stat 99.86 / bran 99.67 / func 100 / line 100 |
| 变异 | **13 / 13 红**（首轮存活 1 个：试探渲染忽略 `omitFrame`——补了一条「预算取两种成本的中间值」的测试） |
| 导出普查 | 1,180 / 715 / 465 三项不变（`renderSemanticUpdate` 出、`assembleSemanticUpdate` 入），**另撤回 1 个**自写孤儿 `SemanticBlock` |
| reach 表 | **P 5/19 → 11/19**：行 3、6、8、10、11 同提交改 P，行 12 记为 **Declined** |
| 派发 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 12.6 位置

| 判据 | 第 96 轮 | 现在 |
| --- | --- | --- |
| E1 fact source | ✅ | ✅ |
| **E2 消费者接线** | ❌ | ✅ **2 接 / 1 结清**：`reviseLedger` + `assemble` 已接并被调用（哨兵白名单 5 → 7，且要求调用点），`resolveContradiction` 记为实测 Declined |
| E3 `MemoryType` | ❌ | ❌ |
| E4 四机制结清 | ❌ | ⚠️ **半做**：`resolveContradiction` 已 Declined（ADR §6.1，算术可见）；`consolidate` 仍**未定** |
| E5 三表同步 | ⚠️ 半做 | ✅ **关闭**：哨兵、reach 表六行、`ARCHITECTURE.md` 两行、`USER-MANUAL` 同提交 |
| E6 语义层测量 | ❌ | ❌（预测未变：500 题上 `deltaQuestions === 0`，非零即跨题泄漏） |
| E7 对外口径 | ✅ | ✅ |
| E8 证据组装 | ✅ | ✅ |

**5 关闭 / 1 半做 / 2 全红。** 剩余最短路径是 **E3**（`MemoryType` 写 `'semantic'` + 一个读取点），随后 E4 的 `consolidate` 与 E6。

一句话：**产品的 prompt 里现在只有一条「值变了」的记录，而且旧值不再以事实的身份出现；为此它也第一次让账本真的写了字——上一轮那个块，是把一个已被驳倒的值和取代它的值并排印出来，只靠一行关系区分。**

## 13. 第 98 轮：`MemoryType` 第一次既被写、也被读

### 13.1 一个字段，三个成员，零个读者

`domain/memory.ts:4` 声明 `'episodic' | 'semantic' | 'procedural'`。到第 97 轮为止：`admission.ts:449` 写死 `'episodic'`，`createMemory` 默认 `'episodic'`，**没有任何代码读过这个字段**（不是选择，不是渲染，不是 FSRS——FSRS 读的是 `stability`）。`'semantic'` 在整个仓库里出现的地方只有一处：那个联合类型的声明本身。

这不只是「语义层没接线」，是**无法表示**：没有值可写，也没有东西会读。E3 的判据原文就是冲着这个来的——*a settable label nobody reads*。

而产品里唯一一个「关于世界的记忆」（相对于「对某个窗口的读数」）的容器，是 `CortexMemory` 的语义槽：8 条被授权的替换，每条是一个带 `supersedes` 边的 `KnowledgeUnit`。它持有 `SemanticUpdate`——一个 unit、一个 fact 顺序、一个 anchor——**里面一个 `MemoryValue` 都没有**。所以产品内存本体论的唯一落点，恰好是内存类型从未到达的地方。

所以 E3 不是「给类型加个标签」。一个内存层的分类学，它的主张就是「不是所有记忆都是同一种东西」；一个有兩種内容、却只有一种类型的 store 说不出这句话，而代价正好在淘汰上：`shift()` 交出的是**持有最久**的那条，对观察是对的，对知识是错的。

### 13.2 写入：五个字段各有来源，三个最容易编造的都留空

`semantic-facts.ts` 新增 `memoryForUpdate`——一条被授权的更新**所是**的那个 `MemoryValue`。

| 字段 | 值 | 来源 |
| --- | --- | --- |
| `id` | `update.key` | 去重键，所以一条更新就是一条记录 |
| `content` | 渲染出的块 | prompt 真的会印出的字符，由 `assemble` 产出而不是在这里描述一遍 |
| `type` | `'semantic'` | 主张本身 |
| `source` | 记录头 `[date] speaker:` | 授权所读的那条记录，**不是** `'supersede'`——那说的是机制名，不是出处 |
| `createdAt` / `lastAccessedAt` | `now` | store 的注入时钟，**不是** `learnedAt`：一条 2026 年被吸收、语料日期是 2023 的条目，不能读起来比持有它的 store 还老 |

`value`、`confidence`、`sourceTrust`、`stability`、`difficulty` 全部交给 `createMemory` 的默认值，也就是一个被准入的 turn 所携带的同一组数。一条 `value: 1` 的语义条目，是关于未来效用的一句没有观察支撑的话。

写这条记录顺带逼出一个修复。`source` 一开始是 `2. [2023/03/12 …] user:`——**渲染器的位置前缀**。那个数字是「某一次渲染里的第几个 turn」，同一条记录在前面多三个 turn 的窗口里就是 `5. `，于是同一句内容的出处会在两次渲染之间变。`splitRecord` 现在剥掉前缀，用的是 `supersede.ts` 找记录边界的那条模式。

### 13.3 读取：表驱动，第二个元素是计数而不是时间戳

`retention.ts` 是 `Record<MemoryType, RetentionRule>`，`leastRetained` 比较它产出的那一对。

| 类型 | 秩 | 为什么 |
| --- | --- | --- |
| `semantic` | `[lastAccessedAt, reads]` | 靠**被使用**留住；没有任何窗口引用过的条目最先走 |
| `episodic` | `[createdAt, 0]` | 一个 turn 是对一个窗口的读数；后来的窗口引用过它几次，不是它还值不值得持有的依据 |
| `procedural` | `[createdAt, 0]` | 同上，写出来而不是默认掉，所以表里没有沉默的成员 |

用表而不是 `if (type === 'semantic')`，理由很具体：后者的另外两个成员会退化成一个注释，而将来加第四个成员时会**落进 `else` 恰好做的事**，而不是编译错误。

第二个元素是**读回计数**，理由不是偏好。产品的时钟是注入且固定的（`CortexMemoryOptions.now`），store 给每条记录盖同一个瞬间，所以同一个实例内每条 `lastAccessedAt` 都相等——无论有没有窗口引用过它。只用 `[lastAccessedAt]` 的秩排序不了任何东西，而断言它的测试会**在读回从未发生**的 store 上通过。计数是 store 真的观测到的量，所以 tie-break 是它。

`reads` 存在 store 自己的记录上，**不写进** `MemoryValue.value`：后者的契约是 `[0, 1]`，生产者是准入闸门；两个尺度共用一个字段，正是 `math/fsrs.ts` 在时间维度上花了一整段 docstring 修掉的缺陷。

### 13.4 对照：一次读回，两个不同的被驱逐者

`semantic-memory-type.test.ts` 让两个 store 各走 9 次吸收（第 8 次填满边界，第 9 次越过），只差**一件事**：

| 条件 | store 看到了什么 | 谁被驱逐 |
| --- | --- | --- |
| A 对照 | 8 条更新，中间没有窗口 | `record 0`，最旧的那条 |
| B 机制 | 8 条更新，一个窗口读过 `record 0` | `record 1`，它之后的那条 |

一个不读 `type` 的 store——以及它替换掉的 `shift()`——在 A 和 B 上到达同一个状态。**只有这一对**才能把「规则读了类型」和「规则恰好和插入顺序一致」分开，这也是为什么单独一条 B 只是关于代码的断言，而不是关于产品的。

`semanticCarryCensus()` 增加 `stored`：一个**按 `MemoryType`** 而不是按事件的普查。8 条 `episodic` 在那个对象的每一个其他数字上都是 8 次吸收；类型普查是产品自己的分类学在读本里唯一出现的地方。

### 13.5 八个变异，全部被杀

| # | 变异 | 杀死它的测试 |
| ---: | --- | --- |
| 1 | `type: 'semantic'` → `'episodic'` | 四条端到端全红 |
| 2 | `leastRetained` → `return 0`（旧的 `shift()`） | **只有**机制测试，对照仍绿 |
| 3 | `stored.reads += 1` → `+= 0` | **只有**机制测试 |
| 4 | 剥前缀的正则复原 | `source` 测试 |
| 5 | `content` → `''` | `content` 测试 |
| 6 | `id` → `crypto.randomUUID()` | `id` 测试 |
| 7 | `createdAt` → `learnedAt` | 时间戳测试 |
| 8 | `source` → 正文 | `source` 测试 |

第 2、3 个是关键：各自**只杀机制测试、对照保持绿**。这才是「这一对是因果的，不是并列的」的证据。

### 13.6 普查自己抓到的东西

`tools/export-census.mjs` 报出 `cortex-core: MemoryType` **离开**了孤儿账本——因为 `retention.ts` 现在 import 它。它原本被归为 `referenced-locally`（符号有活的调用点，只是 `export` 关键字多余）——但对一个联合类型成员来说，这个分类本身就是问题：类型被导出、被文档引用、被**零处读取**。

同一门禁还抓到本轮写下又撤回的两个导出：`retentionRank`（排序和它喂的那个选择是同一个决定，所以边界是 `leastRetained`）和 `Retainable`（外部没有东西需要命名那个参数类型）。这是连续第五轮，门禁在**写下它的同一轮**里报出了作者刚声明的符号。

### 13.7 读数

| 项 | 值 |
| --- | --- |
| `pnpm check` | **绿**（`manual:check`：31 示例、34/34 选项、2 张契约表；字段数未变，仍 28） |
| TS 测试 | **6,229**（+17：memory 1,422（+16）、core 932、eval 3,423、ai 327、storage 125） |
| 覆盖率 | **168** 文件（+1：`retention.ts`）、16 豁免、**0 ratchet**；memory stat 99.86 / bran 99.67 / func 100 / line 100；`retention.ts` 与 `semantic-facts.ts` 均 100/100/100/100 |
| 变异 | **8 / 8 红**（其中第 2、3 个只杀机制测试、对照保持绿） |
| 导出普查 | 1,180 → **1,182** exports、715 → **718** with caller、465 → **464** orphan（`cortex-core: MemoryType` 离开账本，因为它第一次被 import）；**另撤回 2 个**自写导出 `retentionRank`、`Retainable` |
| 门禁自检 | `cortex-core` 的 `export-census-gate` 在基线更新前**红过**（总数不匹配），这正是它该做的事 |
| reach 表 | **不变，P 11/19**——`MemoryType` 不在那 19 行里，它是 §5.2 说的行 1 前提 |
| 派发 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 13.8 位置

| 判据 | 第 97 轮 | 现在 |
| --- | --- | --- |
| E1 fact source | ✅ | ✅ |
| E2 消费者接线 | ✅ | ✅ |
| **E3 `MemoryType`** | ❌ | ✅ **关闭**：`memoryForUpdate` 写、`retention.ts` 读、驱逐结果随之改变；对照 + 机制成对断言，8 个变异全杀 |
| E4 四机制结清 | ⚠️ 半做 | ⚠️ 半做（`consolidate` 仍未定，E4 拥有它） |
| E5 三表同步 | ✅ | ✅ |
| E6 语义层测量 | ❌ | ❌（预测未变：500 题上 `deltaQuestions === 0`，非零即跨题泄漏） |
| E7 对外口径 | ✅ | ✅ |
| E8 证据组装 | ✅ | ✅ |

**6 关闭 / 1 半做 / 1 全红。** 剩下的两条是同一条：E4 的 `consolidate`（要么一个调用点，要么一个显式 Declined），以及 E6——唯一需要派发的一条，而它正是 `S10`/`S9` 解禁的条件。

### 13.9 产品册这一列终于不是 0

§1.3 的三个口径里，「可表示」的定义是**类型层能写进一个值、并且有代码读它**。送审时它是 **0 / 10**，理由是 `'semantic'` 在产品包里出现 0 次、`admission.ts` 每次准入都写 `type: 'episodic'`。

第 98 轮之后它变成 **1 / 10**：一行写得进、读得出。这不是「实现了一行功能」，而是「产品册的第三列从不可满足变成部分可满足」——一个可以逐行推进的计数，而不是一个恒为 0 的断言。

交付口径仍是 **1 / 10**、实现口径仍是 **7 / 10**：`semanticCarry` 默认关，500 题上预测字节不变，E6 未跑，所以没有任何一行能被说成「改变了已发表 artifact」。可表示性提高不等于交付提高，这两个数必须分开读。

一句话：**store 现在知道它手里哪一条是知识、哪一条只是读数，并且据此决定先丢哪一条——为此它第一次写下了一类型，也第一次有一个读者因为这个类型而做了不同的决定。**

## 14. 第 99 轮：遗忘时钟的输入是空集，而它写的东西没人读

### 14.1 E4 的判据里有一个「或」，本轮用的是第二个分支

E4 的原文是 **charter 四机制结清**：`consolidate` / `resolveContradiction` 从 0 调用变为**有产品调用者**，**或**由 ADR 显式 **Declined** 并给出理由与代价。判据两条路，但不给第三条：**沉默不算**。

四个机制现在全部落地，只是落法不同：

| 机制 | 结清方式 | 证据形态 |
| --- | --- | --- |
| `MemoryGraph`（Hebbian 多跳） | **带读数的 Declined** | 接进时序路径后被测量淘汰：77.95% → 70.87%，修好 6 个、弄坏 15 个，精确 McNemar p = 0.039 |
| `resolveContradiction`（对数几率融合） | **Declined + 算术** | ADR §6.1：喂它唯一可辩护的输入（那一对事实），返回的正是账本刚驳掉的值，后验 0.999 由数组顺序决定 |
| `consolidate`（FSRS 遗忘时钟） | **Declined + 算术**（本轮） | 下面三条，每条都有可检验形态 |
| `sinkhorn`（最优传输蒸馏） | **inert Declined** | 无读数、无调用者；删除它是另一个决定 |
| `Fact.derivedFrom` | **作为第二套机制被拒** | `KnowledgeFact.references` 已经是派生边，`revision.ts` 已经在它上面级联 |

「带读数」和「有算术」不是同一种证据，而「有算术」和「没人到过」也不是——这一轮的全部工作量就在于把第三种变成第二种。

### 14.2 三条理由，每条都能被检验

**(1) 它测到的流逝时间，在一个 store 内部恒为 0。** 一个 store 只有一个时钟（`CortexMemoryOptions.now`，一个数字），`memoryForUpdate` 用它同时盖 `createdAt` 和 `lastAccessedAt`。于是：

| 量 | 值 | 为什么 |
| --- | --- | --- |
| `now − lastAccessedAt` | `0` | 一个时钟，一次盖戳 |
| `retrievability(0, 1)` | `1` | `exp(0)`；stability 默认一天 |
| 默认阈值 | `0.01` | `exp(-4.6)`，即**四点六个稳定日之外** |
| 能删掉的条目 | `0` | 差的不是一点余量，是这辈子的余量 |

不是「偶尔不删」，是**永不可能删**——只要 store 是一个实例一个时钟。而一个没有任何 access record 的 review 趟，没有东西可 review。

**(2) 它写的状态，产品包里零个读者。** review 趟写 `stability` / `difficulty`，遗忘趟读 `stability`。`packages/cortex-memory/src` 里 `.stability` 出现 **0 次**。所以 FSRS 状态是 `consolidate.ts` 与 `fsrs.ts` 之间的闭环：一个写、一个读，没有任何做决定的模块碰它。接上去，等于把某字段按每次读回乘 1.25（`review` 的零间隔地板）然后交给没人。

`semantic-reach.test.ts` 现在断言这个 0，于是这个拒绝是**自取消的**：哪天产品模块读了 `.stability`，那条测试立刻红，拒绝就得按它想要的东西重新论证一遍。

**(3) 它的动作方向，正是 `not-later` 存在的理由。** 遗忘是「因为时间过去了，所以删掉」。而那条条目不是对某个窗口的观察，是一条替换——它的语料现在仍然写着 `30 dozen`。删掉它不会让这句话变假，只会让 prompt 退回证据，那里旧值 `20 dozen` 无标记地躺着。这正是 §13.371 的 `not-later` 守卫要防的那个结果，也是上一轮实测抓到的那个缺陷（被驳倒的值被当成事实印出来）的另一条到达路径。

而 store 真正有的那个问题是「越过 8 条边界时丢哪一条」——E3 已经用读秩（`lastAccessedAt`，再用读回计数）回答了。再加一条衰减规则，就是对同样八个位置加**第二条淘汰规则**，而两条规则恰好在最要紧的那个案例上分歧：一条旧但承载着当前答案的条目。

### 14.3 顺路抓到的陷阱：这是一个真 bug，不是拒绝的一部分

遗忘趟原本读 `Date.now()`，而它用来算年龄的条目，是由**调用方的时钟**盖的戳。套件看不见：`consolidate.test.ts` 与 `consolidation-clock.test.ts` 的每一个 fixture 都盖 `Date.now()`，于是两个时钟在套件拥有的每一个输入上都一致——和 `AUDIT-CONSOLIDATION-CLOCK.md` 记录的单位缺陷完全同型，只是往前挪了一个参数。

它咬的恰好是**最可能来接线的那个调用者**。replay 会把 `now` 钉在语料日期；今天跑一个批次，它量的是 2023 到今天：

| 调用者 | 条目盖的戳 | 遗忘趟用的钟 | `forgotten` |
| --- | --- | --- | --- |
| 新进程，`now = Date.now()` | 现在 | 现在 | `0` |
| replay，`now` 钉在语料日期 | 2023-03-12 | 墙钟 | **整库** |
| replay，修复后 | 2023-03-12 | `now` | `0` |

`now` 现在是**必填参数**，没有默认值：默认 `Date.now()` 只对「用墙钟盖戳的调用者」正确，对其他人静默错误。模块头写着「pure, side-effect-free orchestration」——读墙钟的时候这句话是假的，现在是真的，而**签名是让它成立的东西**。

`consolidation-clock.test.ts` 里两行 `@ts-expect-error` 钉住这个形状：

```ts
// @ts-expect-error -- no options at all: the batch instant has no default.
const noOptions = () => consolidate(build(), new MemoryGraph(), []);
// @ts-expect-error -- other options given, clock still missing, still refused.
const noClock = () => consolidate(build(), new MemoryGraph(), [], { decay: false });
```

第二行才是要紧的那个。第一行只说了第四个参数必填；第二行说：一个给了**别的选项**的作者，仍然不能省略时钟——这才是现实里的漏法，也是「可选字段 + `?? Date.now()` 兜底」会放过去的那一种。

### 14.4 四个变异

| # | 变异 | 杀死它的东西 |
| ---: | --- | --- |
| 1 | 遗忘趟改回 `Date.now()` | 核心库的「批次瞬间盖戳的条目不被遗忘」——`1 failed` |
| 2 | `now?: number` + `?? Date.now()` | `tsc`：`TS2578 Unused '@ts-expect-error' directive` |
| 3 | `lastAccessedAt` 取 `learnedAt` 而不是 store 时钟 | 盖戳测试**与**流逝时间测试——`2 failed` |
| 4 | 某个产品模块读 `.stability` | `semantic-reach.test.ts` 的 reach 警报——`1 failed` |

第 2 条是**类型级杀死**，也是唯一能永久关住这个陷阱的一条：兜底会把第二个时钟请回来，而不改动任何一条断言——因为套件里每个 fixture 都显式传 `now`。

### 14.5 两个文档漂移，本轮一并修

- **README 说 `consolidate` 做「episodic → semantic promotion」。它不做。** 它的三件事是 FSRS 复习、共激活强化、阈值淘汰；「提升」在产品里确实存在，但那是 `memoryForUpdate` 在做，不是它。这句话从送审起就在，本轮改掉。
- **`06` 的结论行上一轮漏改**：E3 在第 98 轮关闭，而 §1.2 的「5 关闭 / 1 半做 / 2 全红」还写着 E3 红。这就是「三表同一 commit」那条规则存在的原因——同一个 commit 里，代码与 README 改了一处，`06` 的结论行没改。
- **ARCHITECTURE 的 FSRS 行**原本说「`consolidate` has no caller, so FSRS is reachable only transitively」，现在它说的是**为什么没有 caller 是一个决定**，以及两个已记录的缺陷。

### 14.6 读数

| 项 | 值 |
| --- | --- |
| `pnpm check` | **绿**（`manual:check`：34/34 选项；字段数未变，仍 28） |
| TS 测试 | **6,235**（+6：core 935（+3）、memory 1,425（+3）、eval 3,423、ai 327、storage 125） |
| 覆盖率 | **168** 文件、16 豁免、**0 ratchet**；core 99.60 / 98.40 / 99.78 / 99.82，memory 99.86 / 99.67 / 100 / 100；`consolidate.ts` **100 / 100 / 100 / 100**（`options = {}` 的默认分支随必填参数一起消失） |
| 变异 | **4 / 4 杀**：运行时 1 条、类型级 1 条（`TS2578`）、盖戳 1 条、reach 1 条 |
| 导出普查 | **1,182 / 718 / 464，三个数都不动**——本轮没新增导出，也没撤回导出（签名改动不进计数） |
| reach 表 | **P 11/19 不变**；第 13 行「Consolidation / forgetting (FSRS)」的 Caller 从 `none` 改成 `none — Declined` |
| 门禁自检 | 本轮没有触发（没有新导出、没有删导出），但 reach 警报本身被第 4 条变异验证过会红 |
| 派发 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 14.7 位置

| 判据 | 第 98 轮 | 现在 |
| --- | --- | --- |
| E1 fact source | ✅ | ✅ |
| E2 消费者接线 | ✅ | ✅ |
| E3 `MemoryType` | ✅ | ✅ |
| **E4 四机制结清** | ⚠️ 半做 | ✅ **关闭**：`consolidate` 为 Declined + 算术（三条理由、四个变异）；`MemoryGraph` / `resolveContradiction` / `sinkhorn` / `Fact.derivedFrom` 早已结清 |
| E5 / E7 / E8 | ✅ | ✅ |
| E6 语义层测量 | ❌ | ❌（预测未变：500 题上 `deltaQuestions === 0`，非零即跨题泄漏） |

**7 关闭 / 1 全红。**

E4 一关，剩下的**只有 E6**，而它是八条里唯一需要派发的一条——也正好是 `S10`/`S9` 的解禁条件。这个结构值得说清楚：语义层的修复已经不再被任何**代码**工作阻塞，只被一次**测量**阻塞，而那次测量需要花钱。

一句话：**这一轮没有让产品多接一条机制，而是第一次把「我们为什么不接这条」写成了能算出数的东西——一条遗忘规则在一个只有一个瞬间的 store 里测到的流逝是零，而它写的那个字段，产品里没有一个模块读。**

## 15. 第 100 轮：语义层在哪个包——一次质疑，一个真错位，一个领域缺口

问题来自一次直接质疑：*「语义层的实现是放在 `cortex-memory` 包吗？它难道不属于 `cortex-core` 的部分吗？」*

这一轮没有写新机制。它做的是把这个问题量出来，然后按量出来的结果搬了一个文件。

### 15.1 核查：主体确实在 core，而文档把它藏起来了

| 层 | 内容 | 行数 | 占 core 非测试行数 |
| --- | --- | ---: | ---: |
| `cortex-core/src/knowledge/` | taxonomy · unit · frame · edge · assumption · revision · temporality · markers | 2,089 | 18.8% |
| `cortex-core/src/triage/` | proposer · rules · writer · card · claims · grounding · release · erasure · output-guard | 4,188 | 37.8% |
| **语义内核合计** | | **6,277** | **56.6%**（core 11,085 行） |

`cortex-memory` 从 `@agentix-e/cortex-core` 导入 **45 个符号**，语义内核的消费点是具体的：
`disclosure/session.ts` 用 `TriageWriter` / `CardQueue` / `OutputGuard` / `TriageProposer`，
`semantic-facts.ts` 用 `assemble` / `buildKnowledgeUnit` / `deriveAssumptions` / `deriveSupersedes` /
`locate` / `reviseLedger`。

所以 `DECISION-SEMANTIC-LAYER-ROUTE.md` 第 3 行的决定（the semantic kernel in `cortex-core` gets wired to the
shipping product）是**被执行的**。质疑之所以成立，是因为 `ARCHITECTURE.md` §2 的 layer map 只列了 core 的 8 个
目录，`knowledge/` 与 `triage/` 一个都没有——6,277 行、包内 56.6% 的代码在架构图上不存在。一张那样的图，读出来
的结论只能是「语义层是 memory 的事」。

这是文档缺陷，而且是最该先修的一类，因为它正是这次提问的成因。

### 15.2 真正的错位：`retention.ts` 96 行

| 模块 | 位置 | 纯度 | 依赖 | 判定 |
| --- | --- | --- | --- | --- |
| `retention.ts` | memory | 纯函数、零 I/O、零状态 | 只依赖 core 的 `MemoryType` / `MemoryValue` | **错位**：core 自述「contracts + pure algorithms」，这条够格 |
| `semantic-facts.ts` | memory | 纯构造 | core 内核 7 个符号 **+ memory 的 `SupersessionVerdict`** | **正确**：verdict 由模型判定，上移会把 LLM 带进零 I/O 的包 |
| `memory.ts #semanticAbsorb` | memory | 有状态、splice、计数 | — | **正确**：状态与 I/O 归装配层 |

### 15.3 签名就是证据，而缺口在领域模型里

旧签名：

```
leastRetained(entries: readonly { readonly memory: MemoryValue; readonly reads: number }[]): number
```

纯规则的每个入参都应该是领域能命名的值。`reads` 不是：`MemoryValue` 没有这个字段，store 把它存在自己的
`StoredUpdate` 上，调用方传进来。**一个需要领域类型表达不了的入参的规则，是领域描述不了的规则**——第二个参数
就是它显形的地方。

不是整洁癖：读数留在外面，排序就成了「条目 + 调用方声称的计数」的函数，而且没有任何东西阻止两个调用方对同一条
目声称不同的计数。字段让计数成为条目的属性，排序才成为条目单变量的函数。

修复顺序（顺序本身是被依赖决定的）：

1. `MemoryValue.reads: number` 必填，`createMemory` 默认 `0`；
2. `cortex-core/src/domain/retention.ts`：表 + rank + `leastRetained`，签名不再有第二个参数；
3. `memory.ts`：`StoredUpdate` 去掉 `reads`，驱逐改为
   `leastRetained(this.#semanticUpdates.map((stored) => stored.memory))`，读回改为 `stored.memory.reads += 1`；
4. 删除 `cortex-memory/src/retention.ts` 与其测试。**没有兼容 re-export**——一条规则两个 import 路径会让导出普查
   数两遍。

`reads` 不是 `MemoryValue.value`，这正是它必须独立成字段而不是折进已有字段的原因：`value` 的契约是 `[0, 1]`，
由准入闸用调用方给的 `valueFunction` 算出，而这些语义条目从不经过那个闸；使用计数无界、且是**观测**而非估计。一个
字段装两个标尺，正是 `math/fsrs.ts` 在时间域花一整段 docstring 修掉的缺陷。

### 15.4 必填字段的代价，数出来的

`tsc` 报 **17 个错误、13 个测试文件**，形状全部相同：手写的 `MemoryValue` 字面量列出了它在意的 12 个字段，现在
要列 13 个。其中 15 处是同一个 stub（`stability: 1, difficulty: 5,` 后补 `reads: 0,`）。

值得记下来而不是道歉：这 17 个错误就是本仓**绕过 `createMemory` 手搓 `MemoryValue`** 的位置数。**生产模块零改动**
——`memoryForUpdate`、`admitInto` 及其余构造点本来就都走 `createMemory` 或展开它的结果。`cortex-storage` 在加字段
前查过：`packages/cortex-storage/src` 里 `MemoryValue` 出现 **0** 次，没有 schema、没有迁移、不涉及任何持久化产物。

### 15.5 测试与变异

§12 的 5 条断言意图不变、形状重写（条目而非 `{ memory, reads }` 对），新增 3 条：

| # | 断言 | 用途 |
| ---: | --- | --- |
| 1 | `createMemory(...)` 的 `reads === 0` **且** `value === 0.5` | 独立性：计数没有被折进效用字段 |
| 2 | `@ts-expect-error` 下旧形状 `[{ memory, reads: 3 }]` 不可赋值 | 调用方计数无法在不触发编译错误的情况下回来 |
| 3 | `leastRetained([])` 与单元素都返回 `0` | 文档化契约，含实现拒绝添加的 `-1` 哨兵 |

| # | 变异 | 被谁杀 |
| ---: | --- | --- |
| 1 | `semantic: (m) => [m.lastAccessedAt, 0]` | semantic 用例死，episodic 对照**保持绿**——这才是「计数是因果输入」的证明 |
| 2 | `leastRetained` 返回 `0` | 所有非零期望 |
| 3 | 签名回到 `{ memory, reads }[]` | `TS2578 Unused '@ts-expect-error' directive` |
| 4 | `reads` 写进 `value` 而非独立字段 | 15.5 第 1 条独立性断言 |

### 15.6 读数

| 项 | 值 |
| --- | --- |
| TS 测试 | **6,240**（core 946（+11）、memory 1,419（−6，迁走的 `retention.test.ts`）、eval 3,423、ai 327、storage 125） |
| 覆盖率 | **168** 文件、16 豁免、**0 ratchet**；core 40 文件（+1）99.60 / 98.40 / 99.78 / 99.82，memory 27 文件（−1）99.86 / 99.67 / 100 / 100；`domain/retention.ts` **100 / 100 / 100 / 100** |
| 变异 | **4 / 4 杀**：运行时 2 条、类型级 1 条、独立性 1 条 |
| 导出普查 | **1,182 / 718 / 464，三个数都不动**——文件换了包、`leastRetained` 仍恰好 1 个调用方（`memory.ts`，现经 barrel） |
| bundle | PASS（`./sqlite` +20 B 为本轮前既有差异，容差内） |
| `manual:check` | 2 页 / 31 例编译通过 / 34 个选项全被示例覆盖 |
| 派发 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 15.7 位置

| 判据 | 第 99 轮 | 现在 |
| --- | --- | --- |
| E1 / E2 / E3 / E4 / E5 / E7 / E8 | ✅ | ✅ |
| **E6 语义层测量** | ❌ | ❌（预测未变：500 题上 `deltaQuestions === 0`，非零即跨题泄漏） |

**7 关闭 / 1 全红，与上一轮相同。** 本轮是纯位移，不改行为——它**不**是 E6 的替代，也不消耗 E6。

### 15.8 这轮不主张什么

- **不主张准确率。** `semanticCarry` 仍默认关，E6 仍 `unrun`；不改行为的重构预测 `deltaQuestions === 0`，非零即
  位移跨题泄漏。
- **不主张 `cortex-memory` 其余部分都已放对。** 本轮只裁决了一个含纯规则的文件。`question-shape.ts`、
  `confidence.ts`、`tally.ts` 未逐一核查，而 layer map 的过时本身（15.1）就是「至少还有一处」的理由。
- **不主张 layer map 现在完备。** 它列的是目录，不是文件；列出的目录里新增文件它仍然看不见。更深的修法——
  生成式架构图、像 `docs-crosscheck` 校验 marker 那样校验它——没有做，记在这里是「假装漂移不会复发」的替代。

一句话：**这一轮把一个纯规则搬回了领域，代价是给 `MemoryValue` 加一个必填字段——而 17 个编译错误证明的不是字段太贵，而是本仓有 17 处手搓领域值的地方。**

## 16. 第 101 轮：evaluate 的对象是产品——三条臂，其中一条从未有过读数

### 16.1 触发：一次质疑，以及上一轮的三处事实错误

质疑是这句话：*「cortex-eval 难道 evaluate 不是产品吗？参考流水线不也应该是基于产品和使用场景的吗？」*

核查的结果是**质疑方向正确，而上一轮给出的图景错了三处**：

| 上一轮的说法 | 事实 | 证据 |
| --- | --- | --- |
| `cortex-memory` 只是装配层，检索不在产品里 | **错。** `retrieval/search-index.ts` **560 行**：postings over `contentTerms`、可选向量通道、**RRF 融合**、可选 rerank。`CortexMemoryOptions.index` 开启 | `search-index.ts:1`、`memory.ts:2870-2905`、`ARCHITECTURE.md` 第 266 行 |
| 两条实验线平权，各有一个 bench | **错。** `benchmark.yml` 跑参考流水线读 **43.40%**，验收矩阵明文写「its numbers are not on this page and **must not be substituted**」 | `ACCEPTANCE-MATRIX.md` 表格下第二段 |
| 参考流水线 83.55% 是产品对照 | **错（陈旧数）。** 那是 55 commits 前的读数，已被标 **STALE**；`40088479628` 在同一次调用里测出两系统 **80.80% / 43.40%**，证明两者不可比 | `AUDIT-CODE-VS-DOCS.md:27`、`MEASURE-BASELINE-DRIFT.md` §8 |

### 16.2 三条臂：同一条 500 题，唯一的变量是谁排名

| 行 | `relevanceSignal` | 谁排名 | 读数 |
| --- | --- | --- | --- |
| `S11` | `none`（arm **默认值**） | 无人：预算按到达顺序花 | `unrun`（本轮新增） |
| `S9` | `self-index` | **产品**（`SearchIndex` 560 行） | `unrun`；200×2 screening 读 **−1.50 题，McNemar p = 1.0** |
| `S1` | `retrieval-anchored` | 仪器（`cortex-eval` 的 relevance index） | **91.25%**，gate |

三条臂同数据集、同 reader、同 judge、同 prompt、同重复次数，**唯一的差别是谁建排名**。这使它们成为本仓唯一一组「可以相减」的读数。

`none` 是 `bench-memory-arm.ts` 的 `DEFAULT_RELEVANCE_SIGNAL`：`CortexMemory` 在既没有 `relevanceFor` 也没有 `index` 时的行为。它同时也是**用户装完包什么都不配**时拿到的形态。这一条臂此前没有行——**零成本即可到达的交付形态，是矩阵唯一描述不了的那一个**。

### 16.3 `S11` 的阈值不是选的，是从 `S9` 的容差继承的

阈值 **0.88 = `S1` 的 0.91 − `S9` 的容差 0.03**（`S9` 是 −15 题 / 500 题 = 3.0 点）。

推理是：本项目**已经**为「换掉仪器给出的排名」定过最大可接受损失，就是 `S9` 那 3.0 点。`S11` 问的是更难的问题——**干脆没有排名**——所以它沿用那个容差，而不是再发明一个。

- 若 `S11` ≥ 88%：裸装在 3.0 点内，则「要不要排名」对 500 题不是可交付性问题，这个结论比这一行更有价值，且要和 `C1`、`S10` 一起读（它变成一句关于预算的话）；
- 若 `S11` < 88%：裸装不是可交付配置，Quick Start 的最小示例必须传 `index`，这也意味着调用方在第一个答案之前就要拥有一个 embedder。

依赖关系写成**可执行断言**（`S11.threshold ≈ S1.threshold − |S9.threshold| / 500`），所以三行不能各自漂移：只改 `S1` 而不改 `S11` 会让测试变红。

机制读数指向后者：到达顺序下 gold turn 进入模型真正读到的证据的比例是 **11.6%**（14/121，run `38142407062`，`PREREGISTRATION` §13.17.1），天花板 92.1%。所以这一行预期会 miss，而 miss 的含义是「确认排名是交付必需品」，不是「产品不行」——这就是它写成 `aim` 而不是 `gate` 的原因：`gate` 会让一个诚实答案变成红色构建。

### 16.4 文档：粗体裁决与 30 行之后的修复

`AUDIT-SEMANTIC-REACH.md` §9.1 的表格里，retrieval 与 rerank 两行的裁决是粗体 **not the product**；§9.3 在 30 行之后记录了修复（`retrieval/search-index.ts`）。审计**没有过期**——§9 的标题就是过去时（"which of them the product **had**"）。

真正的问题是：**粗体裁决没有任何指向修复的箭头**。上一轮就是停在那张表上的。

修法是加时点而不是改历史：

- 两行裁决改为 `**not the product — until §9.3.**`；
- 表格后新增一段，说明「四条裁决里有两条是历史读数」，并指出验收矩阵的 `S9` / `S11` 才是当前状态所在；
- §8「不主张」清单新增一条：不主张 §9.1 的裁决是当前状态。

同一类缺陷（一份文档里的旧结论没有任何东西把它和后来的修复连起来）在过去几轮出现过两次：`README` 声称 `consolidate` 做 episodic→semantic promotion，以及 layer map 漏掉 6,277 行语义内核。这一条是第三次，也是唯一一次**新旧结论在同一份文件里相隔 30 行**的。

### 16.5 变异

| # | 变异 | 被谁杀 |
| ---: | --- | --- |
| 1 | `threshold: 0.88 → 0.91` | 阈值推导断言（`S1 − S9/500`） |
| 2 | `kind: 'aim' → 'gate'` | `kind` 断言与 `blocking === false` 断言 |
| 3 | `dataset` 去掉 `relevanceSignal: none` | 「点名哪条臂」断言 |
| 4 | `source.path` 换成 `frontier.json` | `source` 全等断言 |
| 5 | `onMiss` 去掉 `Quick Start` | 后果断言 |

**5 / 5 杀**，全部为运行时断言，无类型级变异（本轮不含签名改动）。

第 4 条用全等而非逐字段，是刻意的：第一次 dispatch 落地时**必须**在这一行加 `attest`（路径不是身份——`S1` 曾连续三轮读一个描述了已退役配置的活文件），而那一次编辑会让这条测试变红，也就无法被悄悄跳过。

### 16.6 读数

| 项 | 值 |
| --- | --- |
| TS 测试 | **6,245**（core 946 / memory 1,419 / **eval 3,428（+5）** / ai 327 / storage 125） |
| 覆盖率 | **168** 文件、16 豁免、**0 ratchet**；`cortex-eval` 81 文件 99.57 / 98.64 / 99.83 / 99.76 |
| 变异 | **5 / 5 杀** |
| 导出普查 | **1,182 / 718 / 464** 三个数不动（新增的是一条数据行，不是符号） |
| 验收门禁 | `acceptance:check` exit 0；`S11` 报 `unrun` 并给出原因（文件无值），不是 pass |
| `docs:crosscheck` | 64 / 72 marker 校验通过，8 skipped（本 checkout 无对应证据） |
| tools 测试 | 2,712 passed / 19 skipped |
| 派发 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 16.7 位置

| 判据 | 第 100 轮 | 现在 |
| --- | --- | --- |
| E1 / E2 / E3 / E4 / E5 / E7 / E8 | ✅ | ✅ |
| **E6 语义层测量** | ❌ | ❌（预测未变：500 题上 `deltaQuestions === 0`，非零即跨题泄漏） |

**7 关闭 / 1 全红，与上一轮相同。** 本轮新增的 `S11` 不是 E6：E6 问的是「语义层开不开」，`S11` 问的是「排名开不开」，两者不同轴。本轮也不消耗 `S9`——它依然 `unrun`。

### 16.8 这轮不主张什么

- **不主张准确率。** 没有派发，91.25% 未动，`semanticCarry` 仍默认关。
- **不主张「三臂相减」已经可读。** 三条臂里只有 `S1` 有注册读数；`S9` 只有 screening，`S11` 只有行。这一组表格现在描述的是**实验设计**，不是结果。
- **不主张参考流水线该被移除。** 它仍是 8 个 ablation 的载体，因为那些消融需要「同 instant 双系统」，而 `cortex-eval` 能自建两侧。它的问题不是存在，而是它的读数（43.40%）与产品臂不可比——而这一点矩阵已经写明了。
- **不主张 `cortex-memory` 其余模块都已放对。** 本轮只裁决了「产品是否有检索」这一个事实。

一句话：**这一轮没有让产品多答对一个题，而是第一次把「用户装完包什么都不配会拿到什么」变成一条有阈值、有后果、且阈值来自另一条已注册行的判据——而它此前连一行都没有。**

## 17. 第 102 轮：E6 没有臂——六轮「unrun」描述的都是错的障碍

E6 是语义层八条退出判据的最后一条：*paired readout，`deltaQuestions ≥ −5`*。连续六轮的收尾都写着「E6 仍 `unrun`」，每一次都把它读成预算或排期的注记，下一步自然是「派发」。**这个下一步不存在：那套处理根本没有开关。**

### 17.1 缺的是三个不同的东西

| # | 对象 | 事实 |
| --- | --- | --- |
| 1 | 臂的选项面 | `CortexMemoryArmOptions` 没有 `semanticCarry` 字段，`cortextMemoryArmOptions` 不读这个环境变量，`bench/run-ablation.ts` 往构造函数里条件转发**二十五**个产品选项——每一个都配着一段「缺席即出厂配置」的说明。第二十六个不在里面 |
| 2 | artifact 的 census | `CortexMemory.semanticCarryCensus()` 存在且被测试，而 `cortex-eval` 里没有任何 reader 点它的名；`traceCensus` 读三个 accessor，它是第四个、零调用方 |
| 3 | 判据本身 | `S9`/`S10`/`S11` 覆盖了排名的三条臂；语义层**一行都没有** |

三者是一条链，而第三条正是前两条一直不可见的原因：**一条不存在于矩阵中的判据，无法以任何读者会注意到的方式「unrun」**——它唯一的记录是一句话。

### 17.2 为什么 `0` 是这个总体的必然，而这是设计事实

一条 update 是关于「授权它的那条记录」的。`updateAppliesTo` 是对该记录的子串测试（`semantic-facts.ts:383`），其 docblock 写明为什么不能用更软的判据：相似度会让一条关于语料 A 的 update 抵达一个关于语料 B 的问题，而那在 benchmark 上就是跨题泄漏。

注册总体里**每题自带语料**，所以没有任何一题的窗口会携带另一题的记录，reach 按构造为零——`DECISION-SEMANTIC-LAYER-ROUTE.md` §5 已写明。于是 E6 在这个总体上必然读 `0`，而 `0 ≥ −5` 是 **pass**。「处理没有运行」被记成 pass，比没有这一行更糟。

### 17.3 修复的三部分

1. **`CORTEX_MEMORY_SEMANTIC_CARRY`**：`readToggle` 语义（`'1'` 开，缺席即控制臂），启用与停用两个投影都写，构造函数里条件转发，配置日志行回显，`featureConfig` 记录。条件 spread 是本仓的既定形状，理由与其余选项相同：缺席是每一份归档 artifact 的产出状态，若写一个 present-but-false 的键，「跑了控制臂」和「处理被配置成关」就变成 artifact 分不开的两件事。
2. **报告里的 `semanticCarry`**：跨每个 worker 实例折叠（`censusSourcesOf`，§13.244），构建没有该 accessor 时字段缺席。折叠把 store 自己的算术当作检查：`absorbed − dropped` 等于 `stored` 三项之和，因为 `stored` 数的是**手上的条目**。违反它的记录被丢弃而非发布——与 `supersessionAcross` 对 `attempted === replaced + refused` 的规则相同。
3. **`S12` / `S13`**，其中 `S12.requires = ['S13']`，并为「存在但回答不了本行问题」的数字新增第五种状态 **`void`**。

### 17.4 为什么需要新状态，而不是更严的阈值

没有任何阈值能分开「层没获益」与「层没运行」：两者都读 `0`。任何单数字比较也不能。分开它们的是第二个数字（reach），而让一行的裁决依赖另一行，唯一可执行的做法是把它声明出来。于是有 `Criterion.requires`，`applyRequirements` 是对整个矩阵的第二遍（它需要全部裁决，而 `verdictOf` 刻意不依赖注册表），`void` 是它产出的状态。`void` 与 `unrun`/`stale` 一起计入发布闸门，但分开标注——因为修法不同：一次派发、一次重挂 artifact、一个总体。

### 17.5 变异

**17 / 17 杀**：解析恒 false、`defaultOn: true`、停用臂投影 true、`!== false` 的比较、census 不挂载、`served`/`withheld`/`stored` 各自不累加、`absorbed − dropped` 不变量、三名检查、构造函数 spread 删除、日志子句删除、`featureConfig` 丢字段、**`applyRequirements` 的不动点退化为单遍**、未知 id 检查删除、`void` 的 `blocking` 翻转、`requires` 读成空表。

其中后三条是**文本断言**，也是本轮最弱的一环：`bench/**` 作为入口被覆盖率排除，那行把处理从解析后的选项送进构造函数的代码没有任何测试能执行到。本臂其余每个处理都有同样的缺口和同样的补偿；这里不同的是 artifact 现在把 reach 记在开关旁边，所以将来删掉 spread 会表现为 `semanticCarry: true` 配 `absorbed: 0`——可见，但只对会去看的读者可见。

### 17.6 读数

| 项 | 值 |
| --- | --- |
| TS 测试 | **6,271**（core 946 / memory 1,419 / **eval 3,454（+26）** / ai 327 / storage 125） |
| 覆盖率 | **168** 文件、16 豁免、**0 ratchet**；cortex-eval 81 文件 99.58 / 98.65 / 99.83 / 99.76 |
| 变异 | **17 / 17 杀** |
| 导出普查 | 1,182 / 718 / 464 不动（`SemanticCarryCensus` 被本地引用，未成孤儿） |
| 验收门禁 | exit 0；`S12` = **`void`**（`S13` 未 pass），`S13` = `unrun`——不再可能 vacuum pass |
| `docs:crosscheck` | 64 / 74 marker 通过，10 skipped |
| 派发 | **0 元** |
| 产品表 | 未动 **91.25%** |

### 17.7 位置

| 判据 | 第 101 轮 | 现在 |
| --- | --- | --- |
| E1 / E2 / E3 / E4 / E5 / E7 / E8 | ✅ | ✅ |
| **E6 语义层测量** | ❌（无臂、无行） | ❌（**有臂、有行、有 reach；缺一个能承载的总体**） |

**7 关闭 / 1 全红，与上一轮相同**——但 E6 的性质变了：它从「无从下手」变成「一条被 `void` 挡住的判据」。

### 17.8 这轮不主张什么

- **不主张有读数。** 没有派发：本环境没有 reader 凭据，也够不到数据集主机。`S12` 是 `void`、`S13` 是 `unrun`，矩阵就是这么打印的。
- **不主张注册总体能承载该机制。** 按 17.2 它不能；`S13` 的 `onMiss` 写明修法是**一个语料两个窗口**，而不是再派发一次这一个。
- **不主张派发一定有益。** 在这个总体上它只会产出 `0 / 0`，即 `void`——对一个无法回答该问题的总体的正确报告。
- **不主张准确率。** `semanticCarry` 仍默认关；`CORTEX_MEMORY_SEMANTIC_CARRY` 未设是每一份归档 artifact 的产出状态，现在仍然如此。

一句话：**这一轮没有给语义层一个数，而是给了它拥有一个数的能力，并让那条判据在拿到之前拒绝通过。**

## 18. 第 103 轮：E6 的障碍是一个总体，而建它需要四个对象

第 102 轮的收尾句是「这一轮没有给语义层一个数，而是给了它拥有一个数的能力」。连着八轮说这句话，就该问那个能力还缺什么——**缺的不是 reader 凭据，是一个总体**。`S13` 的 `onMiss` 早就写着修法：*同一语料两个窗口*。而在这一轮之前，仓库里没有任何东西能造出这样一个总体。

### 18.1 缺的又是三个对象

| # | 对象 | 事实 | 表现 |
| --- | --- | --- | --- |
| 1 | 总体 | `loadLongMemEval` 一题一实例，每实例自带 haystack；没有任何选择器能把一个语料问两次 | 机制没有可作用的总体 |
| 2 | 配对 | `CORTEX_MEMORY_SEMANTIC_CARRY` 只说**产品侧**做什么，没有东西说基线是什么。`S9` 用两次派发相比，付掉了 `PREREGISTRATION` §2.2 存在的那个漂移 | delta 会是两次运行之差，而不是一次运行两侧之差 |
| 3 | store | 池给每个 worker 自己的 `CortexMemory`，而领取循环一次只发一个**索引**。一个语料的两个窗口可能被两个 worker 答，第二个读的是从未吸收过第一个的 store | 处理会运行、会 reach 到 0——正是 `S13` 拒绝的那种读数 |

三者仍是一条链，第三条同样最隐形：语料被切开时产出 `matched: 0`，而 `matched: 0` 与「机制什么都没带上」是同一个数。

### 18.2 乘法，以及它在选择器里的位置

`two-window.ts` 把已加载的 dataset 按语料问 `windows` 次：id 加 `#wN`，同一语料的题相邻，`windows = 1` 返回**入参本身**。

- **恒等是同一个对象，不是副本。** 每一份归档 artifact 都是「一题一窗口」产出的，内容相同的副本仍然是从 dataset 里穿过的第二条代码路径。`two-window.test.ts` 里的 `toBe` 就是这句话的可执行形式。
- **语料优先的顺序是契约，不是偏好。** `Question.corpus` 把它写死：相邻、同一实例、升序。§18.3 是它的执行者。
- **它排在选择器最后。** `LIMIT` 问多少个语料、`CORTEX_CAPABILITY` 问哪些，两者都必须看到**语料**而不是窗口；否则 `LIMIT=78, capability=KU, windows=2` 会变成「156 题，其中一半是第二窗口」，样本量取决于一个日志里看不见的乘法。
- **它与 restore 计划互斥。** 计划按**录制的题号**匹配，而乘法重命名了每一个；同时给会让 `restrictDatasetToPlan` 一个都选不中——而且是在数据集下载之后、报的还是计划的问题。所以它在读出后立刻拒绝。

### 18.3 一个语料，一个实例——而领取仍然是动态的

池的领取是 `next++`：索引被原子地取走，取走它的 worker 回答它。那对独立总体是对的，对一个语料是错的；而修法**不是**预切片数组——计数器上方的注释写着原因：切片会让慢 worker 的那一份成为整趟的关键路径。

`claimRun` 改成领取**整段**：从被取走的索引起，把后面 `corpus` 相同的索引一并取走，worker 在自己的实例上按序回答。仍然是按需领取，所以负载均衡不变；只是原子，所以语料切不开。没有 `corpus` 的题目只领一个索引，也就是每一份归档 artifact 产出的那一趟。

### 18.4 对照组是同一个系统，且这条配对拒绝变成两个对照

`arm-pairing.ts` 读 `CORTEX_MEMORY_AB`：`reference` 是注册配对（参考流水线对认知系统）且是默认值；`carry` 用**一个**构造函数造两侧，中间只有一个 flag。于是 `run-ablation.ts` 只有一个 `buildCortex(carry)` 和两个调用点，而不是两份会各自演化、直到其中一份被改动的字面量。

真正值得写下来的是那条拒绝：`ab=carry` 而产品侧 `semanticCarry` 没开，就是两个对照、delta 为 `0`、census 为 `0`——一个从未施加处理的比较被发布成零结果。它**先于第一次调用**被拒绝，所以发现它的代价是零。

### 18.5 派发

`semantic-carry.yml` + `tools/dispatch-semantic-carry.py`，真实 runner，预设写在明面上，只有一处声明过的偏离：`review_pass: supersede`。吸收只发生在那一遍、那一条路由上；用注册的 `bare` 派发 carry，就是派发一个没有东西可带的机制。这一遍在**两侧都开**，所以配对仍然只隔离 carry；它不隔离这一遍，而 artifact 上的 `memoryArmConfig.reviewPass` 就是读者核查它的位置。

### 18.6 十三处变异，与那个「先活下来」的

每处变异施加到源码、跑它自己的测试套件、再还原。套件仍然通过就是**存活**，意味着套件测的不是被删掉的那一行。

| # | 变异 | 归属套件 | 结果 |
| ---: | --- | --- | --- |
| 1 | `claimRun` 在有语料时也一次只领一个索引 | `corpus-run-claim.test.ts` | 杀 |
| 2 | 一个语料的窗口降序领取 | `corpus-run-claim.test.ts` | 杀 |
| 3 | `withWindows` 在一窗口时返回副本而非入参 | `two-window.test.ts` | 杀 |
| 4 | 窗口标记改成前缀（`#w1q` 而非 `q#w1`） | `two-window.test.ts` | 杀 |
| 5 | 乘法后的题目不带 `corpus` | `two-window.test.ts` | 杀 |
| 6 | `readWindowCount` 接受 0 | `two-window.test.ts` | 杀 |
| 7 | 未设 `CORTEX_WINDOWS` 时按 2 | `two-window.test.ts` | 杀 |
| 8 | 未设 `CORTEX_MEMORY_AB` 时按 `carry` | `arm-pairing.test.ts` | 杀 |
| 9 | population 进报告时被丢掉 | `report-population.test.ts` | 杀 |
| 10 | Markdown 里的 population 行被丢掉 | `report-population.test.ts` | 杀 |
| 11 | carry 侧改用 arm 选项而非参数造 | `semantic-carry-arm.test.ts` | 杀 |
| 12 | 两种配对的控制侧都用参考流水线 | `semantic-carry-arm.test.ts` | 杀 |
| 13 | `ab=carry` 而处理侧没开时不拒绝 | `semantic-carry-arm.test.ts` | 杀 |

第 1 条要写下来，因为它**第一次是存活的**，而它存活的原因是测试本身错得像是成功：`runBenchmark` 有九个位置参数，`corpus-run-claim.test.ts` 把 worker 池传进了第八个——那是 `budgetMs`。TypeScript 不报错，套件于是跑了一趟**穿着并发参数外衣的串行 pass**：只有一个 worker、一次只有一个 `claimRun`，于是被改回 `claim()` 的 `claimRun` 依然全部答对，变异存活。修法是两个具名 helper（`runPooled` / `runSerial`）加一行注释——现在套件在「这趟不是并发的」时会失败，而这是让那条变异读起来像变异的唯一办法。

这条教训不止于本文件：**存活的变异首先是关于套件的问题，其次才是关于源码的问题**；本轮的答案是套件一直在测另一件仪器的名字。

目标文本找不到的变异报 `SETUP-FAIL` 并**计入存活**。这是同一条规则：没被施加过的变异，与施加了却没杀掉任何东西的变异无法区分；把「找不到那一行」当通过的脚手架，会在一次重命名之后交出一块干净的板子。

### 18.7 读数

Run [`43590434060`](https://github.com/AgentiX-E/cortex/actions/runs/43590434060)，artifact `14115493476`，`completed success`，约两小时。预设：`capability=KU`、`ablation_runs=2`、`workers=4`、`thinking=disabled`、`CORTEX_MEMORY_AB=carry`、`CORTEX_MEMORY_SEMANTIC_CARRY=1`、`CORTEX_WINDOWS=2`、`review_pass=supersede`。

| 对象 | 读数 |
| --- | --- |
| 总体 | `72 corpora x 2 windows` = 144 题，id 带 `#w` |
| carry census | `absorbed 3 / dropped 0 / matched 8 / served 8 / withheld 8`；`stored {episodic 0, procedural 0, semantic 3}` |
| 不变量 | `absorbed − dropped = 3 = Σ stored`——`semanticCarryAcross` 折叠四个 worker 后 store 的算术仍成立 |
| 正确数 | 控制 `245/288 = 85.07%`，处理 `244/288 = 84.72%`，两次 repetition 合起来差**一题** |
| delta（第二窗口） | **`0.0`**，`n = 72`（`baselineOnly 1`、`featureOnly 1`） |
| delta（第一窗口） | `-0.5`，`n = 72`——吸收发生在这一窗口，机制动不了它 |
| delta（全部窗口） | `-0.5`，`n = 144` |
| McNemar（第二窗口、首个 repetition） | `b = 3`、`c = 1`、`p = 0.6250` |
| 四个不一致 | 得 `c4ea545c#w2`；失 `10e09553#w2`、`50635ada#w2`、`f685340e#w2` |
| supersession | `attempted 285 / replaced 13 / refused 272`——`no-change 204`、`restates 63`、`not-later 4`、`date-not-on-line 1`，`unreadable`/`no-quote`/`agrees`/`not-in-evidence` 全 `0` |

矩阵在这一次之后：

```
S12  —    >= -5   unrun   semantic layer: carrying an authorised update into a later window
S13  8    >= 1    pass    semantic layer: whether the treatment reached any window at all
```

**`S13` 第一次通过，且是在 `8` 上通过、不是 `0`。** 八个题的答案取自一个仍携带三份被吸收 update 之一所授权记录的窗口。这是本项目第一次有「`semanticCarry` 抵达过任何东西」的证据；此前每一次派发都读 `0`，而 `0` 与「机制什么都不做」是同一个数——这就是那条判据是**计数**而不是 delta 的原因。

**`S12` 是 `unrun`，这是设计结果而不是失败。** 这次是筛查配对（72 语料 × 2 repetition），`semantic_carry_analysis.py --tier screening` 把 delta 写在 `screening.deltaQuestions` 下、让 `paired.deltaQuestions` **缺席**，于是读那个键的行没有值。在这一总体上的 `void → pass` 会是对「500 语料 × 4 repetition」的断言，而实测是 72 × 2。筛查对确实产出了第二窗口的 `0.0`，它被写进 `evidence/longmemeval/semantic-carry.json` 的 `screening` 键——一个矩阵不读的键。

**一处不是读数的读数，写下来因为我差点当读数发布。** 144 个题**每一个**都带 `supersessionConsultations: 4`，`0ddfec37#w2` 还带四次 `supersessionReplacements` 且零拒绝；把它们读成 carry 抵达很方便。它们不是：那些咨询是**supersession 这一遍**在逐条读窗口里的候选事实，在整个总体上均匀（144/144），控制侧同样有。carry 在这份 artifact 里唯一的证据是 census——`matched`、`served`、`withheld`——因为 census 是唯一由语义 store 而不是由它前面那一遍产生的字段。**每一行都是同一个数的逐题列，不可能是「抵达了其中八行」的证据。**

### 18.8 位置

| 项 | 值 |
| --- | --- |
| TS 测试 | **6,299**（core 946 / memory 1,419 / **eval 3,482（+28）** / ai 327 / storage 125） |
| 覆盖率 | **170** 文件、16 豁免、**0 ratchet**；cortex-eval 83 文件 99.58 / 98.64 / 99.83 / 99.77 |
| 变异 | **13 / 13 杀** |
| 导出普查 | 1,189 / 725 / 464（+7 / +7 / 0） |
| 验收门禁 | exit 0；`S13` = **8 `pass`**、`S12` = `unrun`（`paired` 键缺席） |
| `docs:crosscheck` | 65 / 74 marker 通过，9 skipped |
| 派发 | 一次真实 run，约 2 小时 |
| 产品表 | 未动 **91.25%** |

| 判据 | 第 102 轮 | 现在 |
| --- | --- | --- |
| E1 / E2 / E3 / E4 / E5 / E7 / E8 | ✅ | ✅ |
| **E6 语义层测量** | ❌（有臂、有行、有 reach；缺总体） | ❌（**reach 已非零 8；注册总体待派发**） |

**7 关闭 / 1 全红，与上一轮相同**——但 E6 的阻塞从「缺一个总体」变成「缺一次能装下 500×4×2×2 的派发」。

### 18.9 这轮不主张什么

- **不主张 carry 已有价值。** 第二窗口 delta 是 `0.0`，McNemar `3 : 1`（`p = 0.625`），两次 repetition 里净失一题。机制抵达了；抵达是否有用没有答案，`S12` 在注册总体派发前保持 `unrun`。
- **不主张 `S13` 的 `8` 稳定。** 一次 run、四个 worker、两次 repetition，而 census 是跨实例求和：同样形状的第二次派发可能读出另一个数，且两个都不算错。这次 run 确立的是**这个计数器在结构上不是零**。
- **不主张注册总体上的任何数。** 500 语料 × 4 repetition 是 4,000 题 × 2 侧 × 4 特性，不是一个 job 装得下的。`8` 是 72 语料上的数，不能按算术放大：第二窗口才是 carry 能落地的地方，而 500 里有多少个带 carry，正是注册派发要测的东西。
- **不主张这一遍是免费的。** `review_pass=supersede` 在两侧都开，所以配对只隔离 carry、不隔离这一遍；285 次尝试里 272 次被拒，其中非 `no-change`/`restates` 的五次（`not-later 4`、`date-not-on-line 1`）是这一遍按未来某一轮可能想审计的理由拒绝的。
- **不改默认。** `CORTEX_MEMORY_SEMANTIC_CARRY` 在这些 workflow 之外仍未设置，每一份归档 artifact 依旧是在未设状态下产出的。

一句话：**语义层抵达了八个窗口、一个都没推动，而测这件事的判据现在等的是一个总体，而不是一个机制。**
