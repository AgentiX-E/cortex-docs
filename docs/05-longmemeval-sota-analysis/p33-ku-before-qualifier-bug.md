# P33 —— `before` 被读作值限定词，把区间问题送进了双时路径（已修复）

**状态：** 一个 bug 已修复并交付（4 个测试，修复前 3 个被验证为红）。
以零 API 成本离线发现，方式是延续 P32 的方法：阅读分支
谓词，然后对照真实运行测量它们所选出的总体。

---

## 1. 该 bug

`classifyKnowledgeUpdateQualifier`（`fact-store.ts`）把 `before` 一词的**任何**出现
都当作一个前值限定词：

```ts
if (/\b(previous|before|previously|originally|used to|earlier)\b/i.test(question)) {
  return 'previous';
}
```

但 `before` 也是一个引入第二个事件的普通介词。在
*"What new kitchen gadget did I invest in **before getting the Air Fryer**?"* 中它
命名的是一个时间锚，不是某个主体的陈旧值。

其后果不是一个分类上的小毛病。当 `answer` 看到一个非 `other`
限定词时，它**先进入双时路径**（`natural-language-memory.ts`
§726-740），该路径提取 `(subject, predicate, object, date)` 三元组，取
**第一个**事实的主体（`facts[0].subject`），并返回
该主体时间线上的 `previousObject`/`currentObject`。对一个真实主体是一个小工具的问题，
该路径在结构上是错误的工具：它从一个无关的"主体"作答，而该主体的两个带日期事实碰巧在场，
返回一个自信的值，而不是落空到区间引擎。

## 2. 该总体，在真实运行上测量

在运行 `35162802298` 的 14 道错误 KU 问题中，只有 **4** 道携带
`previous`/`current` 限定词；其余 10 道是 `other` 且从不触及
双时路径。那 4 道带限定词的全部具有**空的 `llmRaw`**——
即它们由确定性路径作答，而非由模型：

| id | 问题 | 限定词（之前） | 标准答案 | 得到 |
|---|---|---|---|---|
| `031748ae` | "How many engineers do I lead when I just started my new role…" | `current`（"new role" —— 未匹配；见 §5） | 散文 | 5 |
| `c4ea545c` | "Do I go to the gym more frequently than I did **previously**?" | `previous` | Yes | three times a week |
| `f685340e` | "How often do I play tennis … **previously**? How often do I play now?" | `previous` | 散文 | weekly |
| `89941a94` | "**Before** I purchased the gravel bike, do I have other bikes …?" | `previous`（bug） | Yes | commuter bike |
| `0977f2af` | "What new kitchen gadget did I invest in **before** getting the Air Fryer?" | `previous`（bug） | Instant Pot | `null`（弃权） |

五道中有两道是纯 `before` 作介词的案例；`f685340e` 是同一类错误的一个
无介词变体（见 §4）。`031748ae` 和 `c4ea455c`/`f685340e` 在 §5 和 §4 中分析，且**不**在此修复。

## 3. 修复

`before` 现在仅当它限定主体时才读作一个值限定词：

| 形态 | 例子 | 判决 |
|---|---|---|
| 结束子句 | "What was my occupation **before**?" | `previous` |
| 后接所有格/限定词 | "Where did I work **before my current role**?" | `previous` |
| 后接主体 + 动词 | "**Before I purchased** the gravel bike, …" | `other` |
| 后接动名词 | "…invest in **before getting** the Air Fryer?" | `other` |

`previous`/`previously`/`originally`/`used to`/`earlier` 未被触动——它们
无歧义，且没有一个发生冲突。

**天花板：+2 questions (+0.4pp)**（`0977f2af`、`89941a94`）。诚实的限定：
二者都不是保证的转化。`0977f2af` 当前弃权并
落空到一个必须*找到* `Instant Pot` 的读者（P31 测得 14 个此类上下文中
有 10 个为证据缺席）；`89941a94` 的标准答案是一段散文 "Yes. (You have a road
bike too.)"，对照一个要求自行车类型的问题，因此 CoT 提示词可能
或可能不落准。+2 是天花板，不是预测。该修复所依据的更强主张是
**结构性的**：五道其正确主体实体
与双时时间线无关的问题不再从那条时间线作答。
无论替代答案是否正确，这都是对的。

## 4. 一个发现但未修复的第二个、密切相关的缺陷

`f685340e` —— *"How often do I play tennis with my friends at the local park
**previously**? How often do I play **now**?"* —— 是一次**节奏比较**，不是
值选择。`previous`/`current` 选择返回两个*对象*中的哪一个，
并对一个同时命名了旧频率和新频率的标准答案返回了 `weekly`。

这与 §3 形态相同但守卫不同：不是"`before`
是不是介词"而是"该问题问的是一个**频率/节奏**而非
一个值"。我把它**留作未修复**，因为该修复需要一条我无法从 1–2 个例子
辩护的规则，而对两个例子拟合一条规则是过拟合
（与 P32 §5.3 中 R6(a) 被暂存的同一原因）。在此记录，使该
总体被度量而非仅仅被注意到。

## 5. 一个值得记录的近失

`031748ae` —— *"How many engineers do I lead when I just started my new role as
Senior Software Engineer? How many engineers do I lead … now?"* —— 被分类为
`current`，而我的第一直觉是 `new role` 本应使它为
`previous`。那个读法是**错的**：该问题问两件事，而
`now` 一词真正要求的是当前值，因此 `current` 是正确的
限定词。这里的失败是标准答案是一段散文，描述了两个
计数，而引擎返回裸整数 `5`。那是一个**缝合**
问题——双时路径对一个两部分问题返回单个值——
而它是与 §3 不同的缺陷。它不在此修复，且**不是**
`before` 守卫的证据。

## 6. 测试

向 `fact-store.test.ts` 添加四个：

- **修复前 3 个为红**，每个对应运行中一道被测得的问题，各断言
  `other`：
  - "What new kitchen gadget did I invest in before getting the Air Fryer?"
  - "Before I purchased the gravel bike, do I have other bikes …?"
  - "How often do I play tennis … previously? How often do I play now?"
    （通过频率守卫钉住，§4）
- **1 个无回退**，前后均为绿色：句尾 `before`
  （"What was my occupation before?"）和后接所有格的 `before`
  （"Where did I work before my current role?"）必须仍分类为
  `previous`。它存在是为了阻止该修复被扩大到"永不再把
  `before` 当作限定词"。

门：**962 个测试绿色**（cortex-eval 816）。cortex-eval 中覆盖率 99.84 stmts / 98.65 branch
/ 100 funcs / 99.84 lines；任何地方的最低 branch 数字为 97.26%。

## 7. 这使审计处于何处

现在已有三个 bug 来自同一个方法——阅读分支谓词，然后
对照一次真实运行的诊断测量它选出的总体：

| # | 缺陷 | 天花板 | 状态 |
|---|---|---|---|
| P32 | `formatOrdering` 近期性分支遮蔽了序列分支 | +4 (+0.8pp) | **已交付** |
| P33 | `before` 作介词被读作值限定词 | +2 (+0.4pp) | **已交付** |
| P33 §4 | 节奏比较由值选择作答 | ~1 | 已度量，**已暂存** |

该方法奏效是因为一个次序错误或过宽的谓词是一个**结构性**
缺陷：它通过阅读代码可见，其总体可从一次
运行的诊断中数出，而其修复可单元测试。那是唯一一类
无需花一个基准周期即可验证的改动，而它对 TR 和 KU 现在已
穷尽——P31/P32 §6 发现剩余的 TR 质量是 LLM 阅读
质量，而本文档发现 KU 的其他 10 个错误也如此（从一个同时包含两者的上下文中选错
值/时间/数字，而模型直接作答）。

**因此下一个支出是一次运行**，携带 P32 + P33 + R4 + P30 重新打开的
弃权通道，各带自己的消融实验臂。
