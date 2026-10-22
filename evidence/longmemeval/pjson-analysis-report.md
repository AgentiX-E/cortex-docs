# P-json（CP4 后半：JSON 结构化上下文）基准分析报告

- 处理组：`7a349da` —— `formatStructuredContext()` 把检索上下文渲染为一个 JSON 回合数组
- 对照组：`da4fe96` —— CP4 前半（Chain-of-Note 指令 + `parseQaAnswer` 标签抽取）
- 数据集：LongMemEval-S 完整 500 道题（IE 150 / TR 127 / MR 121 / KU 72 / ABS 30）
- 评估协议：每实验臂 3 次运行，**同一天**（对照组 2026-09-03 01:38Z，处理组 03:22Z，相隔 1.7 小时，避免 DeepSeek 跨日漂移）
- 评估系统：`nl-abstain-feature`（带弃权的系统；`nl-naive-baseline` 从不弃权，因此其 ABS 永远是 0% 且不可比）

---

## 1. 底线先行

**P-json 有效；保留它。** 总体 **77.20% → 78.27%（+1.07pp）**，且**即便最差的一次运行也提升了**（最低 76.60% → 77.80%）。IE 提升了 **+2.67pp 且统计显著**（Welch p = 0.033）。

**但该实验暴露了一个此前隐藏的 P0 级 bug：Chain-of-Note 格式契约在 7.5% 的题上完全失效** —— 模型只输出 Step 1 的叙述，从不写出 `Answer:` 行，且答案字段被整块思考污染。P-json 把这一失效率从 5.2% 推高到 7.5%（+45%）。这目前是**最大的单一可解锁收益**所在的问题，且应在讨论任何其他优化之前修好。

---

## 2. 主要指标（3 次运行，特征系统）

| 指标 | 基线 `da4fe96` | P-json `7a349da` | Δ (pp) | Welch t | p 值 | 判决 |
|---|---|---|---|---|---|---|
| **总体** | 77.20%（std 0.43） | **78.27%**（std 0.34） | **+1.07** | 2.74 | 0.0549 | 边缘（接近显著） |
| IE | 86.22% | **88.89%** | **+2.67** | 4.24 | **0.0327** | **显著** |
| KU | 76.39% | 78.70% | +2.31 | 1.25 | 0.2804 | 不显著 |
| MR | 67.49% | 67.77% | +0.28 | 0.38 | 0.7250 | 不显著 |
| TR | 71.13% | 70.60% | −0.52 | −0.53 | 0.6401 | 不显著（回归未被确认） |
| ABS | 98.89% | 98.89% | 0.00 | 0.00 | 1.0000 | 未变 |
| 弃权 | 17.67% | 17.00% | −0.67 | −1.25 | 0.3161 | 不显著 |

逐次运行细节：

| 运行 | 基线总体 | P-json 总体 |
|---|---|---|
| #1 | 77.40% | 78.40% |
| #2 | 76.60% | 77.80% |
| #3 | 77.60% | 78.60% |
| 平均 | 77.20% | **78.27%** |

题级配对 McNemar（470 道题有诊断数据；只有判决的精确匹配 + 数值档可复现，因为 LLM 评判器无法离线重放）：9 个同日配对上的 p 值范围为 **0.337 – 0.690，中位数 0.473** —— 在确定性判断层面两个实验臂没有差异，表明这 +1.07pp 的增益主要落在需要评判器语义判决的题上（JSON 上下文使答案措辞更接近金标准的语义）。

与论文基线的比较：长上下文 GPT-4o 60.6%、ChatGPT+GPT-4o 57.7%（两者均已被超越）、Oracle（GPT-4o 全文）91.8%，当前差距 13.5pp。

---

## 3. P0 Bug：Chain-of-Note 格式契约的故障分解

### 3.1 症状

`conInstruction()` 上的注释说 Step 1 应“在脑中识别相关细节，而非把它们写出来”。但**指令文本本身并没有这样说**：

```
Step 1 — Read each turn and identify the user's facts, events, values, or preferences relevant to the question.
Step 2 — Answer the question using ONLY those identified facts.
```

模型逐字遵循它，把 Step 1 完整写出来然后停下，从不进入 Step 2。结果：

| 指标 | 基线 | P-json | 变化 |
|---|---|---|---|
| 泄漏答案 / 次运行（470 道题） | 26 / 25 / 22（均值 24.3，**5.2%**） | 33 / 36 / 37（均值 35.3，**7.5%**） | **+45%** |
| 按能力码的泄漏（3 次运行合并） | IE 58 + TR 15 = 73 | IE 83 + TR 23 = **106** | +45% |
| 输出了 `Answer:` 行的泄漏题 | 0 | **0 / 33** | 无 |
| 答案 > 1000 字符（3 次运行合并） | 72（最长 3299） | 86（**最长 33504**） | +19% |

### 3.2 证据样本

题 1（TR，P-json 净回归的直接证据）：
- Q：`Which airline did I fly with the most in March and April?` / GT：`United Airlines`
- 基线答案：`United Airlines.` ✅
- P-json 答案：`Step 1 — Relevant turns and dates:\n- 2023/04/27: User mentions a March business trip to Chicago with United Airlines (flights on the 10th and 12th...)…` ❌

题 2（失控生成，`gpt4_9a159967`）：对同一道题，P-json 输出了 **33,504 个字符**，模型困在自言自语的自循环中：
```
Given the data, the most flights are with United and American, each 4. So the answer is a tie.  ← repeated 23 times
Given the context, the user flew United in March (4 flights) and American in April (4 flights). So the most is a tie. ← repeated 23 times
TAIL: 'Given the instruction to answer with ONLY the final answer, I'll say "United and American (tie)" but that might be considered not a single answer.\n\nAlternatively'
```

题 3（TR）：`Did I visit with a friend or not?` / GT：`No, you did not visit with a friend.` → 基线 `No.`，P-json 输出了 Step 1 的叙述。

### 3.3 为何 P-json 使它更糟

JSON 结构化上下文把每个回合的 `date`/`role`/`content` 变为显式数据字段，这**使摘录事实极其容易** —— 模型在 Step 1 中找到一种低成本的“成功感”，因此更彻底地沉浸其中，甚至不进入 Step 2。这解释了为何 IE（偏好题，事实点最多）泄漏最重，TR（最机械的日期摘录）次之，而 MR / KU（经过聚合 / 双时间引擎，答案短而确定）零泄漏。

### 3.4 该修复收益的诚实界限

在 P-json run1 的 33 道泄漏题中，**只有 4 道在叙述中逐字包含金标准字符串**。因此：
- 只改解析器（从叙述中钓出答案）收益有限，且**不能成为主要修复**
- 必须从提示词侧恢复格式契约，使模型根本不写 Step 1

---

## 4. 下一次迭代计划：P0 —— 恢复 CoN 输出契约

### 目标

消除 CoN 叙述泄漏，把答案恢复到短语形态，解锁被它埋没的 IE / TR 准确率，并同时消除失控的长生成。

### 具体改动（3 项）

1. **`conInstruction()`**（根因修复，对齐注释与措辞）：
   - 显式约束 Step 1：`"Step 1 — Silently read each turn and identify the relevant facts. Do NOT write these notes down."`
   - 追加最终输出契约：`"Finish your reply with a final line in exactly this form: Answer: <short answer phrase>"`
   - 限定 Step 1 的长度：`"If you must note anything, use at most 5 bullets of at most 12 words each."`

2. **`parseQaAnswer()`**（防御性回退，而非提示词修复的替代）：
   - 优先取 `Answer:` 标签行（已存在，保留它）
   - 新增：没有标签时，剥离以 `**Step` / `#` / `- ` / `* ` 开头的叙述行与列表行，并取第一个剩余的非空内容片段
   - 新增：长度断路器 —— 没有 `Answer:` 行且答案超过 200 字符时，在第一处句末截断（阻止那 33,504 字符的失控输出抵达评分）

3. **TR 时间提示词，具体地**：把 Step 1 的措辞收紧为 `"silently identify the turns and their dates"`，并保留既有约束 `"answer with ONLY the final answer (a number, date, or short phrase)"`。

### 验收标准

| # | 验收项 | 阈值 |
|---|---|---|
| 1 | 单元测试 | ≥ 8 个新用例覆盖泄漏形态；四维覆盖率 **≥ 95%**（无 mock，真实断言） |
| 2 | 泄漏率 | 470 道诊断题中的泄漏答案 **< 1%**（当前 7.5%） |
| 3 | 失控生成 | 答案 > 1000 字符者 **每 3 次运行 < 10**（当前 86）；最长答案 **< 1000 字符** |
| 4 | 总体 | **≥ 78.27%**（不得相对当前回归），同日 3 次运行，Welch **p < 0.05** |
| 5 | IE / TR | IE **≥ 88.89%**，TR **≥ 71.13%**（TR 必须收复那 −0.52pp） |
| 6 | 回归 | push 前 lint / format / typecheck / 全套测试 / CI 冒烟全部绿 |
| 7 | 三重命中 | 连续 3 次运行均达阈值；单次命中不算成功 |

### 预期收益（粗略估计，须经验验证）

以每次运行 35 道泄漏题计，若 70% 被契约修复、其中 60% 转化为正确答案 → 约 +15 道题 ≈ **+3pp**；在此之上，TR 收复 −0.52pp。目标区间 **总体 80%–81%**。这是一个估计，不是一个结论。

---

## 5. 待办：MR 仍是最大的弱点

MR 为 67.77%，是五个能力维度中唯一低于 70% 的。MR 走聚合提示词，零泄漏且答案极短（均值 4.4 字符），这表明 CoN 泄漏不是它的问题，瓶颈是**多会话聚合/计数**本身。建议在 P0 修复被验证之后，另行划定一次根因分析（检索召回对聚合计数）。
