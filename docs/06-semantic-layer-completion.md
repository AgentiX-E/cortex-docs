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
| **E1** | **fact source 存在且 additive**：产品能构造 `KnowledgeFact`，来源是**已计算的** supersession 状态（不新增模型调用、不替换原文） | 存在非测试构造点，且其输入来自 `supersede.ts`/`memory.ts:1603` 的计算结果；一条行为级测试证明同语料下 prompt 字节**因该事实而变** | ❌ 唯一构造点在 arm |
| **E2** | **消费者接线**：`assemble` → `reviseLedger` → `resolveContradiction` 在产品路径被调用 | `semantic-reach.test.ts` 的命中清单**非空**且打印出符号；reach table 对应行改 **P** | ❌ 命中 = 0 |
| **E3** | **可表示**：`MemoryType` 的 `'semantic'` 有写有读（读 = 影响 selection/渲染/调度之一）**或**两个不可达值被删除且文档同步撤回 | 一条「写入 semantic → 读回并改变行为」的测试；或删除后的类型快照 | ❌ 0 次写入、0 次读取 |
| **E4** | **charter 四机制结清**：`consolidate` / `resolveContradiction` 从 0 调用变为**有产品调用者**，或由 ADR 显式 **Declined** 并给出理由与代价 | `grep` 出调用点（非测试）；或 ADR 文件存在且被 `ARCHITECTURE.md` 引用 | ❌ 两者皆 0，无 ADR |
| **E5** | **三表同步**：哨兵测试、`AUDIT-SEMANTIC-REACH §3`、`ARCHITECTURE.md` 状态表**同一提交**内一致 | `pnpm check` 绿 + 三处 diff 在同一 commit | ❌ 未开始 |
| **E6** | **语义层自身有测量**：至少一次 paired 读数或离线 trace 指标（FEB-30 四项），且**不伤准确率**（判据 `deltaQuestions ≥ −5`，与 S10 同口径） | artifact 有 run id 与配置行；McNemar 双侧 | ❌ 无 |
| **E7** | **对外口径一致**：README、白皮书 §4、`ARCHITECTURE.md` 中语义层行与代码一致 | `pnpm docs:crosscheck` + 人工对表 | ⚠️ README 已改，白皮书 #3 已改，`ARCHITECTURE.md` 字段数已改 |
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
| E1 fact source | ❌ 唯一非测试 `KnowledgeFact` 构造点仍在 arm |
| E2 消费者接线 | ❌ 命中 0 |
| E3 `MemoryType` 可表示 | ❌ 0 写 0 读 |
| E4 四机制结清 | ❌ 0 调用、无 ADR |
| E5 三表同步 | ❌ 未开始 |
| E6 语义层测量 | ❌ 无 |
| E7 对外口径 | ⚠️ README 已加 evidence assembly 段；白皮书 §4 的 10 行仍未全对齐 |
| **E8 证据组装正确** | ✅ **关闭** |

**8 条里 1 条关闭、1 条部分、6 条全红。** 下一项是 **E1（fact source）**——它是 E2/E3/E4 的前置：没有事实就没有可装配的语义单元；有了事实，`assemble → reviseLedger → resolveContradiction` 才有输入，`MemoryType` 的 `'semantic'` 才有写入方。

`S10` / `S9` 的 500×4 对照对**仍在冻结区**。

### 10.7 一句必须写清的话

E8 让 artifact 说得清「走了哪条路、窗口里是什么角色」，但**它一个字也没让答案更准**。它的价值在下一轮：当 E1–E7 的接线真正改变 prompt 字节时，能分辨「字节变了因为语义层」与「字节变了因为别的原因」的，就是这两个字段。**仪器完备不等于测量完成**。
