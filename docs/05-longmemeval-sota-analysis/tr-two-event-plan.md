# 迭代 #145 — 双事件时间题测量了错误的参照

## 0. 结论先行

确定性时间引擎对点名了第二个事件的 `relative` 题回答 **0/6**，而对只点名一个事件的题回答 **18/19**。原因是一行硬编码：对于 `kind === 'relative'`，引擎总是测量
`elapsed(events[0].date → questionDate)`。形如 *“How many days had
passed since I started ukulele lessons **when** I took my guitar to the tech?”* 的题要求
`elapsed(A → B)`，因此引擎返回 `elapsed(A → questionDate)` — 结果为 59，而金标是 24，且**在全部 4 次运行中完全相同**，因为该计算是确定性的。

修复方案是把这些题路由到引擎已有的区间计算。受影响的总体恰好就是当前得 0/4 的那 6 道题，因此**在它们内部不可能产生回归**。预期：**+5/127 TR（+3.9pp），+5/500 总体（+1.0pp）**。

本迭代取代 #144，后者的前提已被证伪 — 见 §1。

---

## 1. 为何 #144（确定性 MR 条目计数）被取消

是测量得出的，而非论证得出的。所有数字来自 `ab_turn/` 中的 4+4 同瞬 A/B，treatment
实验臂（121 道 MR 题 × 4 次运行）。

| #144 的主张 | 证据 | 判决 |
|---|---|---|
| “16 道错误计数题中有 8 道在 Step 1 列出了 ≥ 金标条目数，随后给出更低的答案” | 脚本在补全内容中**任意位置**搜索第一个 `Answer: <n>`。`parseAggregationAnswer` 只接受**行锚定的**标签，因此两者在 **213/484 条记录（44%）** 上不一致。用生产解析器更正后：**15 道中有 6 道**，即 **5 道真实题目**。 | **产物** |
| “Step 2 重新推导列表并丢弃条目 → 应在代码中计数” | 在全部 5 道中，排除判决都写在 **Step 1 的条目**里：`Forbes \| canceled \| (not current)`、`(same event as above, counted once)`、一条明确的“dry cleaning is not a store”论证。逐条目的 `included` 判决会携带同样的判决并返回同样错误的数字。 | **错误机制** |
| P0：把 `how many years older` 路由到推导提示（2 道题） | “grandma” 金标=43 需要 grandma 75 **以及用户的年龄**；上下文只说了*“still getting used to being in my 30s”*。“graduated from college” 金标=7 需要当前年龄；该会话**未被检索到**。两者都是**操作数缺失**，而非提示不匹配。 | **价值为 0** |
| “弃权是由庞大嘈杂的上下文驱动的” | 纯 `UNANSWERABLE` 率：短半段为 6.2%，长半段为 10.0%；上下文中位数 17,029 字符（纯弃权）vs 16,451（已作答）。 | **被证伪** |
| “干扰项负载限制了准确率” | 正确题 vs 错误题：13 vs 13 个会话，11 vs 11 个干扰项，15,902 vs 15,797 字符。无法区分。 | **被证伪** |

**已采取的行动：** 为 #144 编写的 P0 和 P1 代码已被 **回退**（`git checkout`），
因此没有任何零收益的变更进入 `master`。分析脚本予以保留。

---

## 2. 剩余错误实际在哪里

`treatment` 实验臂，4 次运行，500 道题：

| 能力 | n | 准确率 | 错误答案数 |
|---|---|---|---|
| ABS | 30 | 100.0% | 0 |
| IE | 150 | 95.2% | 7 |
| KU | 72 | 75.7% | 17 |
| **MR** | 121 | 74.6% | 31 |
| **TR** | 127 | **71.1%** | **37** |
| 总体 | 500 | 81.6% | 92 |

TR 是最弱的能力**且**是最大的错误池。它还从不弃权，因此其 37 个错误中的每一个都是自信的错误答案 — 而这恰恰是确定性引擎本应胜出的情形。

按引擎自身的分类法对 TR 拆分（`tr_error_analysis.py`，用**已发布**的 `classifyTemporalQuestion` 分类，而非重新实现）：

| kind | n | 准确率 | 稳定错误 |
|---|---|---|---|
| relative | 25 | 72.0% | 6 |
| interval | 26 | 84.6% | 3 |
| ordering | 40 | 97.5% | 1 |
| eventLookup | 20 | 75.0% | 2 |
| other | 16 | 68.8% | 5 |

## 3. 机制

`temporal-engine.ts`，`computeTemporalAnswer`：

```ts
case 'relative': {
  const reference = normalizeDate(questionDate);          // <-- always the question date
  const value = elapsedValue(normalized[0]!.date, reference, relativeUnit(question));
  return String(value);
}
case 'interval': {
  if (normalized.length < 2) return null;
  return String(intervalValue(normalized[0]!.date, normalized[1]!.date, relativeUnit(question)));
}
```

`interval` **已经**计算了双事件题所需要的正是那个量。`relative` 从不考虑第二个事件，并且总是取 `normalized[0]` — 因此答案取决于 LLM 恰好列出事件的顺序。

证明这一点的拆分（`tr_two_event.py`）：

| 子集 | n | 准确率 | 稳定错误（4/4） |
|---|---|---|---|
| `relative`，无第二事件 | 19 | **94.7%** | 0 |
| `relative`，点名第二事件（`when`） | 6 | **0.0%** | **6** |
| `interval` + `ordering`（引擎对照） | 66 | 92.4% | 4 |

佐证区间读法才是本意：`interval` 桶正确地回答了同样的 *“How long had I been X when Y?”* 构造（5 道中 4 道正确），因为它同时使用了两个事件。

## 4. 修复方案（P0）

在 `computeTemporalAnswer` 中，当一道 `relative` 题点名了第二个事件**并且**至少抽取到两个事件时，计算**两个事件之间**经过的时间，而非从第一个事件到问题日期：

- 新增一个导出的谓词，例如 `hasSecondEventReference(question)` — 一个引入事件的 `when` 分句（`when I …`、`when the …`），对全部 25 道 `relative` 题进行测试，从而那 19 道单事件题可被证明未受影响；
- `relative` + 第二事件 + ≥2 个事件 → `intervalValue(events[0], events[1], unit)`；
- `relative` + 第二事件 + <2 个事件 → 返回 `null`，从而回退到 LLM 时间提示，而不是输出一个在构造上就错误的数字；
- 单位选择不变（`relativeUnit`，已有单元测试）。

**有意排除在范围之外：** 两道 `other` 桶的题
（*“How many weeks have I been taking sculpting classes when I invested in …”*，金标 3 vs 6；
*“How old was I when I moved to the United States”*，金标 27 vs 弃权）。它们是一处分类器覆盖漏洞，属于不同机制，而且该构造触及的题目中有一道当前是**正确的** — 因此把它们并入会牺牲这次 A/B 的干净归因。它们将有自己的迭代。

## 5. 测试计划（TDD，离线，无 LLM，无网络）

`computeTemporalAnswer` 是纯函数，因此每个生产失败都可以作为单元测试重放。两个事件日期是**精确重建**的，依据是观测到的错误答案与金标（`tr_reconstruct_fixtures.py`）：

> `answer = elapsed(A → questionDate)` ⇒ `A = questionDate − answer`
> `gold = elapsed(A → B)` ⇒ `B = A + gold`

| 题目（片段） | qdate | A | B | 观测值 | 金标 | B ≤ qdate |
|---|---|---|---|---|---|---|
| finished reading 'Evelyn Hugo' | 2023/02/10 | 2022/12/28 | 2023/01/15 | 44 | 18 | 是 |
| started ukulele lessons | 2023/04/01 | 2023/02/01 | 2023/02/25 | 59 | 24 | 是 |
| recovered from the flu (weeks) | 2023/10/15 | 2023/01/22 | 2023/05/07 | 38 | 15 | 是 |
| launched my website | 2023/03/25 | 2023/03/01 | 2023/03/20 | 24 | 19 | 是 |
| bought Adidas running shoes | 2023/02/03 | 2023/01/10 | 2023/01/24 | 24 | 14 | 是 |
| attended a baking class | 2022/04/15 | 2022/04/10 | 2022/05/01 | 5 | 21 | **否** |

第五列是自检：`B` 必须落在问题日期当天或之前。6 道中 5 道成立。唯一的失败是一个**不同的子缺陷** — 那里的 `when` 分句标识的是头事件，而引擎却选了修饰事件，因此金标是
`elapsed(baking class → questionDate) = 21`，而引擎使用了蛋糕日期（5）。
区间路由会让它以不同的量级出错；它不可能使其回归（当前 0/4）。

测试义务：

1. **先红** — 5 个测试逐字复现 5 个生产失败（题目文本、问题日期、两个事件），断言**金标**数字，在修复前编写并确认失败。
2. **回归护栏** — 对 19 道单事件 `relative` 题中的每一道，行为逐位相同：一个表驱动测试断言仍然返回 `elapsed(A → questionDate)`。同时断言当只抽取到一个事件时**不**走双事件路径（`computeTemporalAnswer` 返回 `null`）。
3. **单元覆盖** — 天 / 周 / 月，以及两种事件顺序（修复必须与顺序无关，因为 LLM 的列出顺序无保证）。
4. **每一个**维度（语句 / 分支 / 函数 / 行）覆盖率 ≥ 95%，并且 `pnpm check`（lint、typecheck、test、format）加 `pnpm build` 全绿。

## 6. 基准的验收标准

同瞬 4+4 A/B，全部 500 道题，`temperature=0`：

- **主要（确定性）**：6 道双事件 `relative` 题从 **0/6** 到 **≥5/6**。该端点**无采样方差** — 计算是确定性的，且全部 6 道当前稳定地错，因此每个实验臂跑一次即可精确测量它。
- **次要**：TR 准确率和总体准确率，以带噪声底噪的描述性估计形式报告，并附 4 次运行置换检验。
- **护栏（全部必须通过）**。阈值是**校准过的**，而非零 — 见 §6.1。“0 回归” 落在基准自身噪声底噪以下，会否决一个什么都没改变的修复。
  1. 19 道单事件 `relative` 题上 ≤1 个回归（当前 18/19）；
  2. `interval` 上 ≤0 个回归，`ordering` 上 ≤3 个（当前 61/66）；
  3. TR 之外的任何能力都不得超出其自身的运行间波动 —
     IE / MR / KU / ABS；
  4. TR 弃权率不得上升。

### 6.1 噪声底噪校准，在读取 treatment 之前测得

`ab_turn` 是一个**时间零假设**：其 control（`183a3cc`）与 treatment
（`db92e62`）仅在 MR 轮次召回通道上不同，而 `temporal-engine.ts` 和 `temporal.ts`
在两个引用之间逐字节相同
（`git diff 183a3cc db92e62 -- packages/cortex-eval/src/temporal-engine.ts`
无任何输出）。因此它的全部 8 次运行共享同一条时间代码路径，所以将它们**任意**拆成 4 vs 4 都是有效的零假设比较 — 共计 35 种不同拆分。

`tr_guard_noise_floor.py` 枚举全部 35 种拆分，并报告当实际上什么都没有改变时每个护栏产生的最大回归数：

| 组                  |   n | 零假设最大损失 | 零假设 p95 | 零假设最大绝对差 |
|------------------------|-----|-----------------|----------|--------------------|
| **双事件 relative** | **6** | **0**        | **0**    | **0**              |
| 单事件 relative  |  19 | 1               | 1        | 1                  |
| interval               |  26 | 0               | 0        | 1                  |
| ordering               |  40 | **3**           | 3        | 3                  |
| other/eventLookup      |  36 | 1               | 1        | 2                  |

两个结论，二者都改变了上面的标准：

- **主要端点是无噪声的。** 在全部 35 种零假设拆分中，双事件桶从未移动，哪怕一道题也没有。这 6 道题中的每一道在一个实验臂的全部 4 次运行上都返回相同的字符串，因此多数投票桶是由算术而非投票决定的。因此 0/6 → 5/6 的变动在类别上**不是**采样噪声。
- **`ordering` 上的 “0 回归” 不可达成。** 一次零假设比较产生多达 3 个。原标准比基准的稳定程度更严苛，会否决一个什么都没改变的修复。它被放宽到测得零假设最大值。

这项校准是在 #145 A/B **被下载之前**于 `ab_turn` 上计算的，因此它不可能被调参去迎合它所用来评判的结果。

## 7. 本分析产出的脚本

| 脚本 | 用途 |
|---|---|
| `mr_filter_recheck.py` | 用**生产**答案解析器重跑 #144 的诊断 |
| `mr_error_census.py` | MR 错误普查：弃权 / 检索 / 枚举 / 过滤 |
| `mr_abstention_mechanism.py` | 检验纯弃权与上下文大小及证据密度的关系 |
| `mr_distractor_load.py` | 检验准确率与干扰项负载及证据占比的关系 |
| `mr_counting_scope.py` | 确定性条目计数的范围检查 |
| `tr_census.mjs` | 逐题 TR 普查，用**已发布**引擎分类 |
| `tr_error_analysis.py` | 按时间 kind 与错误形态划分的 TR 错误 |
| `tr_two_event.py` | 隔离该缺陷的双事件拆分 |
| `tr_other_bucket.py` | 列出引擎交还给提示的题目 |
| `tr_reconstruct_fixtures.py` | 从生产数据重建离线单元测试夹具 |
