# `cortex-agent` 的包边界，与 MemCog 到底能搬过来什么

> 触发：`ask=enumerated`（`44962474136`）在跑期间的两次提问。
> 本文只做事实核查与判据，不派发、不改代码。
> 结论先行，证据在后，每条都可复核到文件行或 artifact。
>
> **后续（2026-11-22）**：§1 的结论已作废并被取代，见 `DECISION-AGENT-MERGE.md`。
> 作废的原因不是论证错，是前提变了：B′ 端口化把"依赖倒置"这条代价消掉了，用户随后选择
> 用"零共同演进（0/11 提交）"这条判据换"少一个包"的产品形态。§2 关于 MemCog 的部分不受影响
> ——未开源、表 2 拼装、架构消融只值 2.43 点这三条仍然成立。

## 0. 两个结论

1. **`cortex-agent` 不该并进 `cortex-ai`。** 技术上行得通（不是循环依赖），代价却不对称：
   合并能省下的是一个 `package.json`（1,159 行、10 个文件，是本仓六个包里最小的），
   要付的是**依赖方向倒置**与**用户注入契约从接口层降到配置层**。
   如果将来一定要收，正确的落点是 `cortex-memory` 的 `./agent` 子路径，不是 `cortex-ai`。
2. **MemCog 没有开源，"复刻它的代码"没有对象；而"用它的架构配我们的 reader/judger"，我们两个月前就做完了，
   只是从没接线到评测臂。** 这就是它没变成分数的唯一原因。

## 1. 问题一：为什么不把 `cortex-agent` 放进 `cortex-ai`

### 1.1 事实

| 包 | 源文件 | 行数（不含测试） | `dependencies` | 导出面 |
| --- | --- | --- | --- | --- |
| `cortex-core` | 48 | 11,974 | `ml-matrix` | 单一 |
| `cortex-ai` | 20 | 3,888 | `cortex-core` | `.` / `./local` / `./web` |
| `cortex-memory` | 37 | 19,169 | `cortex-core` | 单一 |
| `cortex-storage` | 10 | 1,802 | `cortex-core`（peer：`better-sqlite3`、`pg`） | 单一 |
| `cortex-agent` | 10 | **1,159** | `cortex-core`、`cortex-memory` | 单一（5 个名字） |
| `cortex-eval` | 91 | 47,082 | `cortex-ai`、`cortex-core` | 单一 |

依赖图当前无环，且 `cortex-agent` **不依赖** `cortex-ai`：

```
core ──┬── ai ── eval
       ├── memory ── agent
       └── storage
```

### 1.2 两者的职责不是"都碰 LLM"，而是"怎么连"与"连上之后问什么"

- `cortex-ai` 是**供应商适配**：`llm/openai-compatible.ts`、`embedding/openai.ts`、`local/*`（transformers.js）、
  `web/platform-language-model.ts`、`pacing.ts`、`retry.ts`、`quota-error.ts`。
  它回答的问题只有一句：**这个 provider 怎么调**。
- `cortex-agent` 是**读什么**：`prompt.ts`（决策提示词是什么形状）、`parse.ts`（回复怎么解析、什么算解析失败）、
  `stop.ts`（什么时候停）、`trace.ts`（每一步记什么）、`compose.ts`（结果交给谁渲染）。
  它回答的是：**读者自己决定下一步看什么**。

同一个包要同时容下这两句，`cortex-ai` 的 `.` 导出面就会变成"模型接入 + 检索策略"。

### 1.3 合并的代价，四条（其中一条我核查过、不成立，先排除）

| # | 代价 | 是否成立 | 依据 |
| --- | --- | --- | --- |
| 1 | 破坏浏览器构建 | **不成立** | `cortex-core` 与 `cortex-memory` 的 `src/` 里 `from 'node:` 命中数为 **0**；`./web` 不受影响。这条不能拿来当理由 |
| 2 | 依赖方向倒置 | 成立 | `cortex-ai` 现在只依赖 `core`，是叶子；并入 `agent` 后必须依赖 `cortex-memory`（19,169 行，本仓最大业务包）。只想接一个 embedding 的用户被迫装进索引与渲染契约 |
| 3 | 用户注入从接口层降为配置层 | 成立 | §14.98.3 原计划写的是 `cortex-agent → {core, ai, memory}`；§14.98.7 主动改为 `{core, memory}`，原话：「循环只吃 `cortex-core` 的 `LLM` 接口。依赖适配器包等于依赖供应商清单，而约束 11 要求供应商可换、用户可注入」。`types.ts:17-19` 有同一段注释 |
| 4 | 覆盖率门禁的失败模式混叠 | 成立 | `cortex-ai` 的测试是 provider parity（`test:parity`，同一 prompt 跨 provider 等价）；`cortex-agent` 的测试是策略行为（停止规则、解析容错）。合成一包后一个阈值同时守两类不相关回归 |
| 5 | 单一渲染路径变弱 | 成立 | `loop.ts` 末尾写明它**不写答案 prompt**，只把 `selected` 交给 `cortex-memory` 的 builder，所以多步与注册臂共用一条渲染路径、数字可比。并入 `ai` 后适配层会持有渲染契约的引用 |

### 1.4 成本不对称这件事本身

合并省下的东西是可枚举的：一个 `package.json`、一份 `tsconfig.json`、`turbo` 图里一条边。
代价是 §1.3 的第 2、3、4、5 条。1,159 行不是维护负担，147 万行里它是唯一一个**小于 2,000 行**的功能包。

### 1.5 什么条件下我会同意收

到 `cortex-memory` 的 `./agent` 子路径，而不是 `cortex-ai`，且要同时满足：

1. `cortex-memory` 先拆出 `index`（索引与选择）与 `render`（装配与渲染）两个内部层，使 `agent` 只吃前者、只通过后者的公开函数输出；
2. `agent` 的公开面从 5 个降到 2 个（`retrieveStepwise` + `composeAgentPrompt`），因为 `indexRetrieval`、`carriedIds` 在新位置是内部函数；
3. 导出普查（`census:check`）能对子路径导出继续做"无调用者即缺陷"的判定。

三条任一条不满足，就不是"合并省事"，而是"把一套策略埋进一个更早发布、被更多下游依赖的包里"。

## 2. 问题二：MemCog

### 2.1 事实核查第一层：它没有开源

arXiv 2605.28046（Tencent WeChat，2026-05-27）全文**没有任何代码发布声明**。唯一外部链接是脚注 1：

```
Available at https://anonymous.4open.science/r/ProactiveMemBench-76E1/
```

那是 **ProactiveMemBench 的数据集**，不是 MemCog 系统的实现。文中对基线只说
"all other baselines are reproduced using their official implementations"——指**别人的**官方实现。

所以"拿 MemCog 的架构搭配我们的 reader/judger"这句话里，"拿"只能是从论文正文重建：
Dimensions/Pages/Sections 三层 + 四类有向链（`related_to` / `temporal_next` / `caused_by` / `contrasts_with`）
+ 四个导航动作 + Proactive Reasoning Protocol 系统提示。这**正是** `cortex-agent` 已经在做的那一族，
只是没有 MemWiki 那个三层产物。

### 2.2 事实核查第二层：95.80 的口径

| 项 | MemCog 95.80 | cortex 91.25 |
| --- | --- | --- |
| reader | **GPT-4o-mini**（表 2；另有 GPT-4.1-mini、GLM-5.1 的分行） | `deepseek-chat` |
| judge | GPT-4o | 同库 judge |
| baseline 行来源 | **抄自 Latimer et al. 2025 / Sen et al. 2026，未重跑** | 同 harness 配对 |
| 写路径 | GLM-5.1 对每题建 dimension/page/section + 聚类 + 建链 | 无（纯读） |
| 每题成本 | **论文未给**（会话数、token、费用全部缺失） | 按 artifact 的 `promptChars`/`calls` 实测 |
| 代码 | 未公开 | — |
| `MR` | 92.48 | 77.5 |

三条必须写下来的：

1. **"更低成本"没有出处。** 论文没有给 LongMemEval 的任何成本数字。而它的写路径是一次全量重建，
   我们的 91.25 是读路径。把两者并排说"它更便宜"不成立——**没测过的东西不能说便宜**。
2. **它的表里只有自己是现测的。** 这是 §3 那个模式第三次被独立确认：拼表会把"系统差距"与"测量差距"混成一个数。
3. **`abstention` 分项在它的表 2 里没有。** 我们的 91.25 含 ABS 30 题。

### 2.3 事实核查第三层：我们已经建了那一族，而且量过

`@agentix-e/cortex-agent`：reader 自己写 query、`maxSteps` 上限、`no-new-evidence` 停、检索委托
`cortex-memory` 已有的索引（不复制排序）、结果走同一条渲染路径。

探针 `44867629266`（`--steps 1 --capability MR`）：

```
cases                : 121 (MR, maxSteps 1)
reader calls         : 121, searches 106 on 106 questions
searches that added  : 118 questions
gold found by reader : 586 turns on 105 questions
gold: seed / selected / carried / total : 862 / 1448 / 1377 / 3663
found but not carried: 71
deciding prompt chars: 4141 per question
```

一句话：**读者自己搜一遍，命中金标轮次从 862 涨到 1,448（+586，+68%），交付 1,377。**
这是 `MR` 上唯一一个被量过、方向为正、且不换模型的信号。

### 2.4 它为什么没变成分数：`multiStep` 从未接进评测臂

```
$ grep -rn "multiStep" .github/workflows/ packages/cortex-eval/src/
（零命中）
```

- §149.2 记过一次：「`multiStep` 在 `cortex-eval`/`cortex-memory` 里**一次都没出现**」。
- §150.1 随后把接线**撤了**，理由是「`MR` 22 道稳定失败里 18 道的金标数字**已在提示词里**」。

### 2.5 §150.1 那个取消的适用边界（本文最重要的一条）

那句话描述的是 **22 道稳定失败**的病因：集合已全，读者算错。它对**那 22 道**成立。

但 `MR` 有 121 题，而探针量到多步在**证据覆盖**上净增 586 个金标轮次。
用"22 道的病因"取消"121 题的机制"，是把这一族失败的一种原因当成全部原因。

两者不冲突，因为它们是**两个不同的量**：

| 量 | 覆盖对象 | §150.1 的数 | 多步的数 |
| --- | --- | --- | --- |
| 提示里有没有金标数字 | 22 道稳定失败 | 18/22 = 82% | 未测 |
| 金标轮次交付率 | 121 题 MR | 未测 | 862 → 1,377（`carried`）/ 3,663 |

所以正确的写法不是"多步被否证了"，而是：**多步能救的那一半，和 §150.1 量的那一半，可能不重叠；
这件事一次配对派发就能分开，而它至今没被派过。**

同形状的还有一个：`sessionClock`（§151.2）建好、预登记写完、五条可达性链路钉住，**判据从未被读**，
缺的同样是"配对"这一环。这是本仓的**系统性病灶**，不是两个孤立事件。

### 2.6 为什么"100% 复刻"也拿不到 95.8

复刻能复刻的是架构（三层 + 四链 + 四动作 + 协议）。复刻不了的是 reader：

- 本仓自己的读数：`deepseek-v4-pro` 换掉 `deepseek-chat` → **−3 题**（`44507560716`）；
- 台账里唯一的 7B 行 `MEMTIER` **38.2**，与同表 frontier 行 90+ 之间夹着 50 点以上的 reader 效应；
- MemCog 自己的消融：`w/o Proactive` 95.00（−0.80）、`w/o Graph Overlay` 93.37（−2.43）。
  **它的架构贡献是 2.43，不是 95.80。**

所以"复刻架构 = 拿到分数"这个等式在它自己的消融里就不成立。要追 92.48 的 `MR`，
路径是"我们的 reader + 多步交付"，不是"它的 reader"。

## 3. 下一步（P0–P3，判据写在派发前）

| 级别 | 动作 | 前置 | 判据 | 成本 |
| --- | --- | --- | --- | --- |
| **P0** | 读 `44962474136`（`ask=enumerated`，500×4）并定序位 | 产物落地 | ≥92.75% 进确认；≤91.25% 关闭该轴写 `RETRACTIONS` | 已付 |
| **P0** | `multiStep` 接进 `cortex-eval` 臂，`0` 态**逐题复现注册臂** | 无 | 差异题数 = 0（§14.98.5 的不派发条件） | 0 |
| **P1** | `multiStep: 0 → 1`，只 `multi-session` 路由，121×2 重复 | P0 两条 | `MR` ≥ **+3 题**且配对 McNemar `p < 0.05`；账单 ≤ **1.15×** | ≤14 CNY |
| **P1** | 仪器判据：`trace.queries > 0` 且至少一步 `newTurns > 0` | 同上 | 否则测的是"更贵的单步" | 0 |
| **P2** | 若 P1 成立，`1 → 2`（MemCog 的 2–3 步） | P1 成立 | 同上，且账单 ≤1.30× | ≤18 CNY |
| **P2** | 若 `enumerated` 成立，`[thing N]` 在已采纳臂上配对 | `enumerated` 成立 | 121 题 ≥3 翻转 | ≤18 CNY |
| **P3** | `sessionClock` 的配对环节（同样"建好未派发"） | P1 结论 | 复用 P1 的配对脚手架 | ≤14 CNY |
| **P3** | MemWiki 三层产物（Dimensions/Pages）——**只从论文重建，无代码可抄** | P2 成立 | 不预先登记，因无公开可比数 | 未知 |

**反判据（写死，不许事后解释）**：P1 净增 < **+1 题** → 多步在该臂无效，`multiStep` 回 `0`，
结论写进 `AUDIT-MR-ENUMERATION.md` §10，并且**"MemCog 架构"这一族在 `MR` 上关闭**。

## 4. 一句话

`cortex-agent` 不需要被合并，它需要被**接线**；MemCog 不需要被复刻，它需要被**承认架构贡献只有 2.43 点、
剩下的是 reader**。这两件事的答案都不是"再设计一个包"，而是"把已经建好的东西派一次"。
