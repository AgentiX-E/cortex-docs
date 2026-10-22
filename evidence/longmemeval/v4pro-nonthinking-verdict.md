# V4-Pro Non-Thinking 诊断运行 — 判决：NEGATIVE（劣于 V4-Flash）

## 摘要

| 读取器 | 配置 | 总体 | 判决 |
|---|---|---|---|
| V4-Flash | non-thinking（`deepseek-chat`） | **83.95%**（RRF 基线，4 次运行） | 参照 |
| **V4-Pro** | **non-thinking**（`deepseek-v4-pro`，`thinking:disabled`） | **78.40%**（1 次运行） | **−5.55pp，在每一个能力上均更差** |

V4-Pro 在 **non-thinking 模式下系统性地劣于** V4-Flash 的 non-thinking 模式。所谓“更大的读取器必然更好”的假设并不成立：V4-Pro 是一个以推理为优化目标的旗舰，其价值存在于 thinking 模式，强行将其置于 non-thinking 会损害指令遵循能力。

## 逐能力（相同 RRF 架构，单次运行 vs 4 次运行基线）

| 能力 | V4-Flash non-thinking | V4-Pro non-thinking | Δ |
|---|---|---|---|
| IE | 94.50% | 88.67% | **−5.83pp** |
| MR | 79.55% | 77.69% | −1.86pp |
| KU | 81.25% | 75.00% | **−6.25pp** |
| TR | 73.43% | 69.29% | **−4.14pp** |
| ABS | 100.00% | 76.67% | **−23.33pp** |
| **总体** | **83.95%** | **78.40%** | **−5.55pp** |

## 根因（有证据支撑，非推测）

单一失败模式是 **non-thinking 模式下的指令遵循能力退化**，以三种具体方式显现：

1. **过度生成 / 冗长（IE，14/14 个错误答案均为 LLM 过度作答）。**
   - “What did I buy for my sister's birthday gift？” 金标 `'a yellow dress'` →
     V4-Pro 回答 `'A yellow dress and a pair of earrings to match'` — 正确事实
     确实出现了，但额外附加了一个错误事实，因此评判器将其判为错误。
   - 偏好类问题（“Can you recommend……”、“Any tips……”）金标是简短的
     `“The user would prefer……”` 句子；V4-Pro 产出一篇长篇论述，偏离了金标措辞。

2. **在该弃权时未能弃权（ABS，最灾难性的回归）。**
   - V4-Flash 在 ABS 上弃权 30/30。V4-Pro 仅弃权 23/30：在 7 道不可回答的
     题目上它强行作答而非弃权，且这 7 道全部错误。

3. **在 TR/KU 上有更多 LLM 层面的错误**（20 个 TR + 10 个 KU 错误答案由 LLM
   生成，此外还有 20 个无论读取器为何都完全相同的确定性引擎错误）。

决策理由证实了弃权上的变化：`answered 459 / llm-abstain 40 /
threshold 1` — V4-Pro 回答了 500 道题中的 459 道，远比 V4-Flash 激进，而正是这些额外的作答使它失分。

## 为何这是一个有价值的负面结果

这纠正了我早先引入的一个错误前提：我曾断言“剩余差距是 DeepSeek 读取器的天花板，更强的读取器是唯一的杠杆”。这在两方面都是错的：

1. 早先的运行使用 `deepseek-chat` = **V4-Flash non-thinking**，即*最底*层级，
   而非“DeepSeek 的全部能力”。
2. 但*修复*方式**并非**简单地切换到 V4-Pro — V4-Pro 的 **non-thinking**
   实际上更差。V4-Pro 的强项是 **thinking 模式**（其 49B 激活量的 MoE 针对
   思维链推理而优化），而这一点我们尚未测量。

## 下一步（建议，尚未执行）

解锁 V4-Pro 真实能力的唯一剩余路径是 **V4-Pro + thinking 模式**
（`DEEPSEEK_THINKING=enabled`，已在 `dcb970d` 中作为环境开关接好）。这需要两项
当前测试装置所缺乏的条件：

1. **更长的单次尝试截止时间。** `DEFAULT_RETRY_TIMEOUT_MS = 60_000` 对于
   thinking 模式推理而言远远不够（在大型检索上下文下测得每次调用 20–200s）。
   对于 thinking 实验必须提高到约 300s。
2. **成本容忍度。** 推理 token 按输出 token 计费（$0.87/M）；该基准约 500 道题
   × 每题多次 LLM 调用，成本将显著高于 non-thinking。

如果测量了 thinking 模式且其表现亦不及 V4-Flash，那么正确的最终答案是：
**V4-Flash non-thinking 的 83.95% 是这个基准的正确读取器**，而 SOTA 差距是
提示/架构的天花板，而非读取器层级的天花板。
