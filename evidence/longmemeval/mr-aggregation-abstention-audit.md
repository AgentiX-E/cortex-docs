# MR 数值/计数/日期聚合弃权 — 深度审计

**日期：** 2026-09-05
**被审计的实验臂：** 处理组（`master` = `4640c86`，即 #146 之后）
**范围：** 弃权过的 18 道不同 MR 题（4 次运行共 49 次弃权）

---

## 1. 结论（先于证据）

MR 弃权缺陷**不是一个缺陷** —— 它是一簇彼此不同的失效模式，各自的修复方式与收益都大相
径庭。其中一种模式是可定位根因的**确定性分类缺陷**：若干推导类问题被路由到枚举提示词，
而后者在结构上无法产生一个计算得出的答案，于是模型即便全部操作数都逐字出现在上下文中也
仍然弃权。这一模式正是本次迭代瞄准的干净、高置信度的修复。其余模式（检索未命中、LLM
操作数识别失误、枚举少计、问题/数据不匹配）要么更大、要么置信度更低，已编目留待后续迭代，
不并入本次修复。

---

## 2. 提示词架构（为何分类重要）

`answerSessions` 把每一道 MR 题恰好路由到两个提示词之一：

| 提示词 | Step 1 要求模型做什么 | 产出 |
| --- | --- | --- |
| `buildAggregationQaPrompt`（枚举） | 枚举每一个匹配项 + 动作 | 一个计数 / 求和 / 列表 |
| `buildDerivationQaPrompt`（推导） | 识别具体的操作数 | 一个计算得出的值 |

路由器是 `classifyAggregationKind`：

```ts
/\b(percentage|percent|average|mean|difference (?:in|between)|
   how much (?:more|less|faster|earlier|older)|increase in|decrease in|
   discount|cashback|minimum|maximum|how old was)\b/i  → 'derivation'
// otherwise                                                            → 'enumeration'
```

枚举提示词的 Step 2 让模型*对时长求和 / 统计不同项的个数 / 对金额求和*。一道答案为
**两个时长之差或两个年龄之差**的题无法由该提示词作答：模型枚举各项，找不到等于答案的项，
于是弃权。推导提示词是唯一能做减法的那个。因此，一道*本应*属于推导却被分类为枚举的题，
是确定性地丢分。

---

## 3. 已确认的分类缺陷（类别 A）

### 3.1 "How long have I been working in my current role?" — 金标准 `1 year and 5 months`

`classifyAggregationKind` 返回 **`enumeration`**（已对照已发布的 `dist` 构建核验）。
枚举提示词确实被用到了 —— 模型自己的推理引用了两个操作数，然后弃权：

> "started as a Marketing Coordinator and worked my way up to Senior Marketing
> Specialist after **2 years and 4 months**" ... "my **3 years and 9 months**
> experience in the company" ... "no session states how long they have been *in*
> the Senior Marketing Specialist role itself. Answer: UNANSWERABLE"

算术是精确的：`3 years 9 months − 2 years 4 months = 1 year 5 months` = 金标准。
两个操作数都逐字出现在检索上下文中（模型引用了它们）。这是一道 **4/4 弃权题** —— 每次
运行都丢分 —— 且失败完全确定：该提示词无法表达减法。

### 3.2 "How many years older is my grandma than me?" — 金标准 `43`

`classifyAggregationKind` → **`enumeration`**（正则里是 `how much older`，没有
`how many years older`）。奶奶 75 岁（逐字："turned 75 recently"），用户 32 岁
（`"do you think 32 is considered young"` 就在检索上下文中）。`75 − 32 = 43` = 金标准。
**4/4 弃权。** 同样的确定性根因。

### 3.3 "How many years will I be when my friend Rachel gets married?" — 金标准 `33`

`classifyAggregationKind` → **`enumeration`**。检索上下文同时持有两个操作数：
`"32"`（出现 4 次）与 `"next year"`（1 次）配 `"married"`（1 次）。`32 + 1 = 33` =
金标准。**4/4 弃权。**

### 3.4 "How many minutes did I exceed my target time by in the marathon?" — 金标准 `12`

`classifyAggregationKind` → **`enumeration`**（`exceed ... by` 是一个差）。
**1/4 弃权** —— 另外 3 次运行作答了，因此分类缺陷在这道题上只是间歇性地咬人。

### 类别 A 的收益

| 问题 | 弃权/4 | 上下文中的操作数 | 置信度 |
| --- | --- | --- | --- |
| current role（`1y5m`） | 4/4 | 两者均逐字（模型引用了） | 确定 |
| grandma older（`43`） | 4/4 | 75 逐字，32 存在 | 高 |
| Rachel married（`33`） | 4/4 | 32 + "next year" | 高 |
| marathon exceed（`12`） | 1/4 | 尚未核验 | 中 |

**修复：** (1) 扩展 `classifyAggregationKind` 的推导集合，覆盖时长/已历时间
（`how long have I been …`）、年龄差（`how many years older`）、未来年龄
（`how many years old will I be when …`）以及按差值计（`how many minutes … exceed … by`）；
(2) 为 `buildDerivationQaPrompt` 的 Step 2 加入匹配的算术规则（时长差、事件时年龄）。

---

## 4. 其他失效模式（已编目，**不**并入本次修复）

### 类别 B —— 正确路由到推导，但 LLM 漏掉了一个确实存在的操作数

- **"average age of me, my parents, and my grandparents"**（金标准 `59.6`，2/4）：
  检索上下文逐字包含 `"I just turned 32 on February 12th"`，然而模型的 Step 1 却列出
  "my own age | not explicitly stated (only 'early thirties')"。操作数就在那里；模型没有
  把 "turned 32" 与 "my age" 联系起来。`(55+58+75+78+32)/5 = 59.6` = 金标准。这是 LLM
  的操作数识别失误，与温度方差相邻，不是路由缺陷。

### 类别 C —— 检索失败：操作数在完整会话中，却缺席于检索窗口

- **"How old was I when Alex was born?"**（金标准 `11`，4/4）：完整的答案会话包含
  `"I just turned 32 last month"`（一个职业转型会话），且 Alex 21 岁（`"he's just 21"`）。
  `32 − 21 = 11` = 金标准。但检索窗口里只有 Alex/21，**没有 "32"** —— 那个年龄会话未被
  召回。这是检索排序/覆盖问题，不是提示词问题。
- **"What time did I reach the clinic on Monday?"**（金标准 `9:00 AM`，4/4）：完整会话
  包含 `"9:00"`；检索窗口里有 "clinic"（3 次）但没有 "9:00"。检索问题（或者 9:00 这个
  细节所在的轮次被窗口丢弃了）。

### 类别 D —— 枚举少计（各项分散，模型过早停下）

- "days attending workshops/lectures/conferences in April"（`3 days`，4/4）、
  "health devices"（`4`，2/4）、"siblings"（`4`，2/4）、"furniture"（`4`，2/4）、
  "museums in February"（`2`，1/4）、"social media breaks"（`17 days`，1/4）、
  "people reached by FB + IG"（`12,000`，1/4）。这些需要更强的枚举或更好的召回，且
  单题量级都小。

### 类别 E —— 问题/数据不匹配或非数值操作数（低置信度）

- "page count of novels finished in January and March"（金标准 `856` = 416+440，但
  "January"/"March" 在答案会话中出现 **0** 次 —— 那些小说是在别的月份读完的）。很可能是
  不完美的问题/金标准配对。
- "average GPA"（金标准 `3.83`；本科只有 "First-Class distinction"，找不到数值 GPA）。
  该数值操作数似乎并不存在。
- "When did I submit my research paper…"（金标准 `February 1st`；那个日期是 *ACL 会议*
  的投稿日期，不是用户自己的投稿日期）。有歧义。

---

## 5. 为何总体准确率无法验证这一点（方法论）

这个干净的修复瞄准约 3–4 道 MR 题。那是 500 题基准的约 0.6–0.8% —— 低于实测的臂内离散度
（6–7 题/运行）。与 #146 一样，**机制端点**是唯一有效的检验：在*被分类为推导*的问题上的
MR 弃权率，修复前 vs 修复后，采用同一时刻 4v4 协议并做精确置换检验。总体准确率仅作为带
噪声底的描述性估计报告。

---

## 6. 修复计划（P0 —— 本次迭代）

### 6.1 生产改动（均在 `natural-language-memory.ts`）

1. **`classifyAggregationKind`**：扩展推导正则，覆盖
   - 已历/时长：`how long (?:have I|has it) been …`
   - 年龄差：`how many years (?:older|younger)`
   - 未来年龄：`how many years (?:old )?will I be when …`
   - 按差值计：`how many (?:minutes|hours|days|… ) … exceed … by`
   每一处新增都是*具体*的词法模式，而不是宽泛的"这是否是一个关于数字的问题"式启发式，
   因此它不会悄悄把计数题重新路由。

2. **`buildDerivationQaPrompt`** Step 2：为新情形加入明确的算术规则：
   - `"how long have I been [in/at/working] X"` → 识别总任职时长与达到 X 所需时间，然后
     相减：`total − time-to-X`。
   - `"how many years older is A than B"` → `age(A) − age(B)`。
   - `"how many years will I be when X happens"` → `current age + years until X`。
   - `"how many … exceed … by"` → `actual − target`。

### 6.2 测试（TDD，在实现之前）

1. 针对全部四种新表述对 `classifyAggregationKind` 做单元测试（以及阴性对照：一道普通的
   计数题仍必须分类为 `enumeration`）。
2. 单元测试断言 `buildDerivationQaPrompt` 会输出每一条新算术规则，且 `answerSessions`
   会把新表述路由到推导提示词。
3. 一个**完整性不变量**，镜像 #146 的测试：每个 `AggregationKind` 值都有 Step 2 规则，
   因此新分类出的推导题不可能落到一个没有匹配指令的提示词上。
4. 一个**变异测试**：若移除新的分类器分支或新的 Step 2 规则，相关测试必须失败（证明该
   测试具有区分力）。

### 6.3 验收标准

| 准则 | 门槛 |
| --- | --- |
| 覆盖率 | 被触及包在 Statements / Branch / Functions / Lines 上 ≥ 95% |
| Lint / format / typecheck / 测试 | `pnpm check` 退出码 0，零跳过 |
| 机制 A/B | 4v4 同一时刻；MR 推导弃权率 ↓ 且精确置换检验 p ≤ 0.05；守卫 IE/KU/TR 不变 |
| 归因 | 残差 0 —— 该改动只移动被分类为推导的 MR 问题 |
| 提交 | `Lambertyan <lambertyan@agentix-e.dev>`，英文注释/信息 |

### 6.4 本次迭代不在范围内

类别 B（操作数识别失误）、C（用户年龄 "32" 的检索未命中）、D（枚举少计）与 E（问题/数据
不匹配）已编目但推迟 —— 它们要么更大、要么置信度更低，会污染一处外科手术式提示词路由修复
的归因。

---

## 7. 类别 C 背后更大的收益（下下次迭代候选）

用户年龄 `"32"` 是一个**跨题操作数**，三道 MR 题都需要它（"Alex born" 11、"grandma
older" 43、"average age" 59.6），而它的检索结果并不一致 —— 对 "average age" 存在，对
"Alex born" 缺席。这指向检索排序/覆盖，并且它很可能同样损害*错误*答案（不只是弃权），
凡是模型猜测而不弃权之处。那是更大的、独立的调查，安排在此次修复之后。
