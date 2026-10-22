# P30 —— 五个消融实验臂禁用了弃权，破坏了与评分路径的对等性

**状态：** 离线以零 API 成本发现，已修复，由五个在修复前被验证为红的测试
钉住。**本发现未授权任何重跑** —— 见 §6。

## 1. 缺陷

每一个在其两个实验臂之间保持弃权*恒定*的消融，
都把它保持在 `false`：

| 消融 | 实验臂 | 之前 | 之后 |
|---|---|---|---|
| `runMrAggregationAblation` | `mr-legacy-aggregation`、`mr-cot-aggregation` | `false` | `true` |
| `runTemporalEngineAblation` | `tr-llm-temporal`、`tr-deterministic-temporal` | `false` | `true` |
| `runDeterministicCoverageAblation` | `tr-base-engine`、`tr-extended-engine` | `false` | `true` |
| `runTimeWindowAnnotationAblation` | `tr-no-time-window`、`tr-time-window` | `false` | `true` |
| `runBitemporalKnowledgeUpdateAblation` | `ku-cot-*`、`ku-bitemporal-*` | `false` | `true` |

两个合理不同的位置未被触及：`runNaturalLanguageBenchmark`
（在那里弃权*就是*变量——基线关、功能开）和
`runAbstentionRetryAblation`（两个实验臂已经都是 `true`，正确）。

## 2. `false` 实际做了什么

`respondWith`（`natural-language-memory.ts:1138`、`:1248`）在两处对它
分支：

- 检索为空 → 返回 `'unknown'` 而不是 `null`；
- 解析后的答案是 `null`（模型拒绝）→ **发出 `abstained: false`，
  reason `'answered'`，并返回字面字符串 `'unknown'`。**

因此一个拒绝的模型不仅未被记录，它还被**重写成
一个答案形态的字符串，并记录为已作答**。所报告的
`abstentionRate` 因此被钉在 0.00%，无论模型做什么。

## 3. 它使什么失效、不使什么失效

这是值得精确的部分，因为那个诱人的主张比真实的主张更强。

**未失效：准确率零。** `'unknown'` 和一次真实弃权
都被计为错误——`abstentionAwareAccuracy` 被定义为等于 `accuracy`
（`metrics.ts:95`、`:318`），且这些 TR/KU/MR 总体中没有问题具有
`expected === null`。因此，若该标注或扩展引擎曾把一次
弃权转化为正确答案，准确率本会移动，而不一致
计数本会上升。运行 `35162802298` 在两个 TR 实验臂上的 `Δ = +0.00%` **成立**。

**失效：这次运行关于该机制所能说的一切，以及它与评分路径的对等性。**

- 两个 TR 实验臂都报告 `Abstention rate: 0.00%`，一个在构造上被钉在那里的
  数字——而 P29 测得相关亚总体的弃权率是
  19.4%（36 个未服务时间类别中的 7 个），对照 2.2%（91 个被服务中的 2 个）。
  任何把 "0.00%" 读作"未发生弃权"的人都在误读一个常量。
- 这次运行无法把*"该选项什么都没改变"*与*"该选项
  把弃权改变成了不同的错误答案"*分开——在旧设置下，
  二者是同一个观测。
- **这些实验臂不是正在被评分的那个系统。** 评分功能系统
  （`runNaturalLanguageBenchmark`）会弃权；这些实验臂不能。受测功能与
  弃权机制之间的任何交互都未被度量。

## 4. 它为什么存活

这个改动在构造上是准确率中性的——§3——因此读者
核对的任何数字都从未移动。它在消融*报告*的图中不可见，而在它必须能够报告的图中却是全部。
这与重试
消融的仅 MR 范围（P20）是同一形态：仪表读数为零是因为它被指向的东西，
不是因为那里存在的东西。

## 5. 修复以及为什么它安全

全部十个实验臂中 `enableAbstention: true`，外加记录*为什么*
该常量被保持在 `true` 而非 `false` 的文档块。显式钉住而不是
留给库默认值，这样未来一次默认值翻转就无法静默地重新启用
这个缺陷。

安全论证：

- **该常量仍然是常量。** 每个消融的两个实验臂共享该设置，
  因此每个差值仍可归因于那个唯一不同的选项。
- **未引入新的弃权机制。** 五个实验臂中没有一个设置
  `abstainThreshold`，而阈值分支以它为门
  （`natural-language-memory.ts:1153`）。只有空检索和
  解析失败分支改变，而二者此前都产生 `'unknown'`，其
  评分与 `null` 相同。准确率不变；只有报告通道
  打开。
- **`abstentionAwareAccuracy === accuracy`** 由度量模块自身
  断言，因此要点比较不可能偏移。

添加了五个测试，每个被改动的对一个，每一个断言一个返回
`UNANSWERABLE` 的模型**在两个实验臂中**都产生 `abstentionRate > 0`：

```
runMrAggregationAblation > records a declined answer as an abstention in both MR arms
runTemporalEngineAblation > records a declined answer as an abstention in both TR-engine arms
runTimeWindowAnnotationAblation > runs with abstention enabled, so the population it exists to explain is observable
runDeterministicCoverageAblation > runs with abstention enabled, so weekday-anchored resolution can be observed
runBitemporalKnowledgeUpdateAblation > records a declined answer as an abstention in both KU arms
```

全部五个在修复前**被验证为红**，方式是在 `runner.ts` 中把 `enableAbstention:
true` → `false` 回退并重跑：5 个失败。恢复后，5 个通过。
MR 那个还额外钉住：自定义 `aggregationPrompt` 的选择退出
（`abstentionRetryAllowed`）只抑制*重问*，不抑制*记录*——
两个不同的开关，容易被混为一谈。

修复后的门：**952 个测试绿色**（cortex-core 87、cortex-node 16、
cortex-llm 43、cortex-eval 806）；cortex-eval 中覆盖率为 99.88 / 98.71 / 100 / 99.88，
任何地方的最低 branch 数字为 97.26%。

## 6. 处置：不重跑

重跑以在两个 TR 实验臂上收集 `Δabstention` 会花费一次完整运行而
不改变任何决定——准确率零成立（§3），因此 `extendedTimeRange` 和
`enableTimeWindowAnnotation` 在评分路径上都保持关闭，恰好与它们
现在一样。`bench/run.ts` 在**每一次**分派时执行所有这些实验臂，因此下一次
运行会以零边际成本在通道打开的情况下重新度量它们。把这
折进下一次被授权的实验，严格优于为它花一次运行。

## 7. 这如何改变此处对零的读法

已有两个零被追溯到仪表范围而非功能：P20
（仅 MR 的重试范围）和这一个。此后的常设规则：

> 在把一个 `Δ = +0.00%` 读作关于一个功能的证据之前，检查该实验臂
> 是否能够*表达*该功能会改变的结果。如果报告说某个
> 在结构上并非被强制为零的量是 `0.00%`，那它是一次
> 测量；如果它在结构上被强制，那它是一个披着
> 测量外衣的配置事实。
