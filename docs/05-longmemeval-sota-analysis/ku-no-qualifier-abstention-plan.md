# 迭代 #146 — KU 无限定词弃权缺陷

状态：**已接受 —— 见 `/workspace/analysis/ku-no-qualifier-verdict.md`**

实测结果（4v4 同一时刻 A/B）：KU `other` 弃权 14.36% → 4.26%（−10.11pp，精确置换检验
p = 0.0143）；KU 准确率 75.35% → 79.51%（+4.17pp，精确置换检验 p = 0.0143）；归因残差 0；
守卫 IE/MR/TR 不变。

本次迭代**取代**此前提出的 #146（`flu` 操作数识别）与 #147（`ABS` 弃权）。两者均已被
测量结果作废——见 §1。

---

## 1. 为何先前的计划被作废（基于测量，而非假设）

### 1.1 `flu` 操作数识别 — 已死

`370a8ff4` "How many weeks had passed since I recovered from the flu when I went
on my 10th jog outdoors?"

| 项 | 值 |
| --- | --- |
| 流感康复轮次 | `2023/01/19`（"finally recovered from the flu **today**"） |
| 第 10 次慢跑轮次 | `2023/04/10`（"I went on my 10th jog outdoors **today**"） |
| 正确间隔 | 81 天 = 11.57 周 → `12` |
| 引擎输出 | `"12"` —— **操作数与算术均正确** |
| 金标准 | `15`（= 105 天） |
| 整个检索上下文中最大的跨度 | `2023/01/05 → 2023/04/10` = 95 天 = 13.57 → `14` 周 |

从上下文中任意一对日期都够不到 `15`。引擎并没有选错操作数；金标准所需要的那次更早的
流感会话从未被检索到。**这是一个检索问题，任何引擎改动都无法产生 `15`。**

佐证普查（`tr_gold_reachability.mjs`，调用**已发布**的引擎，因此没有任何逻辑被重新实现）：
在 24 道机器可比的 `relative` TR 题中，**21 道可精确达到，23 道在 ±1 内达到**。
`relative` 子类并不是余量所在之处。

### 1.2 `ABS` 弃权 — 从未存在

我此前报告"ABS 0/30，零弃权，引擎对每个答案都在编造"。那是错的：我读的是
`nl-naive-baseline` 实验臂，它是一个刻意设计的非弃权对照基线，不是 cortex 系统。

cortex 实验臂（`nl-abstain-feature`）得分 **ABS 30/30，30/30 弃权正确 —— 100%，四次
运行全部如此。**

---

## 2. 基准的真实状态（处理臂，4 次运行）

| 能力 | 正确 / 总数 | 准确率 |
| --- | --- | --- |
| IE | 142.25 / 150（均值） | 94.8% |
| MR | 87.0 / 121 | 71.9% |
| KU | 53.0 / 72 | 73.6% |
| TR | 93.75 / 127 | 73.8% |
| ABS | 30 / 30 | **100%** |
| **Overall** | **406.0 / 500** | **81.20%**（80.40 / 81.80 / 81.20 / 81.40） |

剔除 ABS，cortex 实验臂在其余 470 题上得分 80.2%，而朴素基线为 **80.6%**。
**在 ABS 之外，弃权通道是净负的**；全部的 +5.6pp 都来自 ABS 0 → 30。

`abstentionCorrectRate = 46.2%`：65 次弃权中，30 次正确（全部为 ABS），**35 次错误
——系统在可回答的问题上说"我不知道"。那是基准的 7.0%。**

---

## 3. 35 次错误弃权的根因

`buildKnowledgeUpdatePrompt` 让模型承诺一个两步契约。Step 2 提供三个互斥分支：

```
Step 2 — Pick the value matching the time qualifier:
  - "previous", "before", "originally", "used to"     -> the EARLIER (older) value
  - "currently", "now", "most recent", "latest", ...  -> the LATER (newer) value
  - "still", "same", or a Yes/No question             -> compare the turns, answer Yes or No
```

**完全没有为根本不含时间限定词的问题准备分支。**

`classifyKnowledgeUpdateQualifier` 恰恰对这类问题返回 `'other'`，而
`answerKnowledgeUpdate` 中的路由守卫是 `qualifier !== 'other' && ...` —— 因此 `'other'`
问题**既**跳过双时态路径，**又**落入不完整的 Step 2。该提示词除弃权标记外，没有为不可满足的
Step 2 定义任何终止出口。

### 3.1 实测后果（`ku_qualifier_census.mjs`，4 次运行合并）

| 限定词 | 每次运行 N | 每次运行弃权 | 弃权率 | 金标准逐字出现在上下文中 |
| --- | --- | --- | --- | --- |
| `previous` | 10.0 | 1.00 | 10.00% | 1.0 / 1.0 |
| `current` | 15.0 | **0.00** | **0.00%** | — |
| **`other`** | **47.0** | **7.00** | **14.89%** | **6.8 / 7.0** |

`'other'` 对 `'previous'+'current'`：14.89% 对 4.00%，**z = 2.801**。
`'current'` 在四次运行中弃权 **0 / 60** —— 弃权并非 KU 固有的，而是 `'other'` 路径特有的。
`'other'` 占 KU 的 **65%**（47/72）。

逐次运行的计数在四次运行中逐字节相同（`current: 0/15, other: 7/47, previous: 1/10`），
所以这是结构性的，不是噪声。

### 3.2 这些失败是明确无误的

| 问题 | 金标准 | 检索上下文中逐字出现的证据 | top1 |
| --- | --- | --- | --- |
| Where am I planning to stay for my birthday trip to Hawaii? | `Oahu` | "I'm actually planning to stay **on Oahu**" | 0.670 |
| How long have I had my cat, Luna? | `9 months` | "I've had my cat, Luna, for about **9 months** now" | 0.687 |
| How long have my parents been staying with me in the US? | `nine months` | "they've been staying with me for **nine months** now" | 0.709 |
| How much time do I dedicate to coding exercises each day? | `about two hours` | "dedicating **about two hours** each day" | 0.752 |
| How often do I see my therapist, Dr. Smith? | `every week` | "I see Dr. Smith **every week**" | 0.669 |
| How many free night's stays can I redeem at Hilton? | `Two` | "enough points for **two** free night's stays" | **0.911** |
| What new kitchen gadget did I get before the Air Fryer? | `Instant Pot` | "using my new **Instant Pot**" | 0.677 |

### 3.3 代码库中已经存在该修复范式

`buildAggregationQaPrompt`（MR）带有明确的反弃权护栏：

```
'Combining facts across several sessions is NOT a reason to abstain.',
'If the answer can be computed from facts already in the context ... compute it.
 Needing to derive the answer is NOT a reason to abstain.',
```

`buildKnowledgeUpdatePrompt` **一条都没有**。KU 提示词只是缺失了 MR 提示词早已获得的那一
处理。

---

## 4. 修复

对 `src/natural-language-memory.ts` 中 `buildKnowledgeUpdatePrompt` 的两处编辑：

1. 增加**第四个 Step 2 分支**，覆盖无限定词的情形：按原样报告该值；当同一主体有多个值时，
   报告来自 LATEST（最新）轮次的那个。
2. 增加**反弃权护栏**，镜像已被验证的 MR 范式：没有时间限定词不是弃权的理由；只找到一个
   值也不是弃权的理由。

刻意**不**做的事：

- **放宽 `classifyKnowledgeUpdateQualifier`。** 它只会把 7 道失败题中的 1 道重新分类
  （例如 "after her recent relocation"），却带来把一个货真价实的 `previous` 问题翻成
  `current` 的风险，那样确定性双时态路径就会用错误的值作答。风险/回报不佳——推迟。
- **把 `'other'` 路由进双时态路径。** 对于一个多值的 `'other'` 问题，正确的限定词本就是
  未定的，因此确定性地取最早/最新不过是一种猜测。提示词修复处理得更好。

---

## 5. 测试计划（TDD —— 测试在修复之前先编写并观察到失败）

1. **完整性不变量** —— *正是它的缺席让本缺陷得以发布。* 对于
   `classifyKnowledgeUpdateQualifier` 值域中的每一个值，提示词**必须**包含一个匹配的
   Step 2 选择规则。每一行先断言该测试夹具确实被分类为该限定词，这样表格就不会悄悄腐坏。
   今后往分类器中新增第四个限定词，会立即破坏此测试，直到补上一条规则。
2. 无限定词分支存在，并指明 LATEST 轮次的平局裁决规则。
3. 护栏：没有时间限定词被明确声明为不是弃权的理由。
4. 护栏：只有一个值被明确声明为不是弃权的理由。
5. 接线测试：`answerKnowledgeUpdate` 对一道无限定词 KU 问题实际交给 LLM 的提示词携带了
   新分支（防止该提示词在 KU 路径中被替换或绕过）。

## 6. 验收标准

| # | 准则 | 阈值 |
| --- | --- | --- |
| A1 | `pnpm check` 通过 | lint + typecheck + test + format |
| A2 | 覆盖率，**每一个**维度（statements / branches / functions / lines） | **>= 95%** |
| A3 | 新测试在修复前的提示词上失败，修复后通过 | RED -> GREEN |
| A4 | **主要（机制）：KU `'other'` 弃权率** | 基线 14.89%，必须实质性下降 |
| A5 | **共同主要：KU 准确率** | 基线 73.6% |
| A6 | 守卫：总体准确率 | 不得出现超出实测零噪声底的回归 |
| A7 | 守卫：IE / MR / TR / ABS 不变 | 结构性——该提示词只能从 `q.questionType === 'knowledge-update'` 到达 |

### 6.1 为何主要端点是机制，而非总体准确率

预期效应：每次运行约挽回 7 次弃权，其中 6.8 次持有逐字金标准。即便按 50% 的挽回率，那
也是 +3.4 题 = **总体 +0.68pp**，轻松**低于**字节完全相同的代码所测得的约 1.7–2.1pp
的跨时间窗口漂移。因此总体准确率无法分辨这一变更；弃权率这一机制端点可以，因为它构造上
就是去噪的。

注意，在非 ABS 题上弃权本就记 0 分，所以把弃权切换为作答在期望上从不为负。

## 7. 验证协议

同一时刻 4 + 4 A/B（绝不交错——日内时间漂移会使交错设计失效）。机制端点为主；
准确率以带噪声底限的描述性估计报告，附 Wilson 95% CI 与配对 McNemar。

---

# 迭代 #148 — `retryableFetch` 中的逐次尝试请求截止时间

状态：**已修复，端到端对照真实 socket 验证通过**

## 根因

`retryableFetch` 此前没有任何形式的截止时间。重试只有在一次尝试确实**落地**时才有用：
一个被接受随后却停滞的请求（连接被重置或处于半开状态）会让循环挂在一个永不落定的 promise
上，于是 `maxRetries` 永远不会执行，调用方无限期挂起。一次完整的基准运行就这样因
`TypeError: terminated` 而丢失。

## 修复

`src/retry.ts`：

1. **每次尝试都创建全新的 `AbortSignal.timeout`**。`AbortSignal` 是一次性的，因此在循环
   之前创建一次的信号，等重试跑到时早已被中止——每次重试都会瞬间失败，重试预算会在没有
   任何请求到达服务器的情况下被耗尽。
2. 调用方提供的 `init.signal` 被保留，并通过 `AbortSignal.any` 组合，因此外层取消仍然
   优先。
3. `timeoutMs: 0` 表示退出该机制。
4. 三个调参旋钮移入 `RetryOptions` 对象。按位置参数写法为
   `retryableFetch(fn, url, init, 5, 1000, 60000)`。

`timeoutMs` 已贯穿两个适配器（`OpenAICompatibleLLMOptions`、`OpenAIEmbeddingOptions`），
因此可端到端配置。

## 验证

### 单元测试（`retry.test.ts` 中 16 个，TDD：修复前观察到 9 个失败）

| 注入的变异 | 结果 |
| --- | --- |
| 把信号提升到循环之外（跨重试复用） | **已捕获** —— `[false,true,true] ≠ [false,false,false]` |
| 未安装截止时间 | 被 4 个测试捕获 |
| 忽略调用方提供的信号（`AbortSignal.any` -> 截止时间） | 被 2 个测试捕获 |

第一行很重要：更早版本的"全新截止时间"测试只在第一次调用时挂起、第二次就作答，因此重试
路径从未查询该信号，**该变异体在一次全绿的运行中存活了下来**。测试被改写为断言每次尝试所
收到的信号状态，这是确定性的，从而杀死了该变异体。

### 端到端对照真实 socket（`verify_retry_timeout_e2e.mjs`）

之所以需要它，是因为 `AbortSignal.timeout()` 在 Node 中使用的是**未 ref 的定时器**：
它不会让事件循环保持存活，因此每个基于 fake 的单元测试都只在测试运行器把事件循环撑开时
才检验到该截止时间。没有一个能证明截止时间会在真正停滞的 socket 上触发。

```
PASS  stalled socket is aborted by the deadline — TimeoutError
PASS  abort happens at the deadline, not before — 302ms >= 300ms
PASS  abort happens promptly after the deadline — 302ms < 1800ms
PASS  every retry was attempted (3 attempts)
PASS  three independent deadlines elapsed — 906ms >= 900ms
PASS  default deadline is 60s
```

## 验收

`pnpm check` 通过：4 个包共 693 个测试（core 87、node 16、llm 41、eval 549）。
所有包中任一维度的最低覆盖率：**97.22%**（阈值 95%）。
