# 预登记：读者家族的第二级（`R2`）

> 状态：**已登记，派发前写死**。阈值在派发之前写成；run id 在派发后回填到 §6。

## 1. 为什么换的是家族，而不是第四个同族模型

`R1` 之后，读者轴上已经花掉三次派发，**三次都在 DeepSeek 内部换**：`thinking` 开关（+4.35 总体）、
`v4-pro` non-thinking（−5.55）、`v4-pro` thinking（`MR` −3 题且作废）。而竞品按类别表的读数
（`evidence/longmemeval/synap-published-categories.json`）给出了一个这三次都没检验过的形状：

| 能力 | Synap | 我们（`S16`） | 差 |
| --- | ---: | ---: | ---: |
| multi-session | 91.7% | 83.47% | **−8.2** |
| temporal-reasoning | 97.7% | 93.70% | −4.0 |
| knowledge-update | 97.4% | 93.06% | −4.3 |
| single-session（三类合并） | 95.7–96.7% | 91.33% | −4.4 至 −5.4 |

**差距是均匀的（−4 至 −8），不是一处塌陷。** 机制缺失预测塌陷：某个能力掉队，其余不动。一个更弱的
读者预测的正是全线同步后移——同契约、同装配、同提示词，换一个更强的模型，每个能力各涨几点。

> **H2**：`MR` 的剩余差距是**读者家族**，不是读者版本。在同一批 121 题、同一份提示词字节、**同一个判官**
> 下，把读者换成 `zhipu:glm-4.6`，`MR` 会上升。

## 2. 这次为什么比 `R1` 多了一个变量，而恰恰是它让比较成立

`R1` 只改 `reader.model`，但**判官跟着读者走**：80.99% 是 `v4-pro` 判 `v4-pro`，对照是 `deepseek-chat`
判 `deepseek-chat`。两处改动一次比较，所以 −3 题既可能是读者更弱，也可能是判官更严。

这一轮的派发**改两个字段**：`reader.model`（`deepseek-chat` → `zhipu:glm-4.6`）与 `judge`（随读者 →
钉住 `deepseek-chat`）。第二个不是实验变量，它是**让第一个成为单一变量的那个动作**：

| 字段 | 对照（`S16` = `44017278305`） | 处理（`R2`） | 是否混淆 |
| --- | --- | --- | --- |
| `reader.model` | `deepseek-chat` | `zhipu:glm-4.6` | **实验变量** |
| `judge.source` / `judge.model` | `reader` / `deepseek-chat` | `pinned` / `deepseek-chat` | **否**：判官身份两个臂相同 |
| 提示词 | 装配器产物 | 同一装配器产物 | 否：`promptIdentity` 必须报 121/121 |

判官的**身份**（`providerId` + `model` + `temperature`）在两臂一致，`source` 从 `reader` 变 `pinned` 只是
记录它是被告知的而不是继承的。这是 `R1` 缺的那一格。

## 3. 判官钉住机制本身，在本轮之前是不可用的

`llm-factory.ts` 自 §13.312 起读 `CORTEX_JUDGE_MODEL`，`judge-audit.yml` 一直有输入，但
`benchmark-cortex-memory.yml`——**唯一会派发一对臂的工作流**——没有入口。本轮补上了两端，并让它们互检：

| 端 | 文件 | 测试 |
| --- | --- | --- |
| 工作流转发 `vars.CORTEX_JUDGE_MODEL` | `.github/workflows/benchmark-cortex-memory.yml` | `test_workflow_judge_pin.py` 前 4 条 |
| 派发器**每次**写该变量（空值 = 删除），命名时声明 `judge` | `tools/dispatch-cortex-memory-ab.py` | 同文件后 8 条 |
| 注册门禁把 `judge.source` 当第九个条件（注册值 `reader`） | `tools/readout-arm-run.py` | `test_registration_diff.py` 的计数与 `test_index_embedding_wiring.py` 的词汇表 |

**没有第三条的话，这次派发会在花完钱之后被门禁拒绝**（`S14` 的形状）；**没有第二条的话，上一次实验的
钉住会被下一次继承**，而产物会诚实地说 `pinned`——真实，但回答的是另一个问题。

## 4. 判据（四条，`R2.1`–`R2.3` 全部成立才算通过）

| 行 | 指标 | 阈值 | 推导 |
| --- | --- | --- | --- |
| **`R2.1`** | `MR` 配对净正确题数（四轮多数票） | **≥ +5 题** | 与 `R1.1` 同一阈值，不新设：它是 8.18 点差距的一半，也是本仪器在 121 题上的最小可判读量的 2 倍 |
| **`R2.2`** | 精确 McNemar p | **< 0.05** | 与 `S16`/`R1` 同一约定 |
| **`R2.3`** | 提示词同一性 | `identical = 121, differ = 0` | 读者更换不得改动一个字节 |
| **`R2.4`** | `MR` 拒答题数（多数票答案 = 弃权记号） | **≤ 5**（对照 **0**） | 见 §4.1 |

### 4.1 `R2.4` 的阈值在读数之前被更正过一次

登记时写的是「≤ 6（对照 3 的 2 倍）」，那个 3 来自 `R1` §5 的后果表。**它不是可测量的那个数。**
在等 `R2` 的过程中先用 `S16` 自己的产物把判据跑了一遍，得到两个事实：

| 事实 | 读数 |
| --- | --- |
| `S16` 的 121 道 `MR` 题里，多数票答案是弃权记号的 | **0** |
| `reader-rung.py` 自配对（`S16` vs `S16`） | 净 +0、`identical 121/121`、p=1（工具自检通过） |

「2 × 0」不是一个阈值，而是一个恒真式：对照为 0 时，任何「不超过 2 倍」的写法都允许 0。所以把它
改成一个**能从产物算出、且与 `R2.1` 对称**的数：**≤ 5 题**。理由不是「差不多」，而是——一个读者若
拒答超过 5 道题，它放弃的正确数就已经达到 `R2.1` 要求它净赚的全部（+5），于是「靠少答换准确率」这条
路在算术上被排除，不必再看分数。**这次更正发生在 `R2`（`44575952564`）完成之前，且不改动 `R2.1`–
`R2.3`。**

## 5. 后果表（派发前写，读数后执行）

| 读数 | 结论 | 动作 |
| --- | --- | --- |
| `R2.1`+`R2.2`+`R2.3` 成立、`R2.4` 成立 | **`MR` 的天花板是读者家族** | 用户手册增加「读者强度」一节，写明点数与账单；重述 SOTA 口径（我们的数字取自对比表里最弱的一个读者）；`M1` 增加第二级；下一步转向**产品侧**：读者注入的默认建议 |
| `R2.1` 不成立、`R2.2` 不显著 | **读者轴按两个独立家族关闭**（第三个否证） | 记入 `RETRACTIONS.md` §3；下一个候选是 20 道失败题的**判官审计**，而不是第五个读者 |
| `R2.3` 不成立 | **作废**（不是失败） | 装配器读到了读者身份字段；修完再派发 |
| `R2.4` 不成立 | **不采纳，即使准确率上升** | 与 `R1` §5 同一行 |
| 账单 > 30 CNY | 按 `partial` 记录，超时按作废处理 | 派发前已把上界定在 30 |

## 6. 成本与可行性（探针实测）

**探针**：run `44571308998`（`limit=3`、1 轮、`model=zhipu:glm-4.6`、判官钉住 `deepseek-chat`）。
它同时关掉了本待办表的第一项（判官钉住从未在产物里被验证过）：

| 事实 | 读数 |
| --- | --- |
| `memoryArmConfig.judge` | `{providerId: deepseek, model: deepseek-chat, source: "pinned"}` ✅ |
| `memoryArmConfig.reader` | `{providerId: zhipu, model: glm-4.6, thinking: enabled, temperature: 0}` ✅ |
| **限流** | `attempts: 35`、`rateLimited: 0`、`retried: 0`、`refused: 0` |
| 每问 prompt token | 8,002（登记房间下） |
| 注册门禁 | step 18 **success**（`judge` 已声明、可解析） |

**限流那一行是本轮最重要的可行性读数。** `41346610318` 曾在**第 12 题**上 `429` 重试耗尽，当时的每问
prompt 是 ~12k token；而在登记房间（8,002）下，35 次调用**零限流**。约束是 TPM 而不是 RPM，房间表的
−25.4% 账单在这里换来了一个副作用：**它把一个不可行的派发变成了可行的**。这不是把房间表的读数改写成
正面结论（它买到的准确率仍是 −1.85 点），而是说它解除了另一条轴的封锁。

**墙钟外推**：`R1`（121 题 × 4 轮 × 两臂，`v4-pro` thinking）的 A/B 步是 **111.7 分钟**，对照
（`deepseek-chat`）**115.8 分钟**。两臂的形状相同，节流由 `minIntervalMs=6000` 与 4 个 worker 决定而
不是由模型决定，所以 `R2` 的预期墙钟是 **110–130 分钟**，在 340 分钟预算内。

### 6.1 第一次派发被自己的守卫拒绝，而拒绝是对的（`44572976099`）

`R2` 的第一次派发（17:03Z，`fa1b8214`）**没有到达模型**：工作流第 6 步「Check the budget covers the
pace」在**五秒**内拒绝，作业随即结束。**金钱成本 0，runner 成本约 2 分钟。**

拒绝的理由是一个真实的缺陷，且不是这一轮的改动引起的：

```
pacing floor 400 min (500 questions x 1 call(s) x 8 passes x 6000 ms), budget 340
  -> THE RUN CANNOT FINISH
```

`GRADED_QUESTIONS` 的规则是 `inputs.limit == '0' && '500' || inputs.limit`——它知道 `limit`，**不知道
`capability`**。对 `capability=MR` 的派发，它按文件的 500 题算地板，而这次实际只评 **121 题**，地板是
**97 分钟**。同一个缺陷在 `limit` 上已经被修过一次（`42366809734`，20 题 smoke 被判 400 分钟地板），
这一轮它在下一层重演。

**为什么 `R1` 没撞上**：`CORTEX_LLM_MIN_INTERVAL_MS` 只在 `model` 以 `zhipu:` 开头时注入
（`startsWith(inputs.model, 'zhipu:')`）。`R1` 的读者是 `deepseek:deepseek-v4-pro`，没有节奏，因此
`--min-interval-ms` 根本没传，地板不计算。**换家族的第一次派发，第一次让「capability 作用域 + 有节奏
的供应商」这两个条件同时成立**——于是守卫第一次必须回答「121 还是 500」。

修法（`d330bad1`）：守卫读 `tools/spend-baseline.json` 的 `ablation.questionsByCapability`——**与
`spend-projection.mjs` 定价同一个普查**——所以两个前置检查不再可能对同一次派发给出相反答案。未知能力
名**拒绝**而不是记作 0；普查缺块也**拒绝**而不是退回 500。10 条测试，其中一条把「两个前置检查读同一
份普查」写成断言。

**第二个派发：`44575952564`**（17:19Z，`ffaf90e3`，`capability=MR`、`model=zhipu:glm-4.6`、
`ablation_runs=4`、判官钉 `deepseek-chat`、`--budget 30`），第 6 步 **success**。

### 6.2 `R2` 死在供应商的速率限制上，不是死在读者上（`44575952564`）

`R2` 走到 **q=22/121**（+666.8s）时停下，`benchmark-error.log` 的第一行就是结论：

```
retry: exhausted after attempts=9 retried=8 rateLimited=8 elapsed=586328ms url=…/chat/completions
LLM request failed: 429 Too Many Requests — {"error":{"code":1302,
  "message":"您的账户已达到速率限制，请您控制请求频率"}} — not retried (attempts-exhausted)
```

产物（`benchmark-cortex-memory-partial.json`）：

| 事实 | 读数 |
| --- | --- |
| 到达 / 总数 | **22 / 121**（`run=0`） |
| 调用数 | 466，其中 `rateLimited` **33**（7.1%） |
| 重试 | 8 次，累计等待 **280s**，仍是 429 |
| prompt / completion token | 813,621 / 99,611 |
| **缓存命中** | **0**（Zhipu 无 prompt 缓存，DeepSeek 同一形状是 96%） |
| 部分账单 | **≈4.8 CNY**（按 glm-4.6 报价；无缓存折扣） |

**第三次派发（诊断，`limit=10`、1 轮）把「速率」和「额度」分开了**：run `44596567825` 在 **0.4 秒**
内死在 q=2，`2 次尝试 2 次 429`，而且死在**对照臂**（`reference-pipeline`）上——那不是我们的记忆臂在
压供应商，是**账户本身在拒绝每一个请求**。

```
transport losses reached 2 of 10 (ceiling 1, 2%): at this share the pass measures the endpoint
rather than the system under test. … Raise CORTEX_LLM_MIN_INTERVAL_MS, or use an account with a
larger quota, and re-dispatch rather than reading the number this pass would produce.
```

**这就是「不能读」和「读到 0」的区别**，而这次是传输守卫自己说的：它拒绝了一次会产出 0% 的 pass。

**结论：`R2` 未读，且不构成否证。** 读者家族这条轴**没有被关闭**，它被一个账户额度挡住了：

| 时刻 | 状态 | 证据 |
| --- | --- | --- |
| 16:54Z（探针 3 题） | 可用 | 35 次调用，0 限流 |
| 17:19Z–17:30Z（`R2` 前 22 题） | 边界 | 33 次 429，8 次重试耗尽 |
| 19:16Z（探针 10 题） | 关闭 | 2 次尝试 2 次 429（对照臂） |

**代价**：两次运行合计 ≈ **5 CNY**，其中 4.8 是 `R2` 的部分账单。`R2` 的 `--budget 30` 没有被突破，
而它买到的不是读数，是**三个时间点上的额度曲线**——比一次安静的失败有用。

**下一步（不派发）**：这条轴要恢复，需要一个能回答 121×8 次调用的账户，或第三个家族
（`custom:` 前缀已经支持任意 OpenAI 兼容端点，缺的是凭据）。**判据不动**：`R2.1`–`R2.4` 原样保留，
下一次派发沿用本文件的阈值。

---

## 7. 读数

（待回填）
