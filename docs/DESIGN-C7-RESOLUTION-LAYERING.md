# 设计：`C7` 分辨率分层（同一宽度内更高的证据密度）

> 状态：**设计完成，未实现**。判据已在 `03-execution-plan.md` §14.133.2 登记（六条）；
> 本文件只补它缺的那一半——**怎么实现**，以及实现必须落在哪些目录、由谁依赖谁、哪些测试先写。

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
