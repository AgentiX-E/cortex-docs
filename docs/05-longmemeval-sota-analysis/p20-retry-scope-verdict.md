# P20 — 弃权重试在构造上就是惰性的：两处故障，单独看谁也看不见

迭代：提交 `a3a354e`。测量运行：`34915402976`。
此处每个数字的基线：运行 `34791592602`（2026-09-14，`limit=all`，
`runs=1`，`ablationRuns=1`，temperature 0）。

---

## 0. 我打算做什么，以及为什么我做了别的事

`p19-mr-90-verdict-and-tr-target.md` §4 推荐了一个分两部分的迭代：
构建一个确定性相对时间锚解析器，以及把 MR 弃权契约移植到 TR。阅读代码十分钟后我发现
**锚解析器已经存在**——`temporal-engine.ts` 中的
`resolveTimeRange`，带有一个专门的 `eventLookup` 分类，正好针对"what did I do two weeks
ago"这种形态，外加 `extendedTimeRange` / `extendedSecondEventReference` 精化，
而这些已经被消融过了。

所以第 1 条的前提是错的。我在写代码之前从数据重新推导了目标，建议随之改变。证伪它的
测量在 §1；它很廉价，值得为未来任何关于此路径的主张重复一遍。

P19 中存活下来的是第 2 条，而它结果比描述的要大。

---

## 1. 两个零成本测量重定向了这次迭代

**测量 A —— 锚解析器是否到达了那些失败的问题？**
对 18 道相对时间锚定的 TR 问题中的每一道，在 `DEFAULT_ENGINE_OPTIONS` 下和在 `EXTENDED_ENGINE_OPTIONS` 下解析时间窗口，然后问
该窗口是否包含某个被数据集标注为携带答案的会话的日期（`analysis/scripts/p0_anchor_reach.mjs`）：

| | 窗口包含证据 |
|---|---|
| DEFAULT (`extendedTimeRange: false`) | 18 中的 10 |
| EXTENDED (`extendedTimeRange: true`) | 18 中的 14 |
| 在 11 道 FAILING 问题中，DEFAULT | **6** |
| 在 11 道 FAILING 问题中，EXTENDED | **9** |

EXTENDED 到达了 4 道 DEFAULT 无法到达的问题（其中 3 道当前失败），因此该
精化是真实的。但 **11 个失败中的 9 个已经让证据位于窗口内**，所以窗口不是
让它们失败的原因。启用该标志至多是一个 2 道问题的改动，而且它影响的是检索而非仅
提示词，因此它不是安全的第一步。

*（消融同意，且这是从另一方向得到的同一结论：
`tr-extended-engine` 70.87 % 对 `tr-base-engine` 70.08 %——一道问题。那个
消融已经在运行里了，而我没有读到它。）*

**测量 B —— 证据究竟在提示词里吗？**
这才是决定这次迭代的那个。对每一个失败，检验一个被标注答案轮的
文本是否存活到了 `retrieved` 中，使用跨轮采样的 30 字符
shingle，以使轮中截断不能造成假阴性（`analysis/scripts/p0_recall_vs_decision.mjs`）：

| | NONE | SOME | ALL |
|---|---|---|---|
| 失败 (n=74) | **2** | 6 | **66** |

74 个失败中只有 2 个是检索失败，均为 IE。因此问题不在于到达证据。

集中之处在*拒绝*：

| 能力 | n | 弃权 | 率 | **错误** | 占该能力失败的比例 |
|---|---|---|---|---|---|
| IE | 150 | 4 | 2.67 % | 4 | 67 % |
| MR | 121 | 2 | 1.65 % | 2 | 17 % |
| KU | 72 | 0 | 0.00 % | 0 | 0 % |
| **TR** | 127 | 15 | **11.81 %** | **15** | **41 %** |
| ABS | 30 | 26 | 86.67 % | 0 | 0 % |

`236ab1b`（"enforce the MR abstention contract"）把 MR 带到 1.65 %。TR 处于
11.81 %，**高 7.2×**，而且 TR 不是唯一一个：IE 拒绝了 4 次并且这 4 次全错。21 次弃权发生在
弃权能力之外，**全部 21 次都错**。

而在那 21 次中，**20 次提示词里带着被标注的证据**——15 次 TR 中的每一次、两次 MR、4 次 IE 中的 3 次。

那些不是判决，也不是检索失败。它们是跳过，而引擎已经为此写好了一次有界的重问。
它没有到达它们中的任何一个。

---

## 2. 为什么重试没有到达它们中的任何一个：两处相互独立的故障

**故障 1 —— 范围。** `answerSessions`（多会话路径）计算了
`abstentionRetryEnabled` 并将它向下传递。其他每一个调用方——`answer`、
`answerTemporal`、`answerAssistant`、`answerKnowledgeUpdate`、`answerPreference`——
调用 `respondWith` 时不带该参数，而该参数默认为 `false`。

**故障 2 —— 检测器，而这是那个本会隐藏故障 1 修复的家伙。** `detectBareAbstention` 用该 token 检验原始响应：

```ts
return isAbstentionValue(raw.trim(), abstainToken);   // before
```

`isAbstentionValue` 是在剥离包裹引号后进行的一次精确、不区分大小写的比较。但 `parseQaAnswer` 不检验原始字符串——它先提取 `Answer:`
标签之后的值，然后检验*那个*：

```ts
const labelled = trimmed.match(/(?:^|\n)\s*(?:answer|final answer)\s*:\s*(.+?)\s*$/im);
const candidate = labelled ? labelled[1]!.trim() : trimNarration(...);
if (candidate === '' || isAbstentionValue(candidate, abstainToken)) return null;
```

提示词契约以 `Answer: <final answer>` 结尾。因此带标签的形式是一个**合规**模型会写出的形态，而两个谓词在它上面
分歧了：

| 字符串 | `detectBareAbstention`（旧） | `parseQaAnswer` |
|---|---|---|
| `UNANSWERABLE` | 裸 | 弃权 |
| `Answer: UNANSWERABLE` | **不是裸的** | 弃权 |

实测：在运行 34791592602 上恰有 **3 个不同的弃权字符串**，
而全部 19 个可恢复的都是 `Answer: UNANSWERABLE`，20 字符。
检测器恰恰对提示词所要求的那个拼法视而不见，因此它
把 3 个不同字符串中的 2 个分类为裸的，而流水线把这三个都当作
弃权。

**这两处故障不是顺序的——它们是相乘的。** 仅修复范围将什么都改变不了，因为在范围修复下带标签的形式仍然
不会匹配。这就是为什么二者单独都不能在 Δaccuracy 上显现，以及为什么每一个都必须被单独中性化以证明它确实起了
任何作用。

---

## 3. 修复

**检测器** —— 检验解析器会提取的那个值，而不是原始字符串：

```ts
export function detectBareAbstention(raw: string, abstainToken: string): boolean {
  const trimmed = raw.trim();
  if (trimmed === '') return false;
  return isAbstentionValue(soleLabelledValue(trimmed) ?? trimmed, abstainToken);
}
```

`soleLabelledValue` 锚定到整个响应（`^…$`），且有意**不**多行。一个 `Step 1` 账本后跟 `Answer: UNANSWERABLE` 是一个
有理有据的判决；多行匹配会越过推理，剥掉最后一行的
标签，然后重问它——正是裸/有理据区分存在所要防止的那种噪声。这由测试固定。

**范围** —— 默认值现在是"此路径服务于这一轮通过"，反转后使一条新的
回答路径会继承它，而不是悄悄地逃逸它：

```ts
abstentionRetry = true,   // was false
...
const retryEnabled = abstentionRetry && this.options.enableAbstentionRetry !== false;
```

三个后果，每一个都是刻意的：

- 调用方通过现有的 `enableAbstentionRetry`
  选项保留最终否决权，而该否决权现在对每一条路径都施加在 `respondWith` **内部**，
  而不是在某一个调用点。这对
  `runAbstentionRetryAblation` 是承重的，其对照组在它打算比较的每一条路径上都必须惰性。
- `answerSessions` 不再重复该选项；它只传递自己
  路径级的原因（一个自定义 `aggregationPrompt`，即 MR 消融，携带
  自己的弃权契约）。
- **弃权路径显式选择退出**（`false`）。在那里弃权*就是*
  答案：30 道 ABS 问题中有 26 道被正确拒绝，全部为裸
  形式，因此重问将会花费一次模型调用来把正确答案变成错误
  答案。这个例外正是该开关仍然存在的原因。

---

## 4. 验证

**21 个新测试，仓库中 908 个**，`pnpm check` 绿色（lint、typecheck、测试、
prettier）。

**三个中性化，每一个单独失败**——这部分才要紧，因为
故障 1 和故障 2 单独看都是不可见的：

| 中性化 | 它恢复了什么 | 失败的测试 |
|---|---|---|
| A | 检测器再次检验原始字符串 | **3** |
| B | 默认范围回到仅多会话 | **4** |
| C | 弃权路径不再选择退出 | **1** |

**对照本次运行自身输出的往返检验**
（`analysis/scripts/p19_roundtrip_abstentions.py`），而非对照我编写的夹具——这是本会抓住原始缺陷的
那道门：

```
distinct raw abstention strings: 3
    20 chars  'Answer: UNANSWERABLE'
   994 chars  'Step 1 — Enumerate every item … Answer: UNANSWERABLE'
    12 chars  'UNANSWERABLE'
2/3 classified as bare
NOT BARE: "Step 1 — Enumerate every item matching the question's EXACT action…"
```

两个不同的裸形式都被标记；那单个 994 字符的有理据弃权
仍被清除。判别在真实字符串上成立。

**我在那个往返的第一版草稿中自己发现的一个缺陷**：夹具的
`isExpansionPrompt` 只匹配 `Specific events:`，因此在普通 QA 路径上，
查询扩展调用消耗了一个排队的答案，对照组返回了 `'2'`，而它本应拒绝——一个夹具 bug，本会读作一次无法解释的
额外调用，而不是测试失败。每个扩展提示词都以一个
`Specific …:` 标记结尾，但措辞随路径不同（`items` / `activities` /
`events` / `facts to retrieve`），因此该辅助函数现在匹配整个家族。

**改动文件的覆盖率：Statements 100 / Branch 98.85 / Functions 100 /
Lines 100。**

---

## 5. 这应带来什么，以及诚实的天花板

19 个可恢复的弃权，分布为 TR 15 / IE 4 / MR 2。

| 若重试转化了 | 整体 | TR | IE |
|---|---|---|---|
| 0 | 85.20 % | 70.87 % | 96.00 % |
| 一半 (≈10) | 87.20 % | 74.80 % | 98.00 % |
| 全部 19 | 89.00 % | 82.68 % | 98.67 % |

**不要把那上面一行当作已到手。** 两个原因，均来自 `236ab1b` 自身的测量：
重试被限定为一次，而一个拒绝两次的模型会保留该弃权，
因此转化并非逐问题得到保证；且历史恢复率
是 11 道受影响问题中的 10 道，不是 11 道中的 11 道。中间一行才是诚实的
预期，而即便它也是一次预测。

有两个进一步的界限要向前携带：

- **单次运行无法把真实增益与运行间方差分开。** MR 的
  面板 stdev 在 8 次运行上是 3.77 道问题（3.12 pp）。重试对 TR 的效应
  未被度量，因此第一次读数是一个没有区间的点估计。
- **两处已知的 MR 回退未被此改动触及**（`6d550036`、
  `d851d5ba`），而 `d851d5ba` 的机制现在已被理解到足以命名：
  `$8,750 = $3,750 + $5,000`，其中 `$5,000` 来自一个未标注的
  干扰会话，其措辞是一个**对冲**（"raised **over** $5,000"）。把一个
  下界求和进一个精确总数，断言了证据并不携带的精确性。
  那是一个与数据集无关的信号，也是它自身迭代的候选——作为
  一个防护，而不是一条关于哪些慈善机构算数的规则。

---

## 6. 明确不在此迭代中

- **`extendedTimeRange` 提升**（§1）。到达 4 道问题，其中 3 道失败，
  但窗口在 11 个失败中的 9 个里已经包含证据，且该标志
  也会改变检索。值得在重试*之后*做，这样二者可分别
  归因。消融的 +0.79 pp 与测量 A 的"4 道新可达"在量级上
  不一致，提升之前应加以调和。
- **TR 排序问题**（7 道问题，14.29 % 准确率）——P19 中的机制 (B)，
  仍然真实、仍然未解释，而现在明显是一个*决策*失败而非
  检索失败。
- **`6d550036`** —— 干扰项"…Marketing Research class project, where I **led**
  the data analysis team…"字面上匹配问题的动作动词。未发现干净的
  信号；不是 bug。
- **`gpt4_4fc4f797`** —— 标准答案陈述 38/39 天，预测 37，
  `temporal-reasoning` 模板禁止惩罚差一，判官说了不。
  `toJudgeQuestionType` 接线已检查且正确，因此这是 1 道问题上的判官
  行为。
