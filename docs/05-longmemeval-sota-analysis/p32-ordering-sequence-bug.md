# P32 —— `formatOrdering` 对 "from earliest to latest" 只返回了一个条目（已修复），以及三个候选干预被离线证伪

**状态：** 一个 bug 已修复并交付（6 个测试，修复前 4 个被验证为红）；
三个进一步的候选以零 API 成本被证伪。

---

## 1. 该 bug

`formatOrdering`（`temporal-engine.ts`）在序列分支**之前**检验了近期性分支：

```ts
if (/\bmost recently\b|\blatest\b|\bnewest\b/i.test(question)) { … }   // fires first
if (/\border from first to last\b|\bwhat is the order\b|\bfirst, second\b/i.test(question)) { … }
```

近期性分支匹配**裸词** `latest`。一个要求完整排序列表的问题——*"from earliest to latest"*——包含那个词，因此
引擎返回了 `ordered[ordered.length - 1].name`，即单个最后事件，
而不是该序列。

确定性地复现，不涉及 LLM：

```
Q: What is the order of airlines I flew with from earliest to latest before today?
   events JetBlue 2023/01/05, Delta 2023/02/10, American Airlines 2023/03/20
   before: "American Airlines flight"
   after : "First, JetBlue flight, then Delta flight, and lastly American Airlines flight."
```

## 2. 该总体，在真实运行上测量

在 127 道 TR 问题中，7 道匹配近期性正则。在那 7 道中：

| 问题 | 也要求一个序列吗？ | 当前 |
|---|---|---|
| `gpt4_7f6b06db` "…three trips… from earliest to latest?" | 是 | **错** |
| `gpt4_7abb270c` "…six museums I visited from earliest to latest?" | 是 | **错** |
| `gpt4_e061b84f` "…three sports events… from earliest to latest?" | 是 | **错** |
| `gpt4_f420262c` "…order of airlines I flew with from earliest to latest…" | 是 | **错** |
| `gpt4_ec93e27f` "Which mode of transport did I use most recently, a bus or a train?" | 否 | 正确 |
| `gpt4_2f56ae70` "Which streaming service did I start using most recently?" | 否 | 正确 |
| `0db4c65d`（经过时间问题，未路由到 `formatOrdering`） | 否 | 错 |

**4 道受影响的问题全部错，而 2 道真正的近期性问题正确**
——一个异常干净的分割，这正是使它可安全修复而非一次抛硬币的原因。

运行中的失败特征与机制完全相符：
`gpt4_f420262c` 标准答案 `JetBlue, Delta, United, American Airlines`，得到
`American Airlines flight from LAX to JFK`——最后一项。

## 3. 修复

一个要求序列的问题绝不是一个"哪一个是最近的"问题，
即便它包含 *latest* 一词：在 "from earliest to latest" 中，该词
命名的是**列表的端点**，不是要返回的条目。

- `asksForSequence(question)` —— 现有的两个序列模式加上
  `earliest to latest` 和 `from first to last`。
- 序列分支在近期性分支**之前**被检验。
- 列表渲染器移入 `formatSequence`，因此两个调用方共享一个
  排序列表的表示。

**天花板：+4 道题（+0.8pp）。** 诚实的限定：四道中有三道
的标准答案是完整句子而非列表，因此转化取决于判官
接受 `First, X, then Y, and lastly Z.` 为等价。那是下一次
运行所度量的；+4 是天花板，不是预测。

## 4. 测试

向 `temporal-engine.test.ts` 添加六个：

- **修复前 4 个为红**，每个对应运行中受影响的一道问题，断言
  返回完整序列。验证失败信息为
  `expected 'American Airlines flight' to be 'First, JetBlue flight, …'`。
- **2 个无回退**：`most recently` 和 `most recently, a bus or a train`
  必须仍返回单个最新事件。二者在修复前后都为绿色——
  它们存在是为了阻止该修复被扩大到"永不返回最新
  条目"。

门：958 个测试绿色（cortex-eval 812）。覆盖率 99.88 stmts / 98.71 branch /
100 funcs / 99.88 lines；任何地方的最低 branch 数字为 97.26%。

---

## 5. 三个候选被离线证伪（未花运行）

记录，因为一次证伪是一个结果，且其中每一个本会花一个
完整基准周期来发现。

### 5.1 R5 —— 按词汇操作数定日的二元排序：**被证伪**

想法：对 "Which X happened first, A or B?"，两个候选在
问题中被命名，因此通过对检索上下文的词汇匹配为每一个定日并比较
日期。

在 5 道二元排序问题上测量（当前 0/5）：

- 每个案例都返回为**平局**——两个操作数解析到同一个轮
  日期。LongMemEval 把 45 轮塞到 4–5 个会话日期上，而两个操作数
  常常共现在一个轮中。
- 真实证据是**轮文本内部的相对散文**，不是轮
  前缀：`gpt4_76048e76` 的答案来自 *"in mid-February, I had to take it in
  for repairs"*，位于一个时间戳为 `2023/03/10` 的轮中。对轮前缀做日期算术
  看不到那一点。
- 对 `gpt4_385a5000` 和 `gpt4_5438fa52`，甚至没有一个轮同时包含两个
  操作数。

因此二元排序是一个**提取质量**问题，而不是一个
确定性词汇规则能解决的东西。

### 5.2 R7 —— eventLookup 窗口收窄：**被证伪，且本会有害**

P29 §6 提议丢弃窗口外的轮，使读者在
更少候选上判别。在全部 20 道 `eventLookup` 问题上用
`EXTENDED_ENGINE_OPTIONS` 测量：

| 结果 | 计数 |
|---|---|
| 收窄保留每一个可找到的标准答案 token | 13 |
| **收窄丢弃标准答案 token** | **5** |
| —— 其中收窄到 **0 轮**（空上下文 ⇒ 强制弃权） | **3** |
| —— 其中当前正确且会被破坏 | **2** |

收窄后平均上下文：45 轮中的 14.1 轮。三道问题
（`gpt4_d6585ce9`、`6e984302`、`gpt4_5dcc0aab`）解析到根本不包含任何
轮的窗口，因此该干预本会删除整个上下文。两个
当前正确的答案（`gpt4_b5700ca0`、`gpt4_5dcc0aab`）失去其证据。

窗口解析不够可靠，不足以被允许删除证据。如果
该锚曾被用于约束检索，它必须**重新排序**，绝不丢弃，
且当窗口什么都不匹配时它必须回退到完整上下文。

### 5.3 R6(a) —— 缺失单位默认值：**不值得单独一次运行**

当问题未命名单位时，`relativeUnit` 默认为 `day`，因此
`cc6d1ec1`（"How long had I been bird watching…?"）对标准答案
`Two months` 返回了 `59`。总体：8 道 TR 问题，3 道错。但**5 道正确中
有 3 道是裸天数**（`9`、`14`、`28`），判官当前接受它们，因此任何
改为自然单位的改动风险与收益相当。有 8 个例子，对它们拟合一条
规则是过拟合，不是工程。暂存。

---

## 6. 这一模式说明了什么

在 P31 和本文档中，现在已有五个候选 TR 干预被
检验。一个交付（§3）。三个被证伪（§5）。一个因不可拟合而暂存（§5.3）。
**剩余的 TR 错误质量由 LLM 在约 45 轮上下文上的阅读与
提取质量主导，不是确定性代码中的缺陷。** 这是诚实的读法，它
改变了战略：不再有一条可单元测试的路径通向大的 TR 增益，因此进一步的 TR 工作必须是
由运行验证的检索/上下文干预，并带 §5.2 表明必要的轮数和
证据保留防护。

| 能力 | 错 | 最佳剩余杠杆 |
|---|---|---|
| TR | 37 | 主要是 LLM 质量；§3 已交付（+4 天花板） |
| MR | 15 | 本次会话未刻画 |
| KU | 14 | 约 7 个选择失败（两个值都在上下文中，选错了那个）；其余是派生计数，其中"标准答案缺席"是答案格式的伪影 |
| IE | 5 | — |
| ABS | 1 | R4，天花板 +1 |

**下一个推荐支出：** 一次运行携带 (a) §3 修复、(b) R4 的
合取分解，以及 (c) P30 重新打开的弃权通道——
各带自己的消融实验臂，因此单次运行仍能分别归因每个效应。
