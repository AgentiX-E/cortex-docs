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
