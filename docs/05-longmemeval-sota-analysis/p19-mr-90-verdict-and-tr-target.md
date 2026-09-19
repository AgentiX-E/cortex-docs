# P19 — MR 90.08% 是真实的吗？以及下一次迭代应走向何方

受分析的运行：`34791592602`（2026-09-14，`limit=all, runs=1, ablationRuns=1`，
temperature 0）。面板：2026-09-06 的 8 次运行，位于 `/workspace/analysis/ab_rrf`。
脚本：`analysis/scripts/p0_attribution.mjs`、`p0_recall_vs_decision.mjs`、
`p0_abstention_by_capability.mjs`、`p0_tr_mechanisms.mjs`、`p0_tr_elapsed.mjs`。

---

## 0. 对我自己上一篇文档的更正

`p0-mr-90-attribution.md` 陈述的差值为 **+9 questions = +7.44 pp**。那个
数字是错的。从同样的文件重算：

| 量 | 值 |
|---|---|
| 面板期望准确率（121 道 MR 问题，8 次运行） | 79.13 % |
| 运行 34791592602 | 90.08 % (109/121) |
| **差值** | **+10.95 pp = +13.25 question-units** |

早先的数字使用了多数投票式面板分类，并丢弃了翻转表四个单元格中的两个，
因此它既对不上总量也对不上自身。能对上的四单元格分解：

| 单元格 | n | question-units |
|---|---|---|
| gained (panel ≤4/8 → correct) | 18 | +12.75 |
| held (panel ≥5/8 → correct) | 91 | +3.25 |
| lost (panel ≥5/8 → wrong) | 2 | −2.00 |
| never (panel ≤4/8 → wrong) | 10 | −0.75 |
| **总计** | **121** | **+13.25** ✓ |

---

## 1. 混杂因素，以及它为何不能解释这一跳升

三个引擎提交（`c4ab77b`、`f35c4a4`、`236ab1b`，2026-09-13）和一个评分器
提交（`cce134e`，2026-09-12）都在面板之后落地。评分器改动和引擎改动产生**相同的可观测量**——一道问题
从错翻转为对——因此总量无法将它们分开。

`cce134e` 改了两件事，而其中只有两件可从 MR 路径到达：

1. **判官模板分派。** 全部 121 道 MR 问题都是 `multi-session`，路由到
   `defaultTemplate`。因此 `temporal-reasoning` 的差一容差和
   `knowledge-update` 子句**永不触及 MR**。唯一相关的改动是"包含标准答案**或**携带全部中间步骤"
   取代了单纯的"语义等价"。
2. **数值前置门延迟裁决。** 以前，`numericAnswerVerdict` 将预测与
   标准答案的*首位*数字比较，并直接返回 `p === e`。一个陈述了两个可接受值的标准答案会被拒绝，从未
   到达判官。现在这样的标准答案延迟交给判官。

按问题而非按总量将它们分开，方式是重放
**`cce134e` 之前**的评分器对照新运行的答案字符串：

| 类别 | 判据 | 问题数 | question-units |
|---|---|---|---|
| `GATE` | 旧的数值门本身就会返回 `true` —— 完全可判定 | 12 | 8.13 |
| `IDENT` | `normalizeAnswer(answer) === normalizeAnswer(gold)` —— 任何等价或包含式判官都会在相同字符串上同意 | 5 | 4.13 |
| `JUDGE` | 二者均不成立；旧判决是一次判官调用，**无法在本地解决** | 1 | 0.50 |

**来自多值数值延迟裁决的评分器贡献：正好为 0。** 没有任何 gained 问题具有多值标准答案、且其答案匹配
非首位值。特别是 `3fdac837`——正是 `cce134e` 提交信息中引用的那个案例，标准答案为
`"11 days (or 12 days, if April 15th to 22nd is considered as 8 days)"`——
现在回答 `"11 days"`，匹配*首位*值，因此**旧的**门也会放过它。它是引擎增益，不是评分器增益。

将同样的检验扩展到 91 道 `held` 问题（它们本就大多答对，因此更宽松的评分器原则上可能拥有它们的
余量），又增加 10 道 `JUDGE` 分类的问题，价值 0.88 units。

> **界限。** 在 16.00 question-units 的毛增益中，至多 **1.38 units
> (8.6 %, ≤ 1.14 pp)** 可归因于评分器。至少 **14.62 units
> (+12.08 pp)** 可归因于引擎。**90.08 % 是真实的。**

唯一一道 `JUDGE` 分类的增益是 `gpt4_ab202e7f`（标准答案 `"I replaced or fixed
five items: the kitchen faucet, the kitchen mat, the toaster…"`，答案 `"5"`）。
其旧判决无法在不运行判官的情况下确定，而该沙箱中不存在 API 密钥，因此它被留作界限而非主张。

---

## 2. 那两处回退明确无疑是引擎造成的

在*更宽松*评分器下的回退不可能是评分伪影，因此 `6d550036`
和 `d851d5ba`（在整个面板上均为 8/8 正确，如今均错误）是没有混杂的
引擎回退。

**`d851d5ba`** —— *"How much money did I raise for charity in total?"*
标准答案 `$3,750`，答案 `$8,750`。差值恰为 `$5,000`，来自一个**不**在 `answer_session_ids` 中的
会话：

> "I actually helped organize a music benefit concert at the Independent back in
> April … and raised **over $5,000** for the local music education program."

有两件事是错的。该证据是数据集排除的一个干扰项，**而且**
它是带对冲的："**over** $5,000"是一个下界，因此 `$3,750 + over $5,000 =
$8,750` 断言了证据并不支持的精确性。该对冲是一个与数据集无关、数学上可辩护的信号；而范围决策（"一场
音乐教育义演算是慈善吗？"）不是。

**`6d550036`** —— *"How many projects have I led or am currently leading?"*
标准答案 `2`，答案 `3`。检索到的上下文携带了 18 处"project"提及，横跨
干扰会话，其中包括

> "…from my Marketing Research class project, where I **led** the data analysis
> team…"

它字面上匹配了问题的动作动词。没有干净的信号能把它与两个标准答案项分开。这一例是
语义边界失败，不是 bug。

检索长度在 `6d550036` 上从 16,587 → 17,727 字符增长，在
`d851d5ba` 上从 16,749 → 16,982，与词汇桥（`c4ab77b`）拉入更多
上下文、因而更多干扰项一致。16.00 units 的毛增益对照 2.00
units 的毛损失，说明这桩交易强烈为正——但损失机制
是真实的，值得一个防护。

---

## 3. 其余 74 个失败实际上在哪里

要点：IE 96.00 % (150)，MR 90.08 % (121)，KU 79.17 % (72)，
TR 70.87 % (127)，ABS 86.67 % (30)；整体 **85.20 %**，74 道问题答错。

### 3.1 检索不是瓶颈

严格成员资格检验（一道被标注的答案轮的文本是否出现在
`retrieved` 字符串中；对每一轮跨轮采样 30 字符 shingle，以使轮中截断不会造成假阴性）：

| | NONE | SOME | ALL |
|---|---|---|---|
| 失败 | **2** | 6 | **66** |

74 个失败中只有 **2 个**是真正的召回失败（均为 IE）。**66 个的每一个被标注答案会话的文本都在提示词中，
却仍然答错。** TR 有 **零**个召回失败：其 37 个失败中有 33 个拥有完整证据。

任何增加检索广度的迭代都在攻击 2 道问题。

### 3.2 拒绝才是瓶颈，而修复的范围划得太窄

| 能力 | n | 弃权 | 弃权率 | 错误弃权 | 占该能力失败的比例 |
|---|---|---|---|---|---|
| IE | 150 | 4 | 2.67 % | 4 | 67 % |
| **MR** | 121 | 2 | **1.65 %** | 2 | 17 % |
| KU | 72 | 0 | 0.00 % | 0 | 0 % |
| **TR** | 127 | 15 | **11.81 %** | 15 | **41 %** |
| ABS | 30 | 26 | 86.67 % | 0 | 0 % |

`236ab1b`——"强制 MR 弃权契约，而不是信任提示词"——把 MR 带到 **1.65 %**。TR 处于 **11.81 %**，高 7.2×，
且是唯一一个仍然大规模拒绝的非弃权能力。

在 21 个错误弃权中，**20 个的提示词中带有被标注的证据。** 那是全部 74 个失败中可通过一个机制
到达的 27 %，而 20 个中的 15 个是 TR。

### 3.3 TR 弃权在要求什么

| 机制 | n | 准确率 | 失败 | 弃权 |
|---|---|---|---|---|
| (A) 相对时间锚（"last Saturday"，"10 days ago"） | 18 | **38.89 %** | 11 | 7 |
| (B) 排序 / 序列（"order of the N … earliest to latest"） | 7 | **14.29 %** | 6 | 2 |
| (C) 经过时间算术（"how many days between X and Y"） | 36 | 72.22 % | 10 | 4 |
| 余项 | 103 | 79.61 % | 21 | 7 |

(A) 比余项率低 41 pp。(B) 是最差的绝对率，但 n=7。
(C) **不是**一个独立的弱点——72.22 % 对照 70.33 % 的余项——因此不值得一个专门的机制。

TR 弃权由相对时间锚主导：*"I received a piece of jewelry last Saturday from whom?"*、*"What kitchen appliance did I buy 10 days
ago?"*、*"What was the significant business milestone I mentioned four weeks
ago?"*。检索文本中没有任何内容包含短语"last Saturday"；
绝对日期必须先从 `question_date` 推导。这与 `2c2c635`（"add time-window annotation and deterministic-coverage arms for
TR"）和 `p4-timewindow-plan.md` 所瞄准的是同一个问题，而它仍然悬而未决。

---

## 4. 推荐的下一迭代

**把弃权契约从 MR 移植到 TR，并给 TR 与 MR 已有的相同的先枚举后审计形态。**

两个具体改动，按此顺序：

1. **确定性相对时间锚。** 在检索*之前*把"last Saturday" / "N days ago"
   / "N weeks ago" 对照 `question_date` 解析为绝对日期，并要求 TR 路径考虑携带该日期的
   会话。这是纯日期算术——它不需要 LLM，且完全可单元测试。
   目标机制 (A)：18 道问题，38.89 %。
2. **把弃权契约扩展到 TR。** `236ab1b` 使没有推导尝试的裸 `UNANSWERABLE`
   在 MR 上无效。对 TR 施加同样的契约：TR 拒绝必须展示它所解析的锚
   和它考虑过的日期。目标 15 个错误弃权，全部证据在案。

明确**不**在此迭代中：检索广度（攻击 2 道问题），
以及机制 (C)（无可度量的弱点）。

### 验收标准

| # | 标准 | 测量 |
|---|---|---|
| 1 | TR 弃权率从 11.81 % 降至 MR 1.65 % 的 2× 以内 | 在同样的 127 道问题上 ≤ 3.3 % |
| 2 | TR 准确率上升 | 主要终点；用 Wilson CI 报告 |
| 3 | 无 MR 回退 | MR 不得跌破 90.08 % − 1 σ；两处已知回退（`6d550036`、`d851d5ba`）单独追踪 |
| 4 | 整体准确率上升 | ≥ 85.20 % |
| 5 | 增益不是评分伪影 | 重跑 §1 的分类：报告 `GATE` + `IDENT` 份额，`JUDGE` 份额 ≤ 1.14 pp |
| 6 | 每个维度覆盖率 ≥ 95 % | statements / branch / functions / lines，`pnpm check` |
| 7 | 锚解析器是确定性的 | 对星期名、"N days/weeks/months ago"、月边界和年边界的表驱动测试——无 LLM、无网络 |
| 8 | 阴性对照 | 一个禁用解析器的中性化版本必须使标准 1–2 失败 |

### 测试计划（TDD，在实现之前编写）

- `describe('relative time anchor')` —— 约 14 个表驱动案例：每个星期名，
  "last/this/past"前缀，`N days|weeks|months|years ago`，`yesterday`，
  `a couple of days ago`，月和年翻转，以及有歧义的
  "last weekend"。每一个都断言一个绝对 `YYYY/MM/DD`。
- 属性测试：对数据集中每一道携带相对短语的 TR 问题，
  解析器必须产生一个存在于该问题 `haystack_dates` 中的日期。这是真实有效性门——若
  解析器在抽象层面正确、在本数据集上无用，它就会失败。
- `describe('TR abstention contract')` —— 现有的 MR 契约测试，镜像过来：
  裸 token 被拒绝，带已解析锚和已考虑日期的 token 被接受。
- `d851d5ba` 的回退夹具：一个带对冲的数量（"over $5,000"）不得被
  求和进一个精确总数。将其范围定为**单独的**后续项；它是 1
  道问题，不得被捆绑进 TR 迭代，否则两个效应
  会变得无法归因。

---

## 5. 已知但未处置

- `gpt4_4fc4f797`：标准答案 `"38 days. 39 days (including the last day)"`，答案
  `"37 days"`。标准答案有两个值，因此门延迟交给判官，而
  `temporal-reasoning` 模板明确说不惩罚差一——
  37 对 38 差一。判官说了不。1 道问题；接线
  （`toJudgeQuestionType`）已检查且正确，因此这是判官行为，
  不是分派 bug。
- `gpt4_ab202e7f` 是唯一一个归因真正悬而未决的增益。
- `6d550036` 仍未解决：一个字面上匹配问题动作
  动词的干扰项。未找到有原则的信号。
