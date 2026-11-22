# 同模型复跑三家竞品：机制已落地，四条事实先于任何分数

**结论先行。** 要在 Runner 上用与 cortex 相同的 DeepSeek 评测 Mastra / Mem0 / MemCog，缺的不是 workflow 而是三样东西：一个能把"同一个 LLM"变成可审计字段的计量代理、一个能容纳"检索即推理"系统的协议操作、以及三个各自真的能跑起来的驱动。三样都已落地并有测试；四条事实在任何分数产生之前就已经被这次适配推翻或确认。

---

## 1. 为什么"同一个 LLM"必须是一个 base URL，而不是一句承诺

一次比较里有**四个**模型位置，而 cortex 只占一个：

| 系统 | 模型在哪里被调用 | 该位置是否决定它的公开分数 |
| --- | --- | --- |
| cortex | reader（每问 1 次） | 否 —— 纯检索 |
| Mem0 | ingest 抽取（`infer=1`，每 turn 1 次） | **是** —— 94.4 的配置用它 |
| MemCog | 建库 5 步 **+** 导航 2–7 轮 | **是** —— 95.80 是整个循环 |
| Mastra | 答题 agent、Observer、Reflector | **是** —— 84.23 vs 94.87 只差 reader |

只设 `DEEPSEEK_MODEL` 的跑法，等于拿"DeepSeek 读的 cortex"去比"各家默认配置的竞品"。Mastra 的默认是 `'auto'`：有 Google key 时选 Gemini。这不是比较，是三个实验。

因此：**每个驱动的 `base_url` 都指向 `tools/competitor-sut/sut_llm_proxy.py`**，代理转发到 DeepSeek 并从响应里读 `usage`。已被测试钉死的性质（`tools/__tests__/test_sut_llm_proxy.py`，10 条）：

1. 请求体与响应体**逐字节**转发 —— 被测系统在解析它们，重新序列化就是换了一份数据；
2. token 从 `prompt_tokens`/`completion_tokens` 分项读，不用 `total_tokens` 加分项（那会重复计）；
3. `X-Sut-Label` 把账单按阶段拆开：`memcog/build` 与 `memcog/navigate` 是两行，因为"建库占九成"和"查询占九成"需要不同的修法；
4. 计数按模型分表，静默 fallback 会显示为两行而不是一个平均；
5. `stream: true` **转发**并在末帧结算 —— 见 §3，第一版拒绝它是错的；
6. 上游 4xx 原样透传并计 `failures`，不变成 200 空体。

---

## 2. MemCog 的公开仓库调不动模型

`WeAgentAI/MemCog` @ `fff97b2d4190` 的 `src/core/llm_client.py`：

```python
def _call_gpt(...):
    for _ in range(3):
        try:
            # TODO: 在此填入 OpenAI 兼容接口的调用逻辑
            # completion = client.chat.completions.create(**kwargs)
            response = {}
            return response
```

`src/config/llm_config.py` 是四个空字符串。README 要求使用者自己取消注释示例。

**结论：任何 MemCog 复现都必然包含"复现者自己写的传输层"。** 我们这份也一样 —— `memcog_driver.py` 在任何人按名 import 之前 patch `core.llm_client.call_llm`，且补丁只含作者注释里那六行（无额外重试、不改进 prompt、不做解析）。manifest 原文写明这一点。

这不是论文的缺陷，而是"引用这个仓库的数字时，那个数字意味着什么"的一个事实。

### 2.1 而且它在 3.12 以下根本跑不起来，仓库没说

第一次真实派发死在 `manifest produced no response`。驱动 stderr 写着原因：

```
File ".../store_build/sources.py", line 75
SyntaxError: f-string expression part cannot include a backslash
```

PEP 701 在 Python **3.12** 才允许 f-string 替换字段里出现反斜杠。runner 是 3.11.18。于是模块 import 就炸，失败发生在 `main()` 之前，parent 把它报成"驱动死了"而不是"没人核对过的版本假设"——README 里没有任何最低版本说明。

两个后果，且超出这一个文件：

1. **竞品的运行时要求是它配置的一部分**。晚发现的代价是一个完整派发。`memcog_driver.py` 现在在低于 3.12 时 re-exec 进 `MEMCOG_PYTHON`，否则用一句话退出，同时点名版本、文件与 PEP；
2. 解释器**装在 job 的 3.11 旁边**而不是替换它——这次比较的其它每一步都在 3.11 上测量，换掉它就是实验里多一个变量。

---

## 3. Mastra 的 `agent.generate` 走流式，第一版代理拒绝它是我的 bug

第一版代理拒绝 `stream: true`，理由是"usage 只在末帧完整，逐 delta 累加会报一个没测量过的数"。理由对了一半：**不做累加**是对的，**拒绝**是错的。Mastra 每次 generate 都发 `stream: true` 与 `stream_options.include_usage`，拒绝的结果是三家系统里有一家完全跑不起来，且症状是**空答案**——一个会被读成"记忆系统坏了"的形状。

修法：逐块转发 SSE，从**带 usage 的那一帧**读取（赋值而非累加），一次会话计一次 `calls`（不是一帧一次），并记录 `stream_frames`，使得"流结束但没有 usage 帧"可见而不是静默为零。

---

## 4. 两个系统没有检索端点，协议因此长出一个可选操作

`MemoryProvider.answer?` —— 类型上可选、manifest 上可选、它的存在本身是一个关于架构的声明。

| 后果 | 断言位置 |
| --- | --- |
| `self` 系统**不会**再被共享 reader 读一遍 | 用一个会抛错的 reader 断言，而不是一个会记录的（同时调两条路径也能得到像样答案，只有账单会说话） |
| judge **仍然**是共享的 | 所以 accuracy 仍可比 |
| `ProviderScore.answerer` 记 `shared`/`self`/`none` | 表格对 `self` 行的 recall 列打印 `—` 而不是 `0.0%`（它没有排序列表，零是假陈述） |
| `ProviderScore.usage` 携带系统自身花费 | `null` 是"未测量"，不是"免费" |

为什么这个字段非有不可：Mastra 自己的消融是**同一记忆系统 84.23 → 94.87**，只换 reader。把 `self` 行和 `shared` 行并排打印总分会诱导读者去做那 10.64 点明令禁止的减法。

---

## 5. 派发之前的成本与时间算术

本地替身实测（不是语料）：120 turn（约 36k token）的一题，**9 次模型调用**（8 次观察/反思 + 1 次作答），耗时 **4 分 10 秒**。LongMemEval-S 每题约 550 turn，直接外推是每题 5–15 分钟。

| 臂 | 每问调用 | 每问 token（估） | 100 题 | 500 题 |
| --- | ---: | ---: | ---: | ---: |
| cortex（纯检索） | 1 reader + 1 judge | ~7.4k 上下文 + judge | ≈ 1.5M | ≈ 7.5M |
| Mem0 `infer=1` | ~550 抽取 + 2 | ~1.6M | ≈ 165M | ≈ 820M |
| MemCog | ~50 建库 + ~4 导航 | ~200k | ≈ 20M | ≈ 100M |
| Mastra OM | ~8 观察 + 1 作答 | ~36k | ≈ 3.6M | ≈ 18M |

按 DeepSeek 标价（¥2/M 输入 miss、¥8/M 输出）粗算，500 题列：Mem0 约 **¥1,900**、MemCog 约 **¥250**、Mastra 约 **¥60**，另加共享 reader/judge。

**真正的约束不是钱而是墙钟时间**：500 题 × 5 分钟 = 41 小时，单 job（300 分钟上限）跑不完。所以首轮 100 题，500 题那轮需要分片。

这也是 `sut_infer` 默认仍是 `0` 的原因：`infer=0` 是**另一个系统**，manifest 会写明跑的是哪一个。

---

## 6. 首轮派发与它要判的问题

顺序：`sut=memcog` → `sut=mastra` → `sut=mem0&sut_infer=1`，均 `read_questions=100`，`sut_llm` 留空（继承 reader 的模型 id）。

每个数字要回答的问题都被刻意收窄。**不是**"cortex 是否比 MemCog 强"，而是：

1. MemCog 在同 100 题、同 judge、同模型下若领先 3 点以上 → 要抄的机制是**可导航结构与工具调用**，`DESIGN-MULTI-STEP-RETRIEVAL.md` 已有对应预注册；
2. Mastra 若领先 → 要抄的机制是**压缩代替检索**（阈值化的 Observer/Reflector），这是本仓库从未测过的方向，账本里最近的亲戚是 `[thing 3]`；
3. Mem0 `infer=1` 对 `infer=0` —— 抽取消融一旦这个臂存在就是免费的，而它是唯一能回答"事实抽取在这个语料上到底买到了什么"的测量。

**输掉的竞品也回答了一个问题**，这正是"跑他们的代码"而不是"读他们的表格"的意义：§2–§4 的四条事实，全部产生于任何一道题被评分之前。

---

## 7. 遗留风险（已知且未解）

| 风险 | 状态 |
| --- | --- |
| MemCog 建库是**逐 session** 五次 LLM 调用，500 题可能 250 万次调用 | 已按 100 题首轮；若建库主导，下一步是建库缓存（同一 haystack 在题间复用） |
| Mastra OM 的 30k 阈值决定它到底是"压缩记忆"还是"摘要器" | 可由 `MASTRA_MESSAGE_TOKENS` 覆盖，manifest 记录实际值；首轮用 Mastra 自己的默认 |
| Mastra 的 vendor harness / ingest 顺序未知，94.87 不可复现 | 只复现**机制**，不声称复现数字；报告按 `self` reader 降级，不做 A 级比较 |
| MemCog 的判分器是它自己复制的官方模板 | 不采用它的判分；只取它的 prediction，交给共享 judge |
| 流式转发没有背压控制，慢客户端会拖住代理线程 | 单线程顺序跑，无并发；若分片并发需要改成 select |

---

## 8. 首轮实测：同 judge、同模型、同一批题

两次派发在同一个 judge、同一个 DeepSeek、同一份抽样上产出了数字。样本都小——Mastra 30 题、Mem0 首轮 2 题——所以下表每一行都带 `n`：30 题里差 2 题就是一枚硬币。

| 臂 | n | 准确率 | 调用/题 | prompt token/题 | ¥/题（目录价） | 它的上下文是什么 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `mastra`（自答） | 30 | **70.0%**（21/30） | 2.0 | 125,104 | 0.273 | 自己的生成器，观察日志 + 原文 |
| `cortex-session`（共享 reader） | 30 | 63.3%（19/30） | 1 reader + 1 judge | 33,270 | 0.067 | 整 session，预算 8 turn |
| `lexical-reference`（共享） | 30 | 63.3%（19/30） | 1 + 1 | 34,974 | 0.070 | 同 session 的词法 top-k |
| `cortex/trim-2.8k`（共享） | 30 | 56.7%（17/30） | 1 + 1 | 2,799 | 0.006 | 2.8k 字符窗口 |
| `mem0` `infer=1`（共享） | 2 | 50.0%（1/2） | 51.5 | 576,772 | 1.37 | 抽取后的事实，向量 top-k |

阶段成本从产物里读，不靠新计数器：每个 `competitor-read*.json` 里的 `usage` 是代理在该阶段结束时的累计值，相邻两个文件的差就是该阶段自己的花费，SUT 步的花费是余数。这样"每题账单"这个数字只有一个来源，不用再维护一条必须与之保持一致的第二计量通道。

配对检验就在产物里，所以比较是逐题而不是两个比率相减：

```
cortex-session   -> mastra   n=30  +5/-3  delta +6.7%   p=0.7266  不显著
cortex/trim-2.8k -> mastra   n=30  +8/-4  delta +13.3%  p=0.3877  不显著
```

### 8.1 Mastra 的观察记忆在它自己的默认阈值上没有压缩

这个臂被派发来测的机制是"压缩代替检索"：Observer 把旧消息折成观察，Reflector 合并，agent 用观察日志 + 近期窗口作答。`messageTokens` 留 Mastra 自己的默认 30,000，语料约 115,000 token。

账本记录的是**真正进入模型的东西**：90 次作答产生 **180 次调用，每次作答 2 次**，而这两次并不对称：

| | 每次调用的 prompt token |
| --- | ---: |
| 小调用（180 次中的 90 次） | p25 7,765，min 5,884 |
| 作答调用（另外 90 次） | 中位 **112,144**，p75 116,635，max 118,781 |

也就是说**作答调用带的是原文，不是压缩日志**：115k 语料上中位 112k token，等于什么都没压。这个 70% 是一次**全上下文阅读**外面套了一层记忆接口，它该和 `cortex-session` 的 33k、`cortex/trim-2.8k` 的 2.8k 并排读，而不是和 cortex 的预算臂当成同一上下文预算来比。

这个读法改变了"该抄什么"。"压缩代替检索"不是那 +6.7 点的来源，**上下文体积**才是，而 cortex 已经有这个旋钮（`maxPromptCharsByRoute`）。Mastra 真正提供的信息是战利品的尺寸：3.8 倍上下文，+6.7 点，n=30 下不显著。

### 8.2 Mem0 的抽取是表里最贵的上下文，而且两题都输了

`infer=1` 在 ingest 阶段每 session 一次模型调用——两题的 haystack 就是 103 次调用——而抽取提示本身携带对话原文，所以账单是**每题 576,772 prompt token**：整个 115k 语料的 5.0 倍、`cortex-session` 33k 的 17 倍、2.8k 窗口的 206 倍。它答对 1/2。同一批两题上，cortex 每一条臂都答对 2/2。

不是样本量问题的那部分在这里：**换三种读者提示，答案不动**。同一份 `mem0` 上下文在 `con`、`dispatch`、`dispatch2` 下都是 1/2；而 `cortex-session` 是 2/2 → 1/2 → 1/2，`cortex/trim-2.8k` 稳定 2/2。当一个插入能力子句的提示对某条臂毫无作用、对另一条臂有作用时，差别在两条臂**放进 reader 的东西**里。

这个臂的 recall@k 是 0.0%，而这个数字说的是**指标**而不是 Mem0：命中判定的条件是片段文本里含有一个金标 **turn**，而抽取出来的事实不是 turn。这个指标根本看不见抽取型系统，能读的只有它的准确率列。

### 8.3 派发过程暴露的两个缺陷，和它们的共同点

两个都不是关于竞品的，都是关于"跑出了一句它没测过的话"。

**崩掉的 harness 是一个绿色步骤 + 一个空文件。** 九个测量步骤写成 `node ... | tee 产物`，而管道报告的是最后一条命令的退出码。于是 run 45011910491 **成功**结束，阅读表 0 字节，成本报告写着"阅读阶段没写 json"。harness 其实在 import 时就死了，死在第一行输出之前。现在九个步骤都加了 `set -o pipefail`；此后同类失败会显示为红叉——第二个缺陷正是这样被发现的。

**一个没有任何步骤创建过的目录。** `MASTRA_STORE` 在三个阅读步骤里指向 `<workspace>/.cache/mastra/store.db`，而在两个真正 ingest 的步骤里都没设。于是 ingest 用了驱动的 `/tmp` 默认值，没有任何步骤创建 `.cache/mastra/`，libsql 对阅读阶段回答 `ConnectionFailed("...: 14")`——SQLITE_CANTOPEN，读起来像权限或损坏，两者都不是。现在模型/代理/两个存储的变量统一放在 job 的 `env`，驱动自己创建被交付路径的父目录，而 live 往返测试故意传一个父目录不存在的路径。

第三个更小但同类：Mem0 的 DeepSeek 工厂无论模型是否可达都会构造 `OpenAI` 客户端，而检索阶段不携带 `DEEPSEEK_API_KEY`，驱动把 `""` 传了进去，于是以 `Missing credentials` 死在 import。那条路径上没有任何东西读这个凭据——代理会用自己的上游 key 覆盖 `Authorization`。现在 loopback base URL 会拿到显式的 `proxied` 占位符，manifest 记录用了哪个占位符，而任何非本地 URL 仍然什么都不给。

---

## 9. 该抄什么，不该抄什么

| 系统 | 按本次实测，它到底在做什么 | 对 cortex 的判定 |
| --- | --- | --- |
| Mastra OM | 每题 2 次调用，作答那一次中位 112k token：全上下文 + 一份观察日志 | **抄预算，不抄机制。** +6.7 点是上下文体积买来的；`maxPromptCharsByRoute` 是更便宜的杠杆，该做的实验是窗口扫描，不是引入 Observer |
| Mem0 `infer=1` | 每题 51.5 次调用、577k prompt token（语料的 5 倍）把 session 变成事实，然后两题全输 | **不抄抽取。** 它是表里贵两个数量级的上下文；`infer=0` 消融是那个便宜的对照，用来说清"抽取本身没用"还是"只是太贵" |
| MemCog | 库由模型建：36 分钟里 1,198 次调用、215 万 prompt token，最终没有产出任何答案 | **抄接口，不抄建库。** 可导航页面 + 两个工具 + 有界轮数是比看上去更小的改动（`DESIGN-MULTI-STEP-RETRIEVAL.md`）；它每题到底花多少正在用带题号的账本测——第一份账本 36 分钟只有一个标签，无法分辨那是一题还是五题 |

三家都没有证明的一件事：**在相同上下文预算下**有机制能赢过 cortex 自己的窗口。那正是下一轮该跑的实验——把所有臂的 reader 输入固定在 33k token，看观察、事实、导航能不能在**同一个信封内**赢过逐字 session。

---

## 10. 五个必答问题的当前答案

1. **三家能不能在同一模型上被测？** 能。Mastra 与 Mem0 已产出同 judge 的分数；MemCog 的建库成本使 100 题不可行，只能小样本或分片。
2. **"同一个 LLM"是否可审计？** 是。`X-Sut-Label` 把每次调用记到系统与阶段上，账本随产物上传，每个数字都能回溯到调用行。
3. **准确率差距是多少？** n=30 上 Mastra +6.7pp（不显著）、Mem0 n=2 上 −50pp。
4. **成本差距是多少？** 每题 prompt token：2.8k（cortex 窗口）／33k（整 session）／125k（Mastra）／577k（Mem0）／~2.15M（MemCog 建库未完成一题）。
5. **该抄什么？** 预算先于机制：先把窗口给够，再谈 Observer、抽取或导航；要抄的是 MemCog 的**接口形状**，不是它的建库方式。

