# 年龄操作数检索失败 — 深度审计 + 修复计划

**日期：** 2026-09-05
**实验臂：** 处理组（`a104ea0`）
**范围：** 答案需要用户年龄 `"32"` 的 MR 问题

---

## 1. 修正后的事实表（修正了此前两处误读）

早先一轮统计的是字符串 `"32"`，被**时间戳噪声**误导（`[2023/05/25 12:32]` 中含有
`32`）。限定为真实的年龄表述（`turned 32`、`I'm 32`、`age 32`、`32 years old` 等）后得到：

| 问题 | 金标准 | FULL 会话中真实的 "32" | RETRIEVED 中真实的 "32" | 弃权（4 次运行） |
| --- | --- | --- | --- | --- |
| How old was I when Alex was born? | `11` | 2 | **0** | **4/4** — 检索失败 |
| How many years will I be when Rachel gets married? | `33` | 1 | **0** | **4/4** — 检索失败 |
| How many years older is my grandma than me? | `43` | 3 | 1 | 0/4 — 经由路由修复恢复 |
| Average age of me/parents/grandparents | `59.6` | 2 | 1（3/4 次运行） | 多数已作答 |

有两个问题——`Alex born` 与 `Rachel married`——对 `"32"` 这一操作数存在**一致**的
检索失败：在全部运行中，年龄存在于完整的答案会话里，却缺席于检索窗口。

---

## 2. 根因

年龄 `"32"` 是在一个主题为其他内容的会话中作为**顺带一提的附带信息**陈述的：

- `Alex born`：`"…options suitable for someone my age? By the way, I just turned 32 last month…"`（一个职业转型会话）
- `Rachel married`：`"…do you think 32 is considered young…"`（一个旅行/健身会话）

问题问的是 `Alex's birth` / `Rachel's wedding`，因此这些会话与操作数 `"my age"`
语义上相距甚远。

多会话查询扩展提示词是**活动/事件导向**的：

```
Given a question about counting or aggregating past activities,
list the SPECIFIC ACTIVITIES whose descriptions would appear in the evidence sessions.
```

因此对于推导（操作数）类问题，它只会生成事件短语，从不生成缺失的操作数：

| 问题 | 产生的扩展查询 | 缺失的操作数 |
| --- | --- | --- |
| Alex born | `["Alex's birth", "my age at Alex's birth"]` | `my age` / `my birthday` |
| Rachel married | `["get married", "attend wedding", "celebrate wedding"]` | `my age` |

决定性的对照：`average age` 扩展为 `["calculate my age", …]`，并且**确实**检索到了
`"32"`（3/4 次运行）。当扩展中命名了 `my age`，操作数就能被找到；当它只命名事件时，
就找不到。

这与**路由修复属于同一类缺陷**：查询扩展专门针对某一类问题（枚举/计数 → 活动），
而不处理推导（→ 操作数）。

---

## 3. 修复计划（P0）

镜像路由修复，深入到流水线下一层。

1. **`buildDerivationQueryExpansionPrompt(question)`** —— 一个针对推导类问题的新扩展
   提示词，要求 LLM 列出需要检索的**具体事实/操作数**（问题所比较或组合的数字与日期），
   明确包含 `my age`、`my birthday`、`my current age` 以及另一个操作数（例如
   `Alex's age`、`Alex's birth year`）。

2. **路由该扩展** —— `retrieveSessionsForQuestion` 目前硬编码
   `buildMultiSessionQueryExpansionPrompt`。改为按
   `classifyAggregationKind(question) === 'derivation'` 路由（在 `answerSessions` 中
   只计算一次并向下传递，以避免第二次调用），与答案提示词已有的路由方式完全一致。

3. **喂入两条通道** —— 扩展查询目前已被会话级扩展与轮次级召回共同使用，因此操作数查询
   （`my age`）无需进一步改动即可同时到达轮次召回通道。

### 测试（TDD，在实现之前）

1. `buildDerivationQueryExpansionPrompt` 要求的是操作数/事实，而非活动（并且包含
   操作数指令标记）。
2. `buildMultiSessionQueryExpansionPrompt` 保持不变（仍为活动导向）。
3. 路由测试：推导类问题产生推导扩展提示词；枚举类问题保持活动扩展提示词。
4. 完整性不变量：每个 `AggregationKind` 都有匹配的扩展提示词（分类器 ↔ 扩展提示词），
   因此任何问题都不可能路由到其输出遗漏了自身操作数的提示词。
5. 变异测试：移除路由分支或操作数指令，必须使相关测试失败。

### 验收标准

| 准则 | 门槛 |
| --- | --- |
| 覆盖率 | Statements / Branch / Functions / Lines ≥ 95% |
| `pnpm check` | 退出码 0，零跳过 |
| 机制 A/B | 同一时刻 4v4；`Alex born` + `Rachel married` 检索到 `"32"` 操作数（或其弃权下降）；精确置换检验 p ≤ 0.05 |
| 归因 | 残差 0 —— 仅被分类为推导的 MR 问题发生移动；IE/KU/TR 不变 |
| 提交 | `Lambertyan <lambertyan@agentix-e.dev>`，英文提交信息 |

### 收益

两个问题都各自是 4/4 弃权（`Alex born`、`Rachel married`）= 4 次运行共 8 次弃权
= MR 上至多 +2 正确/运行 —— 与刚被接受的年龄路由修复相当（+2.5/运行）。

### 范围之外

更深层的、普适性的问题——用户的年龄是一个在主题相距遥远的会话中零散分布的附带信息
（一个检索粒度问题）——并非本次修复所能解决；本次修复让推导路径命名其操作数，好让现有
检索能找到它们。完整的以实体为中心的检索层是更大的后续迭代。
