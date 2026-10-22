# MR 审计判决：JSON 假设被证伪；真正的瓶颈是过度弃权

**结论先行**

1. **"MR 上下文 JSON 结构化"这一假设被证伪。** MR 错误并非"格式含糊导致条目误识别"，而是**在已有证据时 LLM 仍然弃权**。
2. **真正的瓶颈：过度弃权。** 在 38 个数值型 MR 错误案例中，**20 个（53%）是 LLM 主动弃权（`reason=llm`）**，而其中的 **15 个，其证据会话被完整召回**——模型手中已有数字，却返回了 `UNANSWERABLE`。
3. **方向明确、可修复、低风险**：这些弃权集中在"需要推导"的问题上（百分比/平均值/减法/求和/时间差）以及简单计数。模型并非不会计算——它**没有去计算**（算术本身已被证明是正确的）。修复 = 强化 MR 聚合提示，明确将"跨会话组合 / 推导答案"从弃权理由中排除——这正是单会话 `buildQaPrompt` 已经拥有而 MR 缺失的那一条款。
4. 可恢复的上限空间：若将那 15 个证据完整的弃权转换为作答，以 50–60% 的准确率计，将是 **MR +6–9pp，总体 +1.2–1.8pp**。

---

## 1. 审计过程与证据

遵循"先看方向再下结论"的方法，我对 `f096338` 中 121 个 MR 问题逐一归因：

### 1.1 决定性证据：弃权来自 LLM，而非阈值

| MR 决策来源 | 数量 |
|---|---|
| `answered` | 99 |
| `llm`（模型主动弃权） | 22 |
| `threshold`（检索置信度触发） | **0** |

**检索阈值从未触发过弃权**——每一次弃权都是模型自身的决策。此外，弃权问题的 `top1Score`
中位数为 0.614，与已作答问题的 0.665 高度重叠；检索置信度无法区分二者。

### 1.2 错误归因（38 个数值案例）

| 归因 | 问题数 | 占比 |
|---|---|---|
| **LLM 弃权**（证据完整召回 15 + 证据缺失 5） | **20** | **53%** |
| 已作答但错误（枚举/去重/差一错误） | 18 | 47% |

### 1.3 那 15 个"证据完整却弃权"案例的共同点

模型明确陈述了其弃权原因，逐一阅读可见它们全都属于同一种模式——**"答案需要推导/计算，而我
没有直接看到现成的答案"**：

| 问题类型 | 示例 | 模型行为 |
|---|---|---|
| 百分比 | `percentage of packed shoes`（gt=40%） | 找到了 "2 of 5" 却弃权 |
| 百分比 | `percentage of renovation cost`（gt=10%） | 弃权 |
| 平均值 | `average GPA`（gt=3.83） | 弃权 |
| 平均值 | `average age of family`（gt=59.6） | 弃权 |
| 减法 | `years older than grandma`（gt=43） | 弃权 |
| 减法 | `minutes exceeded marathon`（gt=12） | 弃权 |
| 求和 | `page count of two novels`（gt=856） | 弃权 |
| 返现 | `cashback at SaveMart`（gt=0.75，=1%×$75） | 找到了 $75 却弃权 |
| 时间 | `what time did I go to bed day before…`（gt=2） | 弃权 |
| 简单计数 | `food delivery services`（gt=3） | 弃权 |
| 简单计数 | `health devices per day`（gt=4） | 弃权 |

---

## 2. 为什么 JSON 没有帮助

这 15 个问题的问题并非"分不清哪句话属于哪个会话"（一个 JSON 能解决的结构性问题），而是
**模型拒绝去推导**（一个语义行为问题）。JSON 结构化改变的是呈现形式；它无法改变模型
"看到数字却不做结论"的行为。

## 3. 修订方案：强化 MR 弃权边界（仅提示）

当前的 `buildAggregationQaPrompt` 只有一行：

```
Respond with exactly "UNANSWERABLE" ONLY if the context contains no relevant information at all.
```

单会话的 `buildQaPrompt` 有一个更完整的边界：

```
If the context offers more than one possible answer, choose the one that best matches…
Choosing between candidates or combining several turns is NOT a reason to abstain.
```

**变更**：在 MR 聚合提示中补入"推导/组合 ≠ 弃权"边界，明确列出模型最常见的错误弃权场景：

```
Abstain ONLY when the context contains NO relevant information whatsoever.
If the answer can be COMPUTED from numbers already in the context — a sum, a
difference, an average, a percentage, an elapsed time, or a date read — compute
it; derivation is NOT a reason to abstain. Combining facts across sessions is
NOT a reason to abstain.
```

这是一次**纯提示变更**，不触碰任何解析/聚合代码，风险面最小，且直接针对 53% 的错误案例。

## 4. 验收标准（待批准）

| # | 项目 | 阈值 |
|---|---|---|
| 1 | TDD | 提示断言测试先变红，再变绿 |
| 2 | 单元测试 | 新增 ≥8 个案例：新边界句存在、旧弃权句仍存在、所有其他提示逐字节不变（回归锁） |
| 3 | 覆盖率 | 四个维度 ≥95% |
| 4 | 本地回归 | lint/format/typecheck/test/build 全绿 |
| 5 | 主要端点 | MR 弃权率**显著下降**（逐题精确 McNemar p<0.05；当前基线 22/121 = 18.2%） |
| 6 | MR 准确率 | 相对同时刻对照**上升**（描述性 + 逐题配对的确定性准确率，避开运行级噪声下限） |
| 7 | 无回归 | IE/TR/KU/ABS 不差于对照 −1.0pp |
| 8 | 护栏 | 弃权下降**不得**以"在真正无法回答的问题上强行作答"为代价：ABS 类别不受影响（它走独立路径），且必须对新作答问题的证据召回进行抽查 |
| 9 | 三连中 | 同时刻 A/B（4+4 次运行），处理组有连续 3 次运行均满足 5–7 |

---

**请指示**：我们是否推进"强化 MR 弃权边界"？一旦获批，我将先写失败测试（红）→ 实现（绿）
→ 本地回归 → 以 Lambertyan 提交 → 同时刻 A/B。
