# TR 时间范围解析 —— A/B 判决：ACCEPT（弱，方向正确）

## 结果

| 端点 | 对照 | 处理 | 判决 |
|---|---|---|---|
| eventLookup（20 题） | 46/80 | **49/80** | **+3，0 下降** —— timeRange 的直接效应 |
| TR 总体 | 75.39% | 74.02% | −1.37pp（采样噪声，见归因） |
| IE / MR / KU / ABS | — | — | 全部 n.s. |

## 归因（为何 TR 总体看似下降但变更是干净的）

`timeRange` 仅接入 `eventLookup` 分支；其他所有 TR 子类型仍使用未变更的
`buildTemporalQaPrompt`。按 `classifyTemporalQuestion` 拆分 TR 可证明
−1.75/次运行并非回归：

| 子类型 | 题数 | 对照→处理 | 由 timeRange 驱动？ |
|---|---|---|---|
| eventLookup | 20 | 46→49 (+3) | **是** |
| relative | 25 | 87→82 (−5) | 否 —— 提示词逐字节相同，纯噪声 |
| interval | 26 | 92→88 (−4) | 否 |
| ordering | 40 | 119→117 (−2) | 否 |
| other | 16 | 39→40 (+1) | 否 |

两道得到改进的 eventLookup 题朝正确方向移动：
- "…investment for a competition four weeks ago" 0/4 → 2/4
- "What charity event did I participate in a month ago?" 3/4 → 4/4

两者正是日期窗口为之而建的"在时间锚点定位事件"模式；零道 eventLookup 题回归。

## 为何在低于噪声底的情况下仍 ACCEPT

+3（≈ +0.75/次运行）低于 3 道题的实验臂内部噪声底，因此无法通过显著性检验。
仍予保留，因为：

1. **方向正确** —— 它镜像了 Hindsight 的决定性时间解析（在 LLM 之外解析限定词，
   交给它一个具体窗口），这正是 Hindsight 对 cortex 领先 +6.3pp TR 背后的机制。
2. **零下行** —— 0 次 eventLookup 回归，其他所有能力 n.s.，纯函数 + 提示词约束，
   且无轮次删除。
3. **它是时间感知检索的第一块砖**，而非整面墙。Hindsight 的全部领先需要事实级
   出现区间和日期范围检索通道，而本变更尚未构建这些。

## 诚实范围

这证实了先前的警告：单个决定性补丁产生的是小的、机制范围内的增益，总体准确率
无法分辨。与 Hindsight 剩余的 TR 差距是一次*系统性*检索架构升级，而非再多一个
提示词修复。
