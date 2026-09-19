# 同瞬 A/B 结论：P0 修复不完整，且它引入了一处回归

**底线先行**

1. **P0（`8d87341` CoN 输出契约）不能被评为“通过”。** 它确实消除了目标缺陷（叙述泄漏 6.81% → **0.00%**，逐题精确 McNemar **p = 2.9e-11**），但与此同时它**把 LongMemEval-S 那 29 道 `single-session-preference` 题上的弃权率从 3.45% 推高到 21.84%（+18.39pp）**。一得一失大致相抵：IE 净 −1.11pp，总体净 +0.73pp，且**在运行层面两者都不显著**。
2. **我上一份报告“方差收敛 F=112.0，p=0.0177”的结论必须撤回。** 那是一个正态理论 F 检验在 df=(2,2) 下过度自信。改用精确置换检验（C(6,3)=20 种分配）：**均值 p=0.50，最差运行 p=0.40，极差 p=0.10，弃权均值 p=0.10** —— 在运行层面**没有任何一项显著**。
3. **根因已定位，而它是我自己引入的一个可修复的 BUG**：`buildPreferencePrompt` 一次发出三条互相矛盾的指令。修复计划是下面的 P0-b。
4. 更大面积的杠杆仍是 **MR 确定性聚合**（上限 MR +13.6pp / 总体 +2.3pp），安排在本迭代之后。

---

## 1. 运行层面：同瞬 A/B 什么都证明不了

6 次运行在 **14 秒之内**同时调度（对照 `7a349da`，处理 `8d87341`），全部 `success`。

| 指标 | 对照 `7a349da` | 处理 `8d87341` | Δ | Welch p |
|---|---|---|---|---|
| 总体 | 77.53% | 78.27% | **+0.73pp** | 0.408 |
| 弃权率 | 17.67% | 15.13% | −2.53pp | 0.052 |
| IE | 90.89% | 89.78% | −1.11pp | 0.382 |
| MR | 63.91% | 66.94% | +3.03pp | 0.306 |
| KU | 75.46% | 77.31% | +1.85pp | 0.345 |
| TR | 70.60% | 71.13% | +0.52pp | 0.640 |
| ABS | 100.00% | 98.89% | −1.11pp | 0.423 |

### 精确置换检验（无分布假定，C(6,3) = 20 种分配）

| 统计量 | 观察值 | 置换 p |
|---|---|---|
| 总体均值差 | +0.733pp | **0.500** |
| 总体最差运行 | +2.000pp | 0.400 |
| 总体极差（处理 − 对照） | −2.200pp | 0.100 |
| 弃权均值差 | −2.533pp | 0.100 |
| 弃权极差 | −1.800pp | 0.400 |

**在 n=3 时 F 检验的 p=0.0177 不可信**；精确置换检验的分辨率上限是 1/20 = 0.05，而没有任何统计量触及它。

### 对功效的真正约束（这必须写进此后每一次迭代的设计）

| 端点 | 运行/实验臂 | 最小可检测效应（80% 功效，α=.05） |
|---|---|---|
| 总体（运行层面，取保守的对照 sd = 1.00pp） | 3 | **±2.3pp** |
| 总体（同上） | 6 | ±1.6pp |
| IE（逐题配对，n=74 可确定性判定） | 3 | ±4.52pp |
| MR（逐题配对，n=105） | 3 | ±5.35pp |
| KU（逐题配对，n=43） | 3 | ±3.11pp |
| TR（逐题配对，n=65） | 3 | ±6.13pp |

> **方法学结论**：本仓库的 CI A/B **在运行层面无法检测低于 2pp 的总体改善**。因此**此后迭代的主要端点必须是机制端点**（确定性、逐题、高功效）；总体仅作为带 CI 的描述性估计和非劣性护栏，不作为显著性检验。

---

## 2. 题层面：该缺陷确实被消除了（n = 470 × 3 = 每臂 1410）

产物携带每道题的 `llmRaw`，因此机制可以在**题**层面而非运行层面度量。

| 端点 | 对照 | 处理 | 检验 |
|---|---|---|---|
| **格式崩坏**（写了 Step 1 然后停下，无 `Answer:` 行） | 6.81% (96/1410) | **0.00% (0/1410)** | 精确 McNemar **p = 2.9e-11** |
| 其中 IE | 18.22% | 0.00% | |
| 其中 TR | 3.67% | 0.00% | |
| 其中 MR / KU | 0.00% | 0.00% | 提示词不同，本就不可达 |
| **弃权率** | 12.41% | 9.79% | 精确 McNemar **p = 0.0133** |
| 答案长度 p99 | 2419 字符 | **259 字符** | |
| 答案长度最大 | 3340 字符 | **427 字符** | |
| 答案 >200 字符 | 120 | **29** | |
| 跨运行答案翻转率：**曾经崩坏过的题** | **36/36 = 100%** | 无（0 道题崩坏） | |
| 跨运行答案翻转率：从未崩坏过的题 | 93/434 = 21.4% | 98/470 = 20.9% | |

机制链条完整且可复现：**崩坏 → 该题在 3 次运行之间必然给出不同答案（100% 翻转对 21.4% 基线）→ 运行间方差**。处理实验臂把崩坏降到零，翻转率回落至基线。**P0 的这一部分是对的。**

---

## 3. 但是：P0 在生成式题上引入了一处回归

LongMemEval-S 的 150 道 IE 题**自然分成两簇**：

- **抽取式（121 道）**：金标准是历史中的一个事实 —— `"Business Administration"`、`"Denver"`、`" bronchitis"`。
- **生成式（29 道）**：金标准是 `"The user would prefer responses that build upon / take into account / draw upon …"` —— 答案必须**从偏好中推断**，而非照抄。这 29 道题正是数据集 `questionType = single-session-preference` 路由到 `buildPreferencePrompt` 的那一批。

### 按簇的弃权率

| IE 组 | n | 对照弃权 | 处理弃权 | Δ |
|---|---|---|---|---|
| **抽取式** | 121 | 7.99% | 3.03% | **−4.96pp（收益）** |
| **生成式（偏好）** | 29 | 3.45% | **21.84%** | **+18.39pp（回归）** |
| 每次运行弃权的题数 | | 1.00 | 6.33 | **+5.33 道题/次运行** |

净账：抽取式每次运行少弃权 6.00 道题，生成式每次运行多弃权 5.33 道题 → IE 净 −0.67 道题/次运行，与观察到的 −1.11pp 一致。

**稳定性**：在那 29 道生成式题中，**27 道（93.1%）在 3 次处理运行之间给出完全相同的判决**；其中 5 道 3/3 弃权（对照实验臂只有 1 道）。这不是随机抖动，而是一次**确定性的行为改变**。

### 根因：`buildPreferencePrompt` 发出三条互相矛盾的指令

```
conInstruction()  →  "Step 2 — Answer the question using ONLY those identified facts."
buildPreferencePrompt → "In Step 2, produce a CONCRETE, SPECIFIC recommendation or
                         suggestion that directly reflects those preferences."
conInstruction()  →  "Answer: <a word, name, number, or short phrase>"
```

- 第二条与第一条矛盾：**“推断一个新的推荐”对“只使用所识别的事实”。**
- 第二条与第三条矛盾：**一个具体的推荐不可能是“一个词/名称/数字/短语”。**

**P0 之前，模型通过写出 Step 1 然后停下逃开了这一矛盾** —— 那就是叙述泄漏。P0 堵住了那个逃生口，于是模型转而用**弃权**来解决这一矛盾。抽样的 6 道受害题全是推荐/建议类，金标准在每一种情况下都以 `"The user would prefer responses that build upon …"` 开头，且处理实验臂 16/18 次弃权。

所以：**P0 治好了症状，并暴露了病灶。**

---

## 4. P0-b 计划：让 CoN 契约区分“抽取”与“推断”

### 设计

把 CoN 契约参数化，**默认逐字保留今日的抽取式契约**，只把 `buildPreferencePrompt` 换成一个推荐契约。其余三个调用点（`buildQaPrompt`、`buildTemporalQaPrompt`、`buildTemporalEventLookupPrompt`）保持**逐字节不变**，从而锁定已测得的抽取式收益（−4.96pp 弃权）。

```ts
interface AnswerContract {
  /** What Step 2 must produce. */
  step2: string;
  /** Lines pinning the exact shape of the reply. */
  reply: readonly string[];
  /** Longest unlabelled answer admitted before the runaway safety net fires. */
  maxUnlabelledChars: number;
}

const EXTRACTIVE_CONTRACT: AnswerContract = {
  step2: 'Step 2 — Answer the question using ONLY those identified facts.',
  reply: [
    'Your entire reply is one line in exactly this form, with nothing before or after it:',
    'Answer: <a word, name, number, or short phrase>',
  ],
  maxUnlabelledChars: 200,
};

const RECOMMENDATION_CONTRACT: AnswerContract = {
  step2: 'Step 2 — Recommend something concrete that builds on those identified preferences.',
  reply: [
    'Your entire reply is one line in exactly this form, with nothing before or after it:',
    'Answer: <a specific recommendation, one to three sentences, naming the exact options>',
  ],
  maxUnlabelledChars: 400,
};
```

- `conInstruction(contract: AnswerContract = EXTRACTIVE_CONTRACT): string[]`
- `parseQaAnswer(raw, abstainToken)` **保持其签名与默认行为不变**；新增一个可选第三参数 `maxUnlabelledChars`。
- 新增 `parseRecommendationAnswer(raw, abstainToken)`，以 400 字符的上限委托给 `parseQaAnswer`。
  > 理由：安全网的目的是**截断失控生成**（历史最差 33,504 字符），而不是截断好答案。一段 1–3 句的具体推荐合法地超过 200 字符；当前 200 字符的上限已在截断推荐答案（处理实验臂有 29 个答案 >200 字符）。
- `answerPreference` 切换到 `parseRecommendationAnswer`。

### 验收标准

**A. 代码质量（本地，push 前全部绿）**
1. **TDD**：先写失败测试（红），再实现（绿）。
2. **≥ 15 项新测试**，覆盖：
   - `buildPreferencePrompt` 不再包含 `"using ONLY those identified facts"`
   - `buildPreferencePrompt` 不再包含 `"a word, name, number, or short phrase"`
   - `buildPreferencePrompt` 包含推荐型的 `Answer:` 契约
   - **回归锁定**：`buildQaPrompt` / `buildTemporalQaPrompt` / `buildTemporalEventLookupPrompt` 的 Step 2 行与回复契约与 `8d87341` **逐字相等**
   - `parseRecommendationAnswer`：保留一个 ≤400 字符的 3 句推荐，把失控生成截断到第一句，剥离脚手架，弃权时返回 `null`，优先取 `Answer:` 标签
   - `parseQaAnswer` 的默认上限仍为 200（行为未变）
3. **四个覆盖率维度均 ≥ 95%**（当前：语句 99.73% / 分支 97.53% / 函数 100% / 行 99.73%）。
4. `lint` / `format:check` / `typecheck` / 全套测试 / `build` 全部通过。

**B. 同瞬 A/B（每臂 4 次运行，8 个并发约 55 分钟，对照 = `master` 即 `8d87341`）**
5. **主要端点（机制、确定性、无评判器噪声）**：**偏好题弃权率**从 21.84% 降到 **≤ 8%**，逐题精确 McNemar **p < 0.05**。功效：≥ 0.95（每臂 4 次运行，n=116/臂）。
6. **非劣性护栏**：IE 不得低于对照 −1.0pp；总体不得低于对照 −1.0pp。
7. **非回归护栏**：4 次处理运行中，**470 道诊断题的格式崩坏率必须保持 0.00%**；解析出的最长答案 ≤ 500 字符。
8. **描述性**（非阈值）：忠实记录总体 Δ 及其 95% CI —— 在运行层面，每臂 4 次运行的 MDD 约为 **±2.0pp**，**不足以做显著性检验**。
9. 上述第 5–7 项必须由 **4 次处理运行各自独立满足**，而非仅仅在聚合上满足。

**C. 提交**
10. 以 `Lambertyan <lambertyan@agentix-e.dev>` 提交并推送；注释、文档与提交注释全部为英文；**任何 API 密钥都绝不得出现在代码中**。

### 预期收益

偏好弃权从 6.33 道题/次运行回落到约 1.0 道题/次运行（对照水平），释放 **约 5.33 道题/次运行**。那些题此前全被判定为错误；若恢复作答后评判器接受率为 50–70%，则 IE **+1.8 ~ +2.5pp**，总体 **+0.54 ~ +0.74pp**。这仅仅是**修复我自己造成的一处回归**，而非净增。

---

## 5. 后续杠杆排序

| 迭代 | 内容 | 上限 | 所需运行 | 主要端点 |
|---|---|---|---|---|
| **P0-b**（本轮） | 生成式 CoN 契约 | IE +2.5pp / 总体 +0.74pp | 4+4 | 偏好弃权率（功效 ≥0.95） |
| **MR 确定性聚合** | `parseAggregationItems` + `aggregateItems`，COUNT/SUM 在代码中计算 | **MR +13.6pp / 总体 +2.3pp** | 6+6（MDD 3.78pp） | MR 逐题配对准确率（105 道可确定性判定的题） |

MR 证据（已量化）：证据召回率 94.7%；**在被确定性判定为错误的 MR 答案中，73.7% 的证据被全部召回**（聚合/算术失败），检索失败只占 2.6%。错误分解：COUNT n=141（准确率 75.9%，34 个错误中 25 个是算术），SUM n=116（87.1%，15 个错误中 10 个是算术）。

**更远处**：KU 的潜在不一致（`buildKnowledgeUpdatePrompt` 让模型写一个枚举，却走 `parseQaAnswer`，后者会剥离列表）。已确认当前**不活跃**（216 个 KU 输出零列表，最长 48 字符），低优先级，不单独开运行。

---

## 附录：本次新增的分析脚本

| 脚本 | 用途 |
|---|---|
| `question_level_ab.py` | 逐题（n=470）分组统计：崩坏 / 弃权 / 确定性准确率 / 翻转率 / 长度尾部 |
| `question_level_ab2.py` | 逐题显著性检验（精确 McNemar）、崩坏题归因、TR 深入探查 |
| `perm_and_mechanism.py` | 精确置换检验（替代 F 检验）+ 弃权–准确率机制相关性 |
| `proxy_validation.py` | token-F1 代理指标的校准（Cohen's d = 1.132） |
| `proxy_ie.py` | 在 IE 子集内重新校准代理指标，发现两簇 |
| `generative_ie.py` | 生成式与抽取式的分簇，量化该回归 |
