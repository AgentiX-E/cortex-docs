# 设计：`C7` 分辨率分层（同一宽度内更高的证据密度）

> 状态：**已实现并接线，未派发**（第 134 轮）。判据在 `PREREGISTRATION-RESOLUTION-LAYERING.md`（F1–F5，
> 写在派发之前）。本文件保留为**设计记录**，并在 §11 记录实现与设计的三处偏差——偏差不改判据，
> 但必须写在读数之前，否则读数出来时就没有人分得清哪个是设计、哪个是事后解释。

---

## 1. 它要修的是哪一个数

`C1` 要求每题 prompt token ≤ **6,000**，现状 **7,448**（`S16`），差 **19.5%**。两条已被量过的路：

| 路线 | 账单 | 准确率代价 | 出处 |
| --- | ---: | --- | --- |
| 房间表（48,460 / 24,000） | 9,168 → **7,448**（−18.8%） | **−1.15 点**（题级 −1，p = 1.0） | `44017278305` |
| 宽度计划 `coverage=0.9` | **5,660**（−27.1%，已低于 6,000） | **−4.00 点**（`MR` −10.34 / `TR` −14.29） | `43259830582`（200 题） |

兑换率 **−1 点 / 6.8% 账单**。`C1` 的 22.7% 按直线定价是 −3.3 点，而实测 −4.00 更贵——因为宽度计划的
切法会**切掉事件**。`C7` 的目标不是更省，而是**同样字符里装下更多事件**，从而把 −4.00 点收回一半以上。

**骨架不可压**：产品入口组装一条提示实测 **27,268 字符，其中指令 207（0.76%）**，与 `width.ts` 记录的
**3.0%** 同向。19.5% 不在那里。

---

## 2. 严格单变量：只换渲染器，不换选择器

这是 §14.133.2 第 1 条，也是本设计最容易做错的地方。**选择算法一行不改。**

`chooseEvidence` → `selectByRelevance` 的规则是「**最大的、渲染后仍放得进 room 的前缀**」（二分搜索，
`render` 单调）。若每条 turn 的渲染变短，同一个 room 就装下更多轮——**前缀自然变长，`turnsKept` 自然上升**。
这就是「密度」，不需要贪心、不需要跳过、不需要第二个变量。

> **反例（不要这样做）**：装不下就跳过、继续装更小的 turn。那是 `session-fill` 的二阶版本，会把交付集合
> 从「前缀」改成「子集」，于是读数无法区分「密度」与「换了选择器」。

**「只动渲染器」的边界要划清楚**：每条轮次多长（`maxTurnChars` 的 400）**属于渲染器**，所以分层模式可以
替代它（§3.1）；**房间**（48,460 / 24,000）与**前缀搜索**不属于渲染器，一行不动。这条边界是
§14.133.2 第 1 条可判的原因——同一个 room、同一个前缀规则，只有「一条轮次变成什么文本」不同。

宽度的可比性因此是**构造保证**的：两条臂用同一个 room、同一个前缀搜索，只有 `render` 不同。
第 2 条「每题 `promptChars` 相差 ≤2%」不是靠测量对齐，而是靠「两边都填到同一个 room」成立——
读数只需验证它，不需要修它。

---

## 3. 三种形态，全部确定性

| 形态 | 何时 | 文本 | 上限 |
| --- | --- | --- | --- |
| `raw` | 轮次字符 ≤ `rawCap` | 原文（现状路径） | `rawCap` = 已注册的 `maxTurnChars`（400） |
| `excerpt` | 长轮且与问题**有**词汇重叠 | `excerptAround` 的匹配窗口（词边界 + `…` 标记） | `excerptChars`（600） |
| `record` | 长轮且与问题**无**词汇重叠 | 首句 + 含数字的句子拼接，单行 | `recordChars`（240） |

三个决定与三条理由：

1. **短轮不摘**。400 字符以下的一轮已经是密度的上限，摘它只会丢内容。所以 `rawCap` = 已注册的
   `maxTurnChars`，不引入新数。
2. **有重叠才摘**。摘录的价值来自「哪一句与问题相关」，而这个判断只能来自词汇重叠——`lexicalRelevance`
   已经在流水线里，`excerptAround` 已经在 `excerpt.ts` 里。没有重叠的长轮摘不出东西，所以走 `record`。
3. **`record` 不调模型**。一个会调 LLM 的 `record` 会把成本轴变成成本上升轴，且引入逐题非确定性。
   它只做一件事：**把一轮压成一行事实**（首句 + 数值句），代价是丢失语境——这正是要测的东西。

**切点永不落在词中间**（`excerptAround` 已保证，`a4996e51` 的教训）。`record` 的「首句 + 数值句」
按句读符切分，切不出句子时退化为 `excerpt`。

### 3.1 这一节有一个必须先说的矛盾：`excerptChars` 比 `rawCap` 大

`600 > 400` 看起来自相矛盾——摘录怎么会比原文上限还长？答案是**分层模式替代 `maxTurnChars`，不是叠加**：

- 现状（`raw`）：注册臂在 `multi-session` / `temporal` 上把每一轮截到 **400**，不论长短。
- 分层（`layered`）：`maxTurnChars` **不生效**，由形态决定长度——短轮 `raw`（≤400）、
  有匹配的长轮 `excerpt`（≤600）、无匹配的长轮 `record`（≤240）。

密度不是「每条都更短」，而是**平均长度下降**：绝大多数长轮走 `record`（240），省下的字符让前缀
多装若干轮；少数真正匹配的轮次反而**多拿 200**（600 对 400）。这是一次**重新分配**，不是一次压缩。

> **这条如果写反了，整个读数作废**：把 layered 叠在 `maxTurnChars=400` 之上，`excerpt` 的空间是 0，
> 机制退化成「把 400 变成 240」，读数会显示准确率下降而原因是「宽度缩了」——正是 §14.133.2 第 2 条
> 要防的那件事。

### 3.2 实现难点：形态决策必须只做一次，且预算与渲染共享它

`selectByRelevance` 用**渲染后的长度**做二分搜索（`render` 单调），而 `MAX_TURN_CHARS` 的长度估计走
另一条路（`#renderedChars`，喂给 `planEvidenceRoom`）。两条路若各算一次形态，就会出现
「预算以为是 240、渲染出 600」的分歧——那正是 `43259468403` 被取消的那一类缺陷（计划按原始长度
算预算，而渲染按 400 截断）。

所以实现的第一步不是写 `resolveTurn`，而是把形态决策**提升到 `buildPrompt` 里做一次**：

```ts
const forms = turns.map((turn) => resolveTurn(question, turn.content, options)); // 一次
const render = (picked: readonly AdmittedTurn[]) => picked.map((t) => forms[indexOf(t)].text).join(...);
// #renderedChars 用同一份 forms：forms.map((f) => f.chars)
```

不变量：**同一题、同一 run 内，`forms[i].chars` 与 `render([turns[i]]).length` 必须相等**（一条断言，
不是一条约定）。

---

## 4. 子包布局与依赖分层

```
packages/cortex-memory/src/
  resolution.ts            ← 新增：纯函数，零依赖（不 import prompt.ts / memory.ts）
  prompt.ts                ← 接线：chooseEvidence 的 render 参数
  types.ts                 ← 新增 CortexMemoryOptions.resolution?: ResolutionMode
  __tests__/resolution.test.ts
  __tests__/resolution-reach.test.ts

packages/cortex-eval/src/
  bench-memory-arm.ts      ← 读 CORTEX_MEMORY_RESOLUTION（variable，不是 input）+ 投影进 artifact
  arm-verdict.ts           ← 无改动（配对读数已存在）
  report.ts                ← 打印 resolution + 逐题的 form 分布

.github/workflows/benchmark-cortex-memory.yml   ← 转发 vars.CORTEX_MEMORY_RESOLUTION || 'raw'
tools/dispatch-cortex-memory-ab.py              ← 写入 + 声明 + 严格的域校验
tools/__tests__/test_resolution_wiring.py       ← 五环节，四条变异
```

依赖方向：

```
cortex-core  ←  cortex-memory (resolution.ts 只依赖 turn 的 string 与句读符)
cortex-eval  ←  cortex-memory/bench（devDep，已存在）
```

`resolution.ts` **不 import** `excerpt.ts` 之外的任何模块——`excerptAround` 是它的唯一依赖，
因为它已经拥有「句子边界不切断」这条性质，重写一遍就是两份实现。

### 4.1 纯函数签名

```ts
export type ResolutionMode = 'raw' | 'layered';
export type EvidenceForm = 'raw' | 'excerpt' | 'record';

export interface ResolutionPlan {
  readonly text: string;
  readonly form: EvidenceForm;
  readonly chars: number;
}

/** 一条轮次的渲染形态。纯函数：同输入同输出，不读时钟、不读环境。 */
export function resolveTurn(
  question: string,
  content: string,
  options: { rawCap: number; excerptChars: number; recordChars: number },
): ResolutionPlan;
```

**不变量**（每条都要有断言）：

| # | 不变量 | 为什么 |
| --- | --- | --- |
| I1 | `chars === text.length` 且 `chars <= 输入长度` | 密度只能是「更短」，不能更长 |
| I2 | `chars >= 1`（非空输入时） | 一条轮次不能渲染成空串——那会让前缀无界增长而 room 不动 |
| I3 | `mode === 'raw'` 时 `text === content`（截断后） | 关闭时必须**逐字节**等于现状 |
| I4 | `content.length <= rawCap` → `form === 'raw'` | 短轮不摘 |
| I5 | 词边界：`excerpt` 的切点落在词边界上并带 `…` 标记（`excerptAround` 的合同），`record` 的切点落在句读符上 | 切断词是 `a4996e51` 的失败；静默切是 `excerpt.ts` 整个文件存在的理由 |
| I6 | `forms[i].chars === render([turns[i]]).length`（§3.2） | 预算与渲染各算一次形态，就是 `43259468403` 被取消的那类缺陷 |

---

## 5. 接线（三处，都是既有 `render` 参数的下游）

1. **`prompt.ts`**：`buildSessionPrompt` / `buildPrompt` 构造 `plan.render` 时，若
   `options.resolution === 'layered'`，`render(picked)` = 对每条 `picked` 调 `resolveTurn` 再拼接。
   现状路径（`raw`）保持**逐字节不变**——由 I3 与一条产品路径测试共同保证。
2. **`types.ts`**：`resolution?: ResolutionMode`，**未命名即 `raw`**（与 `sessionClock` 同一条规则）。
3. **`assemble.ts`**：转发（不默认），与 `sessionClock` 同。

**为什么落在 `render` 而不是 `chooseEvidence`**：`render` 是唯一的「一条轮次怎么变成字符」的位置，
而选择器读的是 `render` 的长度。改 `render` 一处，选择和预算两侧**同时**获得密度；
改 `chooseEvidence` 则要复制一份预算算术。

---

## 6. 归因：产物必须携带三样东西

§14.133.2 第 4 条：`form`、`formChars`、`eventsFitted`，缺一不读分数。

| 字段 | 位置 | 内容 |
| --- | --- | --- |
| `resolution` | `memoryArmConfig` | `raw` / `layered`（每次运行一个值） |
| `evidenceForms` | artifact 的逐题记录 | `{ raw: n, excerpt: n, record: n }` |
| `formChars` | 同上 | 每种形态贡献的字符数 |
| `eventsFitted` | 同上 | 该题**交付的轮次数**（现有 `carried` 已可算出，但必须独立成字段，因为前缀增长是机制的**直接**后果） |

`eventsFitted` 是本机制唯一的「是否真的提高了密度」的证据：`promptChars` 不变而它不涨，
说明摘录只是把同样的东西写短了，没有多装事件。

---

## 7. 测试清单（先写测试，再实现）

| 文件 | 条数（目标） | 覆盖的维度 |
| --- | ---: | --- |
| `resolution.test.ts` | 20 | I1–I6 各 ≥2；形态三岔的边界（`rawCap`、`rawCap+1`）；无句读符；纯 Unicode；空问题；幂等 |
| `resolution-reach.test.ts` | 6 | 开关 off 时提示**逐字节**等于 `raw`；on 时 `promptChars` 与 off 相差 ≤2% 且 `turnsKept` 上升；六条路由里只有被命中的路由字节变化 |
| `test_resolution_wiring.py` | 8 | 五环节 + 半径式的「无新 input」断言 |

覆盖率目标：`resolution.ts` **四维 100%**（语句 / 分支 / 函数 / 行），与 `turn-clock.ts` 同档。

**变异检验（必须做，各只红一条）**：
1. 把 I4 的 `<=` 改成 `<` → 边界测试转红；
2. 把 `record` 的数值句过滤删掉 → 对应断言转红；
3. 把 `mode: 'raw'` 的短路删掉 → 逐字节测试转红。

---

## 8. 派发顺序与价格

| 步 | 内容 | 价格 | 判据 |
| --- | --- | ---: | --- |
| 1 | 200 题 × 2 重复，对照 = **B 臂**（`coverage=0.9` 的 5,660 / 86.50%） | **2.85 CNY** | 先读**假证**：`eventsFitted` 中位提升 < 20% → 这一族关闭，不跑第 2 步 |
| 2 | 全量 500 题 × 4 重复 | **14.26 CNY** | §14.133.2 六条 |

第 1 步为什么对着 B 而不是 A：B 已经把账单降到 5,660（低于 `C1` 的 6,000），所以 C 不需要再省，
只需要把 B 丢掉的 4 个点收回一半——`MR` ≥ +5 题、`TR` ≥ +7 题。这是一个比「涨点」弱得多、也现实得多的要求。

---

## 9. 风险，以及每条风险对应的否证形式

| 风险 | 概率判断的依据 | 否证形式 |
| --- | --- | --- |
| 摘录切断答案 | `a4996e51` 的句子被切在词中间 | I5 + 逐题 `form` 记录；若 `MR` 退步集中在 `excerpt` 轮次占比最高的题 → 摘录窗口太小，改窗口不是改机制 |
| `record` 丢掉计数所需的成员 | `MR` 的失败形态是「成员判定」而非「数错」（`PREREGISTRATION-SESSION-CLOCK.md` §1.1：34 道数字型错题里清单本身错的 31 道） | 若 `MR` 退步集中在 `record` 占比高的题 → 计数型问题的长轮必须保留 `raw`，这是形态选择的第二个轴，须重新登记 |
| 密度提升但没有事件增益 | 前缀增长是构造后果，可能只是「同样的轮次写得更短」 | 第 1 步的假证条款：`eventsFitted` 中位 < +20% → 关闭 |
| 与 `anchor-window` 混淆 | 两者都会改变交付集合 | 两条机制**不合并派发**；`anchor-window` 先读（run `44317789307`），`C7` 的对照是它自己那一次 |

---

## 10. 与 `anchor-window` 的关系（为什么不是二选一）

`anchor-window` 改的是**哪些轮次进入候选**（邻域恢复）；`C7` 改的是**同一批轮次占多少字符**。
两者都能提高 `eventsFitted`，但机制不同、可叠加、且必须分别计量——把两条放进一次派发，
`MR` 的移动就无法归因。

顺序上，`anchor-window` 先读是因为它已在跑；`C7` 的实现与它**并行**（0 CNY），派发排在它之后。

---

## 11. 实现与设计的四处偏差（写在读数之前）

### 11.1 两个上限是**比例**，不是两个常数

设计写 `excerptChars = 600`、`recordChars = 240`。实现写 `1.5 × rawCap` 与 `0.6 × rawCap`，
`rawCap` 就是运行已经注册的 `maxTurnChars`。

理由：一个在 benchmark 上调出来的常数会把 benchmark 编码进去，而「窗口需要在匹配两侧留出余地」
与「一行记录是一行，不是一段」是关于**形状**的陈述，在任何宽度下都成立。副作用是这条机制自动适配
它被派发到的宽度——如果将来注册臂从 400 改成 300，分层跟着变成 450 / 180，不需要第二次登记。

### 11.2 `record` 的第一句让位给操作数

设计说 `record` = 「首句 + 含数字的句子」，按阅读顺序填到上限。实现**先预留数字句、再用余下的空间
渲染首句**。

理由是读数逼出来的：一条 425 字符的轮次，首句 245 字符，按阅读顺序填会在首句里花光 240 的上限，
于是**唯一含数字的那句被丢掉**——记录保住了散文、丢了操作数，而这正是这个形态存在的反面
（`ANALYSIS-AGGREGATION-GAP.md` §1：差距是聚合题的算术，不是散文）。`resolution.test.ts` 用那条
425 字符的轮次钉住了「数字句必然存活」。

> 这是本设计里唯一一处「实现比设计更正确」的地方，记在这里而不是悄悄改掉。

### 11.3 `evidenceForms` 未投影

设计 §6 要求逐题 `form` / `formChars` / `eventsFitted`。实现做到的是：每条被缩短的轮次**自己**
在文本里带省略号（所以读者永远知道自己看到的是缩短后的轮次，不需要提示里加一句说明），以及
`roleCensus.total`（已有的交付轮次数，就是 `eventsFitted`）。

逐题的形态分布**没有**投影出来。这不是遗漏，是顺序：判据 F3 只读 `eventsFitted` 与 `promptChars`，
没有一条判据读形态分布，所以它的缺席不会让读数看起来更好或更差。下一轮补它——**在重新登记形态选择
的第二个轴之前**，因为那时它才是判据的一部分。

### 11.4 一个测试陷阱，值得写下来

`contentTerms('how many')` 返回 `['how','many']`，而一条讨论费用结构的轮次里有 "given **how** much
discussion"。于是「与问题无重叠」的夹具连续两次被判成 `excerpt`，密度断言读出的方向与机制相反。

**夹具必须以轮次为基准检查，不能以直觉为基准。** 这不是测试写错了一次，这是这类机制**所有**读数
的失效方式：解释「为什么这一题的提示变了」时，一个隐藏的词重叠会让归因整段错位。分层最终用的是
`sunflower height record` 这类与轮次毫无交集的短问题。

同一轮里这个陷阱又出现了第二次，形状不同：类级预算测试（`resolution-reach.test.ts`）的第一版夹具用
`'a'.repeat(400)` 当填充词，于是窗口的 span 在「放不下的那个 400 字符长词」处结束——`excerptAround`
返回 **15 字符**（`shoes packed 0…`），分层臂的 `evidenceChars` 读 **90** 对对照臂 **1200**，方向与
机制相反。**单个超长 token 会把窗口压成一句话的头部**；夹具必须用真实散文，否则测的不是形态，
是 `excerpt.ts` 对畸形输入的退化路径。两处陷阱合起来是同一句话：**夹具不是背景，它是被测机制的一部分。**

### 11.5 装配完成后那一次「保险裁切」被删除，因为它从未触发

第一版 `recordOf` 拼好一行之后还跑一次 `truncateCodePointSafe(line, room)`，必要时回退到词边界。它
在两份测试文件里 `recordOf` 被调用 **93 次**的过程中**一次都没有触发**。

原因不是运气：预留操作数时每条操作数各自付了自己的分隔符，首句前那个空格从首句的配额里扣掉，所以
`首句 + 分隔符 + 操作数` 的和**按构造** ≤ `room`——是恒等式，不是余量。于是这条裁切是一条不可达分支，
而不可达修复的代价不是多一行代码，而是那段算术**永远不会被测到**：它把越界吸收掉，将来真的越界也是
静默的。

裁切已删除，界限改在**能失败的地方**断言：`resolution.test.ts` 的 `I1` 现在是一次跨上限扫描
（7 / 12 / 25 / 60 / 137 / 400 × 5 条轮次 × 2 个问题），其中 60 那档正是「首句一点空间都不剩、
只能印操作数」的档位——删掉裁切之后，这一档的行为才第一次可测：`truncateAtWord` 拿到非正配额返回空串，
记录只剩 `380 pounds` 那一句加省略号。

覆盖率：`resolution.ts` 本轮结束时是 **100 / 100 / 100 / 100**（语句 / 分支 / 函数 / 行），与
`turn-clock.ts` 同一条线；改这一处之前是 **95.94 / 85.71 / 100 / 100**，那 4 个百分点的一半就是这条死分支。

---

## 12. 补上 `evidenceForms`，并因此抓到三个 census 缺陷

### 12.0 与 §11.3 的关系

§11.3 把 `evidenceForms` 的缺席写成**顺序**决定：没有判据读形态分布，所以它缺席不会让读数更好或更差，
「下一轮补它——在重新登记形态选择的第二个轴之前」。这一轮是那一轮。写下来之后，判据 `V1`
（三形态计数之和 = 交付轮次数）先红的是三个既有缺陷，而不是新字段。

### 12.1 缺陷一：平铺路由的 census 描述了一次没人读过的渲染

11 个外来轮次、`maxChars 1400`、`maxTurnChars 200` 下，探针读出：

```
carried 10 census {"cut":11,"marked":11,"whole":0,"forms":{... "record":{"turns":11,"chars":1243}}}
```

`wholeTurnsIn` 用 `plan.render` 做二分搜索以找「最长能装下的前缀」，而 `render` 每次都会重置并记账。
`fitToBudget` 交付的是 clip 后的字符串，不是任何一次 `render` 的结果，所以 census 停在最后一次探测上。

修法：把「记账」从 `render` 的副作用变成一个有对象的动作。

| 名字 | 语义 | 谁调用 |
| --- | --- | --- |
| `turnCensus().render` | 重置后渲染并记账，返回交付文本 | 各构建器的交付渲染 |
| `turnCensus().recount` | 重置后渲染并记账，**丢弃文本** | `fitToBudget` 在返回前对 `ordered` 调用 |
| `plan.tally` | 读数本体 | 由 `{...tally}` 快照发布 |

为什么不从 clip 的字符里数：那是**从文本里重新解析形态边界**，正是 `TurnWindowCensus` 被引入时
删掉的那件事，而且 clip 可能结束在轮次内部。

### 12.2 缺陷二：`MR` 与 `TR` 从来没有 census

`renderSessionBlocks` 渲染每个 session 块时调用 `formatEvidence`，但**没有把 tally 传下去**，
于是 `plan.tally === undefined`，`fitToBudget` 不发布 `turnWindow`。后果是：`multi-session` 与
`temporal` 两条路由 —— `C7` 存在的两条、`F3` 要读的两条 —— 既没有 `cut`/`marked`（`P1` 的分母），
也没有任何密度读数。

现在 `renderSessionBlocks` 接受可选 tally 并跨块累计，两个 session 构建器都接线，且 **fits 路径也发布**
（多 session prompt 通常低于房间上限，只在超预算分支发布会让这条路由大半没有读数）。

### 12.3 缺陷三：一个未覆盖的兜底

`buildSecondPassPrompt` 的 fits 路径发布 `turnWindow` 时带 `flat.length === 0 ? {} : {...}`，
覆盖率报出 `prompt.ts:4453` 未覆盖。按 §11.5 与上一轮的规矩，未覆盖的兜底要么删要么测——这里测，
因为它是真语义：空窗口不发布 census（三个零会读作「切了 0 个」而不是「没有窗口」）。

### 12.4 三形态投影的形状

```ts
type EvidenceForms = {
  readonly raw: { turns: number; chars: number };
  readonly excerpt: { turns: number; chars: number };
  readonly record: { turns: number; chars: number };
};
```

三条约束：

1. 形态由 `plan.form` 产生，不由 `elided` 推断：一个 `excerpt` 的窗口可能恰好覆盖整段文本，
   按「字节变没变」分类会记成 `raw`，而 `raw` 的 ceiling 对它不适用。
2. `chars` 是**交付长度**：`record` 装得下时短于 ceiling，`excerpt` 可以在文本末尾结束。
3. **缺席即无形态选择**：无 cap、head cut、superseded `collapse` 三种情形都不出现。

`cortex-eval` 侧只镜像字段（`DeliveredTurnWindowCensus.forms`），不镜像名字导出——两个子类型是
module-private，因为普查门禁在同一轮里把它们报成了孤儿。

### 12.5 判据

| # | 判据 | 检验 |
| --- | --- | --- |
| V1 | `raw + excerpt + record` 的 `turns` 之和 `=== cut + whole` | `resolution-forms.test.ts`（单题 + 11 题 × 4 个宽度） |
| V2 | 无 cap / head cut 时 `forms` 缺席 | 同上 |
| V3 | `collapse` 不计入任何形态 | 同上 |
| V4 | dateine 轮次记为 `record`，且 `chars` 含 head | 同上 |
| V5 | 空 session 列表不发布 census | 同上（`buildTallyPrompt`） |
| V6 | `forms` 穿过 capture 并写进 JSON | `benchmark-turn-window-capture.test.ts` |
| V7 | `bench/run.ts` 的失败日志含 `progress:` / `embedding:` / `retry:` | `bench-failure.test.ts`（`progress: null`） |

### 12.6 覆盖率

| 文件 | 语句 | 分支 | 函数 | 行 |
| --- | ---: | ---: | ---: | ---: |
| `prompt.ts` | 100 | **100**（原 99.74） | 100 | 100 |
| `resolution.ts` | 100 | 100 | 100 | 100 |
| `bench-failure.ts` | 100 | 100 | 100 | 100 |

### 12.7 下一轮读 `F3` 时，分母已经存在

`layered` 派发（200 题 × 2 假证，2.85 CNY）仍未发——embedding 余额仍然耗尽。但它现在会读到一个
**有分母**的比值：`forms` 逐题给出每种形态交付了多少轮、花了多少字符，`eventsFitted` 仍是
`roleCensus.total`，而 `cut`/`marked` 第一次在这两条路由上存在。如果 `F3` 通过而 `F4` 失败，
归因所需的形态分布已经在产物里，不必再派发一轮去补。
