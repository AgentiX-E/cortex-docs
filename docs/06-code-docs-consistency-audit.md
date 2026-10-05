# Cortex 代码与文档一致性审计

> 审计日期：2026-09-20
> 审计对象：`AgentiX-E/cortex` @ `master` `31a3371`
> 审计方法：源码通读 + 本地复现全部质量门禁，**不以文档自述为依据**
> 对照文档：本仓库 `01`–`05` 全部文档，以及 cortex 仓库 `README.md` / `ARCHITECTURE.md` / `SOTA-BASELINE.md`

本文档的目的是把「项目声称做了什么」与「代码实际做了什么」逐条对齐，并把偏差写成可
复核的清单。结论先行，证据随后。

---

## 0. 结论先行

工程纪律没有任何问题——**可复核的质量声明全部成立**。问题出在另一处：
**四份根文档中，有三份描述的不是 `master` 上运行的那个系统。**

| 声明来源 | 声明内容 | 复现结果 | 判定 |
|---|---|---|---|
| `CONTRIBUTING.md` | 四个维度覆盖率均 ≥95% | ✅ core 98.29 / 97.32 / 100 / 98.29 | **属实** |
| `CONTRIBUTING.md` | 不使用 mock，真实 SQLite / 真实 HTTP | ✅ 已核对测试源码 | **属实** |
| `CONTRIBUTING.md` | `pnpm check` 全绿 | ✅ lint + typecheck + test + format 全部通过 | **属实** |
| `ARCHITECTURE.md` | 分层、Float64、可插拔后端 | ✅ 与源码一致 | **属实** |
| `README.md` | 六大认知能力即产品本体 | ⚠️ 已实现且测试充分，但**评测路径完全够不到** | **部分误导** |
| `ARCHITECTURE.md` | 检索即巩固 = Hebbian + FSRS + **TD(λ)** | ❌ 全仓库**不存在 TD(λ)** | **不实** |
| `ARCHITECTURE.md` | 跨层蒸馏基于最优传输 | ❌ `sinkhorn` 已导出但**从未被调用** | **不实** |
| `SOTA-BASELINE.md` | 83.55% 测于 `master` | ❌ 实测于 `a52628f`，**落后 55 个提交** | **过期** |

在 `31a3371` 本地复现：

```
packages/cortex-core  Test Files  9 passed  Tests  87 passed  98.29 | 97.32 | 100 | 98.29
packages/cortex-node  Test Files  1 passed  Tests  16 passed   100  | 98.61 | 100 |  100
packages/cortex-llm   Test Files  2 passed  Tests  43 passed   100  | 97.26 | 100 |  100
packages/cortex-eval  Test Files 20 passed  Tests 836 passed  99.84 | 98.68 | 100 | 99.84
                                         合计 982 tests，0 失败
```

---

## 1. 核心发现：认知层不在评测路径上

`cortex-eval` 在 `package.json` 中依赖 `cortex-core`，但它从 core 实际取用的**非类型符号只有
统计工具与一个向量索引**：

```
binomialCdf · BruteForceVectorIndex · mean · stddev · variance · welchTTest · wilsonScoreInterval
```

把范围扩到整个 `packages/`，认知层的关键入口**在自身模块、自身测试与 barrel 导出之外，调用点为零**：

| 导出能力 | 外部调用点 |
|---|---|
| `decideWrite`（价值驱动写入） | **0** |
| `decideRetrieval`（主动弃权） | **0** |
| `defaultValueFunction` | **0** |
| `resolveContradiction`（冲突消解） | **0** |
| `currentFacts`（双时态查询） | **0** |
| `consolidate`（Hebbian + FSRS） | **0** |
| `MemoryGraph` | **0** |
| `sinkhorn`（最优传输） | **0** |
| `retrievability` / `review`（FSRS） | **0** |

**解读**：LongMemEval-S 的成绩由 `cortex-eval/src/natural-language-memory.ts`（2,817 行）与
`retrieval.ts`（1,136 行）产生——那是一套自行实现检索、自行判定弃权、自行拼装提示词的独立
系统。`README.md` 描述的「价值驱动认知记忆层」是一个**测试完备、但产品路径上无人调用的库**。

### 1.1 两个必须先说清的限定条件

这两点会削弱结论的表面冲击力，但它们是严谨读者首先该提的反驳，因此前置声明：

1. **评测逻辑本就该待在评测包里。** 一个测量装置从单一来源引入被测对象，**是正确的工程
   选择**——它让仪器独立于被测物。缺陷不在 import 图，而在**没有任何产品路径**把
   `cortex-core` 的认知层组合成可运行系统。因此 `cortex-eval` 连「原则上能测」都做不到。
2. **`cortex-core` 按设计是纯的。** 它的算法是契约加纯函数，测量装置**本可以直接驱动**。
   但它没有。这正是「已验证的库」与「被测量的系统」是两句不同的话的原因。

两个限定条件都不改变结论：`README.md` 售卖的东西与基准实际驱动的东西之间的落差，与上面
描述的完全一致。

### 1.2 文档并非毫无自觉，但自觉程度被低估

本仓库 `05-longmemeval-sota-analysis/memory-benchmark-sota-landscape.md` §6 已经写了
「图扩散激活 ⚠️（在 core 中，未接入 MR/TR）」。这一条是诚实的，但它**严重低估了范围**：
未接入的不是一项能力，而是**几乎整个 `cortex-core` 表面**。

---

## 2. `SOTA-BASELINE.md` 实质性过期

该文档声明：

> **Measured on:** `master` @ `a52628f` (revert of the DCG experiment)

`a52628f` 是真实提交，但**不是当前 `master`**：

```
a52628f 与 master 之间的提交数：        55
eval src 变更量（30 个文件全部）：      +8,326 / −227 行
```

其中 52 个提交触及 `packages/cortex-eval/src`，包括日期区间召回臂、按发生日期召回、
零 LLM 实体图召回臂（**后被回滚**）、时间窗标注、弃权重试配对臂、R4 合取分解扩展臂等。

**一份测量仪器此后被改写 8,326 行的冻结基线，不能被引用为「Cortex 的当前成绩」。**
`83.55%` 在进入任何对外文档或决策文档之前，必须在 `31a3371` 重测。

### 2.1 交叉矛盾

本仓库 `longmemeval-sota-research.md` 记 83.50%，分项 IE 94.83 / MR 76.65 / KU 78.47 /
TR 75.79 / ABS 99.17；而 cortex 的 `SOTA-BASELINE.md` 记 83.55%，分项 IE 94.50 / MR 77.07 /
KU 78.47 / TR 75.79 / ABS 100。**两份文档对同一基准给出不同数字**，且都未标注彼此存在。
这一项已在 `07-sota-roadmap.md` 中列为必须先消解的前置条件。

---

## 3. 两项被宣传但不存在的能力

### 3.1 TD(λ) 信用分配——不存在

`ARCHITECTURE.md` 与 `README.md` 都把检索即巩固描述为「Hebbian + FSRS + **TD(λ)**」，
白皮书更是把整条创新主线建立在「TD(λ) 资格迹沿记忆 DAG 信用分配」之上。

```
grep -ri "td(λ)"       packages/ → 0 个文件
grep -ri "eligibility" packages/ → 0 个文件
```

仓库中**没有任何时序差分机制、资格迹或信用分配**。`consolidate()` 实际只做三件事：
FSRS 状态更新、共激活边强化、阈值遗忘。

### 3.2 最优传输蒸馏——已导出，从未调用

`ARCHITECTURE.md` 列出「跨层蒸馏 | 熵正则最优传输 | Sinkhorn-Knopp」。
`sinkhorn()` 与 `squaredEuclideanCostMatrix()` 确实存在于 `cortex-core/src/math/ot.ts`
且实现正确（有测试覆盖），但**唯一引用 `math/ot` 的文件是 barrel `index.ts`**：

```
grep -rn "math/ot" packages/ → 仅 index.ts（加测试）
```

`consolidation/consolidate.ts`——那个在文件头注释里声称 "cross-layer distillation" 的模块——
根本没有 import 它。该注释描述的是意图，不是其下的代码。

### 3.3 其他被宣传但缺失的条目

| 宣传出处 | 实际情况 |
|---|---|
| 弃权置信度的 Platt / 温度校准 | 全仓库无 `platt`、无 `temperature scaling` |
| IVF / HNSW 向量索引 | 只有 `BruteForceVectorIndex`；`pgvector` 仅出现在一处类型注释 |
| 浏览器后端（sql.js / IndexedDB） | 无匹配 |
| 多模态记忆 | 无匹配 |
| pgvector 横向扩展路径 | `cortex-node` 只有 `PgStorage`（JSONB） |
| CRDT 多智能体合并 | 无匹配 |
| provenance DAG / 不可变审计日志 | `provenance.ts` 是一个 552 字节的类型文件 |
| 记忆投毒防御 | `poison` 只出现在一处文档注释和一个无关测试中 |

> 这些条目并非「尚未实现所以有错」——路线图上有未完成项是正常的。问题在于它们**以已完成
> 能力的形式出现在文档的能力表中**，且没有任何状态标注。

---

## 4. 确实为真、应当明确背书的部分

这些经过验证，是项目真实的资产，不应因上面的偏差而被稀释：

1. **分层与文档完全一致。** `cortex-core` 零 I/O 依赖，具体引擎位于 `cortex-node` /
   `cortex-llm`。依赖倒置干净。
2. **Float64 数值纪律是真实的。** `Kahan` 求和、Welford 方差、`ml-matrix` Float64 线性代数
   均在位且有测试。
3. **统计工具链是本项目最强的资产**，也是基准真正的立足点：`welchTTest`、`studentTCdf`、
   `logGamma`、`binomialCdf`、`wilsonScoreInterval`——这套统计基础设施优于多数竞品。
4. **覆盖率与测试诚信与声明相符**（见 §0 表），且**确实没有 mock**：真实
   `better-sqlite3`、真实 `pg-mem`、真实本地 HTTP 服务。
5. **`cortex-core` 的 87 个测试有实质意义**——它们验证算法行为，而非验证导出存在。
6. **负结果被如实记录且被执行。** `p3b-graph-verdict.md`、`p24-cap-refuted.md`、
   `mr-plan-refuted.md` 等文档记录了被证伪的假设，且 `7780071` 真的回滚了对应代码。
   这种「测到不利就撤销」的纪律在同类项目中罕见，是本项目最可信的部分。

---

## 5. 偏差清单（按严重度）

| # | 偏差 | 严重度 |
|---|---|---|
| D1 | 没有任何文档说明**评测路径到底是什么**（`natural-language-memory` + `retrieval`），以及它与 `cortex-core` 的关系 | **P0** |
| D2 | `SOTA-BASELINE.md` 引用的基线落后 55 个提交；不存在当前版本实测值 | **P0** |
| D3 | `ARCHITECTURE.md` / `README.md` 宣传的 TD(λ) 与 OT 蒸馏均未接线 | **P0** |
| D4 | 无任何 `vitest.config.ts` 强制覆盖率阈值——≥95% 是约定，不是门禁 | **P1** |
| D5 | `longmemeval-sota-research.md`（83.50%）与 `SOTA-BASELINE.md`（83.55%）数字冲突，且分项不同 | **P1** |
| D6 | `memory-benchmark-sota-landscape.md` 仍把「图扩散激活接入 MR/TR」列为 P0/P1，但该方向已实测并**回滚** | **P0** |
| D7 | 白皮书 `01` 把 TD(λ) / Sinkhorn / Platt 作为已完成机制写入创新支柱与复刻矩阵 | **P0** |
| D8 | `03-implementation-and-acceptance-plan.md` 的 M1–M7 里程碑未标注任何一项的实际完成状态 | **P1** |
| D9 | `05/memory-benchmark-sota-landscape.md` §6 把 RRF 融合标为缺失（❌），但 `rrf-retrieval-fusion-verdict.md` 已判 **ACCEPTED**（`afd5dd5`，MR +5.25/轮，p = 0.0143） | **P1** |
| D10 | `05/memory-benchmark-sota-landscape.md` §7 的 ROI 排序与 §6 自相矛盾：§7.3 第 2 项仍推荐图/双时态接入 TR，而 §6 同表已承认图激活只到「在 core 中」 | **P0** |

**D9 与 D10 的性质不同于 D1–D3。** 前者是「文档落后于代码」，后者是
「文档内部自相矛盾」——同一份文档的 §6 与 §7 对同一能力给出冲突判断。这类矛盾的危害
高于单纯过期：它使读者无法判断该信任表还是该信任结论。

---

## 6. 偏差的根因与闭合路径

### 6.1 根因不是算法缺失，而是缺少组合层

修复方式**不是**把 `cortex-core` 塞进 `cortex-eval`——那会让仪器与被测物坍塌成一体。
基准**应当**测量的那个系统属于产品层，而它不存在。

| 层次 | 包 | 职责 | 状态 |
|---|---|---|---|
| 契约 + 纯算法 | `cortex-core` | `decideWrite`、`decideRetrieval`、`resolveContradiction`、`consolidate`、`MemoryGraph`、`sinkhorn`、FSRS、双时态 | ✅ 存在 ✅ 有测试 ❌ 无人调用 |
| **组合层** | **`cortex-memory`（待建）** | **把上述能力组合成满足 core 自身契约的 `MemorySystem`** | ❌ **缺失** |
| 后端 | `cortex-node` | `SqliteStorage`、`PgStorage` | ✅ 存在（仅存储） |
| 提供方 | `cortex-llm` | LLM 与 embedding 适配器 | ✅ 存在 |
| 仪器 | `cortex-eval` | 测量任何满足 `MemorySystem` 的实现 | ✅ 存在 |

依赖方向保持无环，且 `cortex-eval` 得以继续充当仪器而非参与者：

```
cortex-core  ←  cortex-memory  →  cortex-node
                     ↑                （注入 Storage）
                     └── cortex-llm   （注入 LLM / Embedding）
                              ↑
                        cortex-eval     （依赖 cortex-memory 并测量它）
```

`cortex-eval` 自有的 `natural-language-memory.ts` **保留为对照臂**，使基准能同时报告
参考管线与认知组合层的结果。

### 6.2 完整推进方案

见 [07 SOTA 推进计划](07-sota-roadmap.md)。该文档给出：前置契约、优先序表、
每项的验收判据、消融设计与停止规则。

### 6.3 本次闭合过程中新发现的一类偏差：配置无法抵达测量

§1–§5 记的都是**能力不存在**（认知层无人调用、被宣传的能力查无实据）。
闭合过程中发现了另一类，症状完全不同：

> **能力存在、代码正确、测试全绿 —— 而配置无法从调度入口抵达测量。**

它出现过三次，每次都在更外侧的一层：

| 出现 | 层 | 症状 |
| --- | --- | --- |
| 第 38 轮 | `.github/workflows/benchmark.yml` | 开关没有 input，操作者设了也到不了 |
| 第 38 轮 | `bench-cli` 的 arm options | 同一变量在两个文件里被读，互不知情 |
| 第 44 轮 | dispatch 脚本 / workflow / arm options | `sourceTrust` 在四层中的三层被静默丢弃 |

**这类偏差为什么比 §1–§5 更难发现**：§1 那种偏差会留下「无人调用」的痕迹，
而这一类**没有任何痕迹**。GitHub 接受未声明的 dispatch input 并静默丢弃，
运行正常启动、arm 正常执行、产物正常产出，产物内部没有任何两处互相矛盾。
唯一出错的地方是产物描述的是**操作者意图中的配置**，
而读产物的人没有第二份文件可以对照。

**闭合方式与 §1–§5 相同：不是写一条规则，而是加一道闸。**
`tools/__tests__/test_dispatch_inputs.py` 双向断言
「dispatch 发出的键都必须已声明」与「已声明的 arm input 都必须被转发进 `env`」，
并以三次注入验证它会响。这与 `check-shell-interpolation.py` 的理由同构 ——
**只写在文档里的规则会被遵守到下一次有人赶时间为止。**

这条经验对后续里程碑（N3–N7）直接适用：每一个新开关都必须同时回答
「它被谁读」「它怎么被送达」「送不到时会发生什么」，
而第三个问题的答案是「什么都不会发生」时才真正危险。

### 6.4 第三类偏差：测试在测量机器的安装状态

第 45 轮发现，与 §1–§5 和 §6.3 都不同的第三种形态，症状是**本地全绿、CI 全红**：

> **一个测试的结论依赖于「这台机器装了哪些包」，而不是依赖于被测代码。**

具体机制值得完整记下，因为它是一个容易被忽略的静默陷阱：

| 事实 | 后果 |
| --- | --- |
| `@xenova/transformers` 是 `cortex-llm` 的 **optional** 依赖 | `pnpm install --frozen-lockfile` 不装它，开发机常装 |
| **`vi.mock` 只拦截能解析到的模块** | 依赖缺失时 mock 静默失效 |
| 真实 `import` 执行、`sharp` 加载失败 | **该失败是一个 `Error`**，代码走另一条分支 |

**这与 §6.3 的同类之处在于「静默」**：没有任何一行输出提到「可选依赖不在」。
不同之处在于，§6.3 的缺陷在产物里不可见，而这一类的缺陷**只在 CI 里可见、在开发机上不可见** ——
反过来也一样，开发机上的绿在任何一次干净安装上都不成立。

**修正方式与本项目的两条既有原则一致**：
1. **把故障条件构造出来，而不是指望环境提供它** —— 用调用方注入替代 `vi.mock`，
   于是同一份代码在依赖存在与缺失两种情况下走同样的路径。
2. **验收必须在导致失败的那个条件下做** —— 把可选依赖移出 `node_modules`，
   复现 CI 条件后重跑整个门禁（`rc=0`，四维覆盖率不变），
   最后由 CI 本身确认（`37191170538` `failure` → `37255185307` `success`）。

**对 N3–N7 的直接含义**：任何涉及 optional 依赖、外部网络、或环境变量的测试，
都必须能在「该项缺失」的条件下运行，否则它测的是开发机的配置。
这是本项目「empirical readback 优先于推理」在测试设计上的同一条要求。

---

## 7. 复核方法

本文档所有数字均在 `31a3371` 本地产生。`better-sqlite3` 原生模块基于本地 Node 头文件从源码
构建；环境无法获取预编译产物，因此需要 `pnpm install --ignore-scripts` 配合
`node-gyp rebuild --nodedir`。`pnpm build` 之后全套测试复现全绿。

复现命令：

```bash
pnpm install && pnpm build && pnpm check
```

独立复核 §1 的调用点计数：

```bash
grep -rn "decideWrite\|decideRetrieval\|resolveContradiction\|currentFacts\|sinkhorn" \
  packages --include='*.ts' | grep -v 'cortex-core/' | grep -v '\.test\.ts'
# 预期：无任何匹配
```

复核 §2 的基线差距：

```bash
git rev-list --count a52628f..HEAD
git diff --shortstat a52628f..HEAD -- packages/cortex-eval/src
```

> 本审计的英文原始版本位于 cortex 仓库 `docs/AUDIT-CODE-VS-DOCS.md`，两者内容一致。
