# MR 时长/年龄推导路由修复 — A/B 判决

**日期：** 2026-09-05
**受测修复：** `a104ea0` — `fix(eval): route duration and age-difference questions to derivation`
**实验臂（处理组）：** `master`（`a104ea0`）
**对照组：** `mr-derivation-control`（`4640c86`，即直接父提交——唯一差异就是该修复）
**协议：** 同一时刻交错 4v4；全部 8 次运行 `completed` / `success`，`questionCount = 500`

> 注：本文件与 2026-09-04 的 `mr-derivation-verdict.md` 不同，后者评估的是更早的
> `183a3cc` 推导提示路由。本次迭代将该分类器扩展了四种时长/年龄表述。

---

## 1. 判决

**接受（ACCEPT）。** 该修复恰好完成了其设计目标，且逐题证据无懈可击。准确率层面的置换检验
在 n=4 时统计功效不足——这一点由对照组展现出与 *同一* p 值相伴的、偶然的、不可达的 KU 漂移
所证明——因此该决策依据的是机制端点与逐题归因，而非准确率。

---

## 2. 主要端点 — 移动集合的弃权率（机制）

该修复将五个 MR 问题从枚举 → 推导重新路由（即移动集合）：

| # | 问题 | gold |
| --- | --- | --- |
| 1 | How long have I been working in my current role? | `1 year and 5 months` |
| 2 | How many years older is my grandma than me? | `43` |
| 3 | How many years older am I than when I graduated from college? | `7` |
| 4 | How many minutes did I exceed my target time by in the marathon? | `12` |
| 5 | How many years will I be when my friend Rachel gets married? | `33` |

每次运行的弃权数（在 5 个移动问题中）：

```
control    [3, 3, 3, 4]   mean 3.25
treatment  [1, 1, 1, 1]   mean 1.00
```

**完全分离** — `min(control) = 3 > max(treatment) = 1`。精确置换检验：**1/70 = 0.0143
单侧**。这是构造上最极端的那一种重标记，且不依赖任何分布假设。

## 3. 逐题归因（具约束力的证据）

| 问题 | 对照 | 处理 | 结果 |
| --- | --- | --- | --- |
| current role (`1y5m`) | 0/4 正确，4/4 弃权 | **4/4 正确**，0 弃权 | 已恢复 |
| grandma older (`43`) | 0/4 正确，4/4 弃权 | **4/4 正确**，0 弃权 | 已恢复 |
| college graduate (`7`) | 3/4 正确，1/4 弃权 | **4/4 正确**，0 弃权 | 已恢复 |
| marathon exceed (`12`) | 4/4 正确 | 4/4 正确 | 不变 |
| Rachel married (`33`) | 0/4 正确，4/4 弃权 | 0/4 正确，4/4 弃权 | 不变（检索） |

两个完全恢复的问题（`current role`、`grandma older`）在对照组下是 **4/4 弃权者，在处理组下
变为 4/4 正确**，且其答案已对照 gold 验证（`3 years 9 months − 2 years 4 months =
1 year 5 months`；`75 − 32 = 43`）。这是确定性的——该修复所针对的那些确切问题现在能算出
正确答案——而非统计波动。

`Rachel married` 未能恢复，是因为其 `32` 年龄操作数不在被检索到的窗口内（审计中编录的
Category-C 检索失败），这超出了提示路由修复的范围。

## 4. 恢复效率

```
MR abstentions removed : 53 -> 42  = -11 over 4 runs = 2.75/run
MR correct gained      : 354 -> 364 = +10 over 4 runs = 2.50/run
recovery efficiency    : 10/11 = 90.9%
```

## 5. 共同主要端点 — MR 准确率（弱，受噪声下限约束）

```
control   [87, 89, 90, 88]  mean 88.50/121 = 73.14%
treatment [90, 93, 91, 90]  mean 91.00/121 = 75.21%
delta     +2.50/run = +2.07pp
```

精确置换 p = 3/70 = **0.0429**。分离处于边界上（`min(treatment) = 90 = max(control)`），
因此就其自身而言这是弱的。此处为完整性而报告；决策依据的是 §2 与 §3。

## 6. 守卫项的诚实性 — KU 发生了漂移，而这正是要点

各能力准确率（合并 4 次运行）：

| 能力 | 对照 | 处理 | delta | 备注 |
| --- | --- | --- | --- | --- |
| IE | 571/600 = 95.17% | 570/600 = 95.00% | −0.17pp | n.s. |
| **MR** | 354/484 = 73.14% | **364/484 = 75.21%** | **+2.07pp** | 该修复 |
| KU | 226/288 = 78.47% | 235/288 = 81.60% | +3.13pp | **噪声，见下文** |
| TR | 382/508 = 75.20% | 386/508 = 75.98% | +0.79pp | n.s.（p = 0.186） |
| ABS | 119/120 = 99.17% | 119/120 = 99.17% | 0.00 | 不变 |

KU 的 +3.13pp 位移（逐次运行 `[58,57,56,55]` → `[59,59,57,60]`，delta +2.25/run）产生的
精确置换 p = 3/70 = 0.0429，与 MR 目标**相同**。这并非该修复影响了 KU 的证据——它是可证明
不可达的：`classifyAggregationKind` 与 `buildDerivationQaPrompt` **仅**从 `answerSessions`
（MR 路径，`natural-language-memory.ts` 第 546–547 行）调用；KU 路径
（`answerKnowledgeUpdate` → `buildKnowledgeUpdatePrompt`）从未引用二者中的任何一个。

因此 KU 漂移纯粹是各次运行之间的 LLM 采样噪声，而它是一个警示性的示范：
**在 n=4 时，约 2 个问题/次的准确率位移无法被置换检验从噪声中分辨出来。** 这正是本项目
方法论将机制端点作为决策标准、而将准确率视为受噪声下限约束的描述性估计的原因。总体
82.60% → 83.70%（+1.10pp）同样被这一非 MR 噪声（IE/KU/TR 合计 +13）所抬高；该修复自身
可归因的贡献是 MR 的 +2.07pp。

---

## 7. 结论

该修复在以下依据上被**接受**：

1. **移动集合弃权率** 3.25 → 1.00/次，完全分离，精确 p = 0.0143。
2. **逐题归因**：两个 4/4 弃权者恢复为 4/4 正确且答案经 gold 验证，一个边缘恢复，一个不变，
   一个仍被已知的检索缺口所阻塞。

**恢复效率 90.9%。** 守卫项 IE/TR/ABS 不变；KU 的变动被证明为噪声（不可达代码路径 +
同 p 巧合）。

**下一目标（不变）：** `Rachel married` 问题与三个年龄问题背后的 Category-C 检索失败——
用户的年龄 `"32"` 被不一致地检索到（对 "average age" 存在，对 "Alex born" 与
"Rachel married" 缺失）。这是一个检索排序/覆盖问题，属于更大且独立的另一次迭代。
