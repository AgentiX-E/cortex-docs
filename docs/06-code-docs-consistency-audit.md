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

### 6.5 第四类偏差：注册数字的漂移（键级闸看不见的那一半）

第 46 轮发现。它与 §6.3、§6.4 并列，症状是**全链路都工作、产物照常写出、而值是错的**。

`tools/__tests__/test_dispatch_inputs.py` 守两个方向：派发脚本发的每个键都是
`workflow_dispatch` 声明的输入，且每个声明输入都有 `env:` 转发。
**在这两个断言全绿的情况下**，`tools/dispatch-cortex-memory-ab.py` 当时发的是
`cortex_memory_retrieval_threshold: '0'`，而预注册文档 §10.3 注册的是
`retrievalThreshold: 0.25`；同时它**根本没发** `cortex_memory_threshold` 键，
靠 workflow 默认值恰好落到注册的 `threshold: 0`。

这是 §7.3 那条 side-channel 的**第四种形态**，前三种都已有守卫：

| 形态 | 出错的位置 | 由谁抓 |
| --- | --- | --- |
| 一 | 输入未在 workflow 声明 | `test_dispatch_inputs.py` |
| 二 | 声明了但没转发进 `env` | `test_dispatch_inputs.py` |
| 三 | 转发了但 arm 从不读 | `bench-memory-arm.test.ts` |
| **四** | **读到了，但派发从不发送注册的值** | **`test_preregistration_config.py`** |

**为什么形态四最难看见**：形态二的症状是**值缺席**，缺席会被缺省值掩盖；
形态四的症状是**值错误**，而错值不会缺席 —— 它照常打印、照常写进产物，
读起来完全自洽。本轮之所以暴露它，是因为 §10.6 的前置条件要求**读日志行本身**，
而那一行写着 `retrievalThreshold=0.25`… 唯一的问题是：**当时的脚本发的是 `0`**。
前置条件只点了 `sourceTrust` 一个变量，`retrievalThreshold` 不在它覆盖范围内。

**修正与「三重防线」原则一致**：
1. **修正值本身** —— 脚本改发 `threshold: '0'` 与 `retrievalThreshold: '0.25'`。
2. **把比较对象从「workflow 默认值」改成「注册文档」** ——
   新增 `test_preregistration_config.py`，**从 §10.3 原文读值**，经一张显式映射表
   对照派发脚本的 `INPUTS`。测试里**不重写 `0.25`**：那会成为数字的第三份副本，
   而副本会被人打开哪个文件就先改哪个 —— 那正是这个缺陷本身。
3. **双向断言** —— 只改注册文档会红，只改派发脚本也会红。
   三个注入验证过它不空转：改回 `0`、删掉键、只改 §10.3，全部被抓。

**可推广的结论**：**对「键的接线」设闸，不等于对「键的值」设闸**；
对预注册实验而言，值才是承载论断的那一半。
一个以「日志行命名 X」形式书写的验收条件，其强度等于 X 的覆盖集合 ——
而那个集合是在第二个闸门存在之前选定的。

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

### 6.6 第五类偏差：注册与派发之间的一致性，本身没有被守卫

§6.5 记录的是「**键级闸看不见的那一半**」—— 一个注册值漂移了，而所有既有的键级
守卫（`test_dispatch_inputs.py` 的两个方向）都通过了，因为它们只问
「键是否声明、是否转发」，不问「值是否等于注册值」。

§6.5 的修法是 `test_preregistration_config.py`，它**从注册文件原文读值**再与派发对账。
本节记录的是**这个修法本身被发现还不够的那一步**。

#### 6.6.1 问题：双向守卫看不见对称回退

`test_preregistration_config.py` 保证的是**派发与 §10.3 一致**。
这在正常情况下是正确的不变式 —— 但它有一个必然的盲区：

> 任何**同时**修改两侧的编辑都满足它，无论改到什么值。

§10.9 的否证恰好制造了这个情形。`retrievalThreshold: 0.25` 输 186 题、赢 0 题
（McNemar p = 2.039e-56），预承诺的回退是把两侧都改回 `0`。
回退之后双侧一致，守卫通过 —— 但如果将来有人把双侧**同时**改回 `0.25`，
守卫**仍然通过**，而被重新武装的是一个已被证明有害的配置。

**「两侧一致」与「这一侧是对的」是两件不同的事。** 前者是可判定的，
后者不是（守卫的文档注释自己就写了：它故意不检查「注册值是否正确」，
因为那会让测试为一次合法的重新注册而失败）。所以这里不能加一个断言
声称 `0.25` 是错的 —— 那会把「禁止 redraw」的规则硬编码成一个数字检查。

#### 6.6.2 修法：钉住理由，而不是钉住数字

新增的断言检查的是**否证记录仍然存在**：

- §10.9 必须存在（不是被删掉或被重新编号吞掉）；
- §10.9 必须命名产生该读数的 run id（`37313582403`），使否证可追溯到产物。

**未来的重新注册可以再选 `0.25`。** 但它必须**自己写一节**，
而不能靠删除 §10.9 来让旧结论消失。这把「禁止 redraw」的成本
从「一个数字不能变」改成了「一次重新主张必须留下痕迹」——
前者会随实验演进自然失效，后者不会。

#### 6.6.3 这一轮的另一个自身缺陷：修订位置会让解析器静默失效

`registered()` 的实现是从 `### 10.3` 标题读到**第一个空行**为止。

第一版 §10.3 修订把说明用的 blockquote **放在标题正下方**，
于是 `(.*?)` 只捕获到那个 blockquote，正则解析结果变成 `{}` / `[]` ——
**控制项测试（`test_the_registration_was_parsed`）直接失败**。

这是控制项存在的理由：一个匹配不到任何东西的正则会让它下面**每一条断言都变成空转**，
而测试仍然报告成功。本轮它按设计工作了 ——
**它拦下的是一次文档编辑，而不是一次代码缺陷**，这正是它该覆盖的失效面。

修法是把修订说明移到 bullet 列表**之后**。

#### 6.6.4 偏差分类表（更新）

| 类别 | 内容 | 守卫 |
| --- | --- | --- |
| 一类 | 配置无法抵达测量（输入未声明/未转发/从不读） | `test_dispatch_inputs.py`、`bench-memory-arm.test.ts` |
| 二类 | 测试在测量机器的安装状态 | §6.4 的 CI 修复 |
| 三类 | 注册数字漂移（键都在，值不对） | `test_preregistration_config.py` |
| **四类** | **注册键缺席（不是值错，是键根本没有发）** | **同上的双向对账** |
| **五类** | **对称回退：两侧同时改，一致性守卫必然通过** | **§6.6.2 的理由钉住断言** |
| **六类** | **配置值抵达了决策点，但被它阈值的量坍缩成一个点（惰性闸门）** | **§6.7** |

### 6.7 第六类偏差：闸门惰性 —— 值抵达了决策点，但决策点不可达

§6.3 到 §6.6 记录的五类偏差有一个共同前提：**只要把值送到决策点，它就会生效。**
第六类否证了这个前提，而它是在同一次读取里被发现的 —— 一次「设计正确、接线正确、
执行正确」的运行，测出来的却是一个**与被测机制无关**的数。

#### 6.7.1 现象

运行 `37313582403` 武装 `retrievalThreshold: 0.25`，弃答率 `+46.40pp`，
报告与文档都把这归因于准入闸门关闭。**闸门一次都没有关过。**

`admission.ts` 的取值链条把可达值钉成常数：

```
value = confidence(默认 1) × sourceTrust(0.5) × (0.5 + 0.5 × recency)
      = 1 × 0.5 × (0.5 + 0.5 × exp(0))        // lastAccessedAt === createdAt
      = 0.5                                    // 对每个准入的 turn 恒成立
```

`decideRetrieval` 比较的是 **value 函数的输出**（`value.ts:51`），
故 `≤ 0.5` 恒开、`> 0.5` 恒关，**边界精确落在天花板 `sourceTrust` 上**。
`[0, 0.5]` 内每个阈值都是同一次实验 —— 不是一个「位置偏高的分布」，是一个**点**。

`479` 次弃答全部来自模型输出 `UNANSWERABLE`。这次消融**没有测到闸门**。

#### 6.7.2 为什么前五类守卫全都看不见它

- **一类**（值没送到）通过了：值确实送到了，`decideRetrieval` 确实被调用。
- **三类/四类**（值错/键缺）通过了：`0.25` 正是注册值，键也在。
- `abstention-decision.test.ts` 通过了：它确实测了 `0.9`（关）与 `0.1`（开）——
  但它只变动**阈值**，从不变动**约束取值的那个天花板**。在「闸门只在单点可达」
  这一假设下，这两个样本与「旋钮完全惰性」**完全一致**，所以它区分不了两种假设。

> **测「旋钮有效果」不等于测「旋钮可达」。**
> 一个配置值可以被接受、写进产物、打印进日志，**同时完全惰性** ——
> 只要它所阈值的那个量，其取值范围被调用方的**其他**设置坍缩成了一个点。

#### 6.7.3 上游根因是一句文档陈述

`PREREGISTRATION-CORTEX-MEMORY-ARM.md` 第 453 行原文：

> `decideRetrieval` compares `confidence >= threshold`

实际实现比较的是 **value 函数的输出**；memory 上的 `confidence` 字段只是其**输入之一**，
从来不是被比较的量（局部变量名叫 `confidence`，纯属命名）。**结论碰巧对，理由全错。**

这给一类偏差加了新的查法：**一个「结论正确」的文档陈述不需要被复核，
除非它的理由被用来解释一个意外读数** —— 而那时错误理由会伪装成解释力。

#### 6.7.4 修法：守卫可达性本身

| 守卫 | 内容 |
| --- | --- |
| `retrieval-reachable-range.test.ts` | 钉住常数 `0.5`、钉住边界精确落在天花板、钉住抬高端口会放宽区间 |
| 变异测试 | 把 `sourceTrust` 从价值函数中拿掉 ⇒ **4 个断言全部失败**（确认守卫承重） |

#### 6.7.5 同一类缺陷的第二个实例：`sessionBudget`

`GateOptions.sessionBudget` 在 `types.ts` 里是一条**无条件**承诺
（"Upper bound on how many admitted turns may reach the prompt, counted across all
presented sessions"）。它并非无条件：

`selectSessionBudget` 只有**一个**调用点（`answerSessions` 内）；
其余接收 `sessions` 的路径走 `#admit`，而 `#admit` 直接返回 `admitSessions` 的结果、
**不施加预算**。`answerAbstention` 正是其中之一 —— 也就是**臂实验实际走的那条路**。

实测（预算 `1`，两个 session 各两轮）：

| 路径 | 进入 prompt 的 turn 数 | 预算是否生效 |
| --- | --- | --- |
| `answerSessions` | 2 | 是 |
| `answerAbstention` | **4** | **否** |

**这与 inert `retrievalThreshold` 是同一类缺陷**：一个被记录、被打印进派发行、
却到不了它所命名的那个决策的配置值。第二个字段用**同一个问题**问一遍就出来了 ——
说明这是一个**类别**，不是一次意外。守卫：`session-budget-on-every-path.test.ts`
（断言两条路径**一致**，且平坦路径不受影响）。

#### 6.7.6 诊断缺口（同一轮补上）

`decisionReasons` 只在 `cortex-eval/bench/run.ts`（参考 CLI）产出，
`cortex-memory/bench/run-ablation.ts` **不产出** —— 所以臂的产物**无法说明**
一次弃答来自 `empty` / `threshold` / `llm`，错误归因因此在产物层面**不可反驳**。

修法不是让 harness 事后重建，而是**让被测系统自己产出**（`abstentionReasons()`），
经 `CortexMemoryArmResult.abstentionReasons` 透传进产物并打印。三个硬化点：
普查是**可选能力**（不进 `MemorySystem` 契约）；载荷畸形时**缺失而非伪造**；
读取抛错**不丢弃已测得的端点**。

### 6.8 第七类偏差：计算正确、归因正确、但没送到读者手里

前六类都在讨论**值与决策**的关系（送不送得到、值对不对、能不能判别）。
第七类在决策**之后**：一个值被正确地计算、正确地归因、正确地写进 JSON，
**却没有出现在读者打开的那份文档里**。

#### 6.8.1 三次同一个模式

| 实例 | 计算 | 归因 | 丢失环节 |
| --- | --- | --- | --- |
| `cohortCoverage`（`0e2c30e`） | ✓ | ✓ | 返回在 report 旁边，`formatAblationReport` 拿不到 |
| `retryFires` | ✓ | ✓ | 靠调用点字符串拼接进 Markdown，重新渲染即丢 |
| `abstentionReasons`（§49.2） | ✓ | ✓ | 只进了 JSON，从未被渲染 |

三者的**修法是同一句话**：**把它放进 report 里**。放进 report 之后，渲染器
**不可能**在没有它的情况下产出文档 —— 这从「记得渲染」这种纪律问题，
变成类型层面的不可能。

#### 6.8.2 为什么「JSON 里有」不算送到了

读者打开的是 Markdown。§10.10 的失败形态正是**只看消融表就下结论** ——
而普查本可一眼反驳。把普查放进没人渲染的字段，表格的歧义**完全不变**：
一个 delta，没有归因。

#### 6.8.3 顺序是关键，不是细节

```
census = abstentionReasonsOf(feature)          // 先读
reported = { ...report, abstentionReasons }    // 再放进 report
markdown = formatAblationReport(reported)      // 最后才渲染
```

若按自然的写法（先 `formatAblationReport(report)`，再读 census 返回在旁边），
Markdown 永远拿不到它。**这里的 bug 不在逻辑里，在调用顺序里**，
因此它不会被任何单函数测试发现 —— 只有端到端断言
「Markdown 里含有普查」能抓到（`bench-memory-arm-census.test.ts`）。

#### 6.8.4 附带的第八类苗头：照着邻居抄的形状

`retryFireLines` 是导出的（有第二个调用者 `formatRetryFireSection`）；
我照抄它的形状导出了只有**一个**调用者的 `abstentionReasonLines`，
被 export census 当场报成 new orphan。

这不是误报。**照着「旁边的函数这么做」写而不问「它为什么可以这么做」**，
是从正确实现里复制出一个错误的动作 —— 与本轮别处修的那些缺陷同源。
该类目前不需要独立守卫，因为 `pnpm check` 的 export census **已经**覆盖了它，
且本轮验证了它会拦下。

### 6.9 第九类偏差：修好了**可达**，但没修好**可判别**

§6.7 记录的是「闸门惰性」——值抵达了决策点，但决策点不可达（区间退化成 `{0.5}`）。
本轮（§50）修的是同一处的另一半，而它揭示了一个此前没有被分开的两个概念：

| 性质 | 问题 | 在 §6.7 的修复之后是否成立 |
| --- | --- | --- |
| **可达（reachable）** | 是否**存在**一刀能关上闸门？ | 成立 —— `0.9` 在 `0.5` 下关、在 `1` 下开 |
| **可判别（discriminating）** | 闸门能否**分开**强候选与弱候选？ | **不成立** —— 每个 turn 仍恰好得 `1` |

`sourceTrust: 1` 时区间是**集合** `[0, 1]` 而不再是点，但区间内每一刀仍是全有全无：
`0.9999` 全过、`1 + 1e-9` 全不过。**把一个区间从点拓宽成集合，与在区间里引入分布，
是两个不同的操作**，而只做了第一个。

失败不在于那次修正是错的，而在于把「区间不再是点了」读成了「闸门现在能用了」。
更一般地：

> **一个输入是常数的闸门，无论可比区间多宽，都无法判别。**

#### 6.9.1 为什么既有测试看不见它

`retrieval-reachable-range.test.ts` 的四个断言**全部关于区间**：边界、边界处的常数、
抬天花板后的拓宽、边界的精确位置。它可以在被测量的那个东西**完全缺席**时全绿。

新增的 `retrieval-discrimination.test.ts` 断言的是**离散度**：两个 turn 得到两个不同的值、
区间内部的一刀能分开它们、最强候选之上仍能关上（控制项）、
以及不给回调时旧的常数行为**逐字不变**（兼容性）。

#### 6.9.2 与既有一至八类的区别

| 类别 | 形态 | 由什么发现 |
| --- | --- | --- |
| 侧信道（§6.3 / 6.5 / 6.6 的四种形态） | 配置值送不到决策点 | 比对配置与行为 |
| 闸门惰性（§6.7） | 值送到了决策点，决策点不可达 | 探测区间的**端点** |
| **可判别性缺失（本节）** | 值送到了、区间可达，决策点仍无法用它 | 探测决策能**分开什么**，而非能**达到什么** |

第三类比前两类更难察觉，因为**中间每一层都在正常工作**：值被解析、被转发、被应用、
被写进 artifact、被打印进日志。唯一的问题是被比较的那个量对每个输入都相同。

### 6.10 第十类偏差的苗头：变异的来源放在无人可测的位置

§6.9 留下一个必须回答的问题：如果组合层只拥有**机制**而信号是调用方的，
那么基准臂传什么？

直觉上最小的改动是**在 `bench/` 里写一个内联闭包**。这是错的，理由是本仓库已经
记录过一次的：`bench/**` 作为入口被排除在覆盖率之外，**写在那里的决定没有测试能抵达**
（`bench-arm-options.ts` 的文档记录了代价）。放进那里的变异，其**正确性没有任何东西检查**，
于是臂变成「用基线对比一个只有『运行完成了』这一条证据的机制」。

所以信号是 `src/**` 里的一个模块（`confidence.ts`），且刻意选择
**最弱但可辩护**的信号，而不是可选里最好的那个：

- 不需要模型、词表或调优语料 ⇒ 不可能编码任何关于基准答案的知识；
- 确定、只依赖内容 ⇒ 臂的 delta 里不会有它的噪声；
- 可肉眼核验 ⇒ 读者能自行确认更长的 turn 得分更高。

同时记录一条**区分真实信号与貌似信号**的性质，因为它无法从公式上看出来：

> **只在「运行中永远不会出现的输入」上变化的信号，在被评测的那次运行里就是常数信号。**

`min(1, length / 10_000)` 有界、确定、只依赖内容，且在 LongMemEval 的每一个 turn 上都是常数。
`confidence.test.ts` 因此针对**形如基准的上下文**断言离散度，而不是针对公式断言；
并且用「过滤后的上下文」断言退化变体确实退化成它代表的那个常数。
（该测试的第一版用未过滤的上下文跑 `min(1, length / 10_000)`，得到 8 个不同值而失败；
修正是让变体的主张**关于一个上下文**，而不是关于它自己的公式。）

### 6.11 第十一类偏差：守卫的自身测试带着一个从未生效的变异

在 §6.9 / §6.10 之后，审查这一轮的两仓库门禁时发现的是**另一类**问题，
而且它的形状恰好是本节标题所描述的那个：

> **一个从未真正施加的变异，会让「这个检查坏了」和「这个检查正常」长得一模一样。**

`cortex-docs` 的 `tools/check-analysis-record.test.sh` 用 7 个用例逐个复现守卫
存在的理由。其中「未翻译文档会被抓住」的用例，其变异方式是从 `$SOURCES` 复制英文原版
覆盖记录中的同名文件：

```bash
cp "$SOURCES/longmemeval-sota-research.md" "$WORK/repo/$RECORD_REL/longmemeval-sota-research.md"
```

而**这个文件在 `$SOURCES` 里不存在** —— 守卫的记录里就有同名文件，且已经是中译本。
于是 `cp` 失败、记录保持干净、守卫输出 `exit=0`，用例期望 `1`，报告：

```
FAIL  untranslated document is caught (exit=0, expected=1)
```

#### 6.11.1 为什么这条失败信息是错的，而检查是对的

这条信息读起来像是「`untranslated` 检查坏了」。实际上检查**工作正常**：
把一份纯英文文档放进记录，它会被抓住（§6.11.2 的两个变异都验证了这一点）。
坏的是 **fixture** —— 它没有制造出它声称在制造的那个状态。

`set -euo pipefail` 没有兜住它，因为 `cp` 的失败**没有被 `&&` 或 `if` 连接到后面的
`run` 调用**：`cp` 是一条独立语句，其后是另一条独立语句，`run` 自身的退出码
才是函数返回给断言的东西。**一条被断言吞掉的失败命令，等于没有跑过。**

这与本仓库已经记过的两条是同族的：

| 已有记录 | 形态 |
| --- | --- |
| §6.9 | 值被解析、转发、应用、落盘、打印，**但被比较的那个量对每个输入都相同** |
| §6.10 | 变异的来源写在**没有测试能抵达的位置** |
| **§6.11** | **变异本身没有施加成功，而断言把它读成了「检查坏了」** |

三者的共同后果是同一个：**测试通过（或失败）的理由，与它声称在测的东西无关。**

#### 6.11.2 修法与判别力验证

修法是让 fixture **自己产出**那个状态，而不是去 `$SOURCES` 找一个不存在的文件 ——
这本来就是守卫文档里写下的设计（「asserts against the same originals the fidelity
check uses」，即英文原版提供的是**保真度**基准，而「未翻译」这个主张必须由
测试**合成**）：

```bash
printf '# LongMemEval-S SOTA research notes\n\nA wholly untranslated document.\n' \
  > "$WORK/repo/$RECORD_REL/longmemeval-sota-research.md"
```

两个变异注入确认这条用例现在真的在测它声称的东西：

| 变异 | 结果 |
| --- | --- |
| `THRESHOLD=40` → `THRESHOLD=0`（检查永不触发） | `FAIL untranslated document is caught` |
| `\p{Han}` → `\p{Latin}`（模式不匹配任何汉字） | `FAIL untranslated document is caught` |

修复后：`check-analysis-record.test.sh` **7/7 cases**，
`check-analysis-record.sh` 六项全 `ok`（含 `guard self-test`、`numeric fidelity: 94/94`）。

> **对后续工作的约束**：一个「守卫的守卫」如果不能在自己的变异没有施加成功时报错，
> 它就只是在为守卫的**存在**背书，而不是为守卫的**有效性**背书。
> 判据不是「这个用例跑过了」，而是「把这个用例要防的失败亲手制造出来，它响了」。
