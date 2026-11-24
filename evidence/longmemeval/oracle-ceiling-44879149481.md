Embedding：`openai-compatible` · 模型 `embedding-3` · baseUrl `https://open.bigmodel.cn/api/paas/v4` · 维度 1024

# Cortex 基准报告 —— `nl-abstain-feature`

- 数据集：`longmemeval+oracle`（500 题）
- 被测系统：`nl-abstain-feature` 对基线 `nl-naive-baseline`
- 生成时间：2026-11-21T07:43:07.160Z
- 特征：`nl-abstain-feature` 对基线 `nl-naive-baseline`
- 特征配置：`aggregationCritique=off`、`aggregationCritiquePerItem=off`、`candidateDiscrimination=off`、`entityIdentityClause=on`、`reranker=off`、`retrievalSides=off`
- 标注版本：`not applied`

## 消融（弃答感知准确率）

| 系统 | 最小 | 平均 | 最大 | 中位 |
|---|---|---|---|---|
| nl-naive-baseline | 83.80% | 83.80% | 83.80% | 83.80% |
| nl-abstain-feature | 89.00% | 89.00% | 89.00% | 89.00% |

- Δ 准确率（feature − baseline）：**+5.20%**
- 基线 95% Wilson 区间：**[80.31%–86.77%]**
- 处理组 95% Wilson 区间：**[85.95%–91.45%]**
- 配对 McNemar p 值：**2.556e-6**（显著：是）
- 不一致对：基线对/处理错 = 3，基线错/处理对 = 29
- Welch t 检验 p 值（跨随机重复）：**n/a（确定性）**（显著：否）
- Cohen's d：**+∞**

## 分能力拆解（`nl-abstain-feature` 臂）

| 能力 | 准确率（第 1 遍） | 题数 |
|---|---|---|
| IE | 95.33% | 150 |
| MR | 90.91% | 121 |
| KU | 86.11% | 72 |
| TR | 79.53% | 127 |
| ABS | 96.67% | 30 |

- 总体准确率（`nl-abstain-feature`）：89.00%
- 弃答率（`nl-abstain-feature`）：7.40%
- 弃答正确率（`nl-abstain-feature`）：78.38%
- `accuracyEstimator: first-repetition` —— 上面的准确率行与每一个 `questions[].correct` 都是**一遍**的读数；跨所有遍的均值是那行以「Overall accuracy over all runs」开头的数。

## 分能力配对显著性（McNemar + Wilson 区间）

| 能力 | 题数 | 基线准确率 | 处理准确率 | b✓f✗ | b✗f✓ | McNemar p | 显著 |
|---|---|---|---|---|---|---|---|
| IE | 150 | 96.67% | 95.33% | 2 | 0 | 5.000e-1 | 否 |
| MR | 121 | 90.91% | 90.91% | 0 | 0 | 1.000e+0 | 否 |
| KU | 72 | 86.11% | 86.11% | 0 | 0 | 1.000e+0 | 否 |
| TR | 127 | 80.31% | 79.53% | 1 | 0 | 1.000e+0 | 否 |
| ABS | 30 | 0.00% | 96.67% | 0 | 29 | 3.725e-9 | 是 |

### 不一致题的清单

- 基线对/处理错（3 道）：5d3d2817, 3b6f954b, gpt4_8279ba03
- 基线错/处理对（29 道）：0862e8bf_abs, 15745da0_abs, bc8a6e93_abs, 19b5f2b3_abs, 29f2956b_abs, f4f1d8a4_abs, 88432d0a_abs, 80ec1f4f_abs, eeda8a6d_abs, 60bf93ed_abs, edced276_abs, gpt4_372c3eed_abs, 2311e44b_abs, e5ba910e_abs, a96c20ee_abs, ba358f49_abs, 09ba9854_abs, gpt4_70e84552_abs, gpt4_93159ced_abs, 982b5123_abs, c8090214_abs, gpt4_c27434e8_abs, gpt4_fe651585_abs, 6aeb4375_abs, 031748ae_abs, 2698e78f_abs, 2133c1b5_abs, 0ddfec37_abs, f685340e_abs

### 每次翻转是什么性质的变化

| 翻转 | 基线 | 处理 | 计数 |
|---|---|---|---|
| recovered | 弃答 | 答对 | 0 |
| corrected | 答错 | 答对 | 29 |
| declined | 答对 | 弃答 | 3 |
| missed | 答对 | 答错 | 0 |

- **两个机制一起动了**：翻转跨过了弃答线，同时也换了内容，所以下面的净数是一个「回复形状效应」加一个「知识效应」的和，不得当作其中任何一个上报。
- 弃答流（recovered + declined）= 3，内容流（corrected + missed）= 29
- 恒等关系：recovered + corrected = 29 就是上面那个「买到」的数，declined + missed = 3 就是上面那个「卖掉」的数——这张表是那两个数的细化，不可能与它们矛盾。

## 这份读数在整条线上的位置

这是 `longmemeval+oracle` 配置——**证据只给金标轮次**——所以它是「投递不是瓶颈」时的天花板读数：
500 题 **89.00%**，其中 `IE` 95.33%、`MR` 90.91%、`TR` 79.53%。全部 +5.20 点的增量来自 `ABS`：
29 道「基线弃答、处理答对」，而 `ABS` 在基线上是 0.00%（它没有弃答许可证）。

它同时说明 oracle 不是上界而是**另一个配置**：只给金标轮次会拿走那些不是金标、但读者用来
消歧的轮次，所以 `TR` 掉到 79.53%——比当前投递下的 94.5% 低得多。**「证据完美」这四个字不能
从这份读数推出来**；能推出来的只有「换一种投递方式，各能力的反应方向不同」。
