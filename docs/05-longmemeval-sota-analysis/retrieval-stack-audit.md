# 检索栈审计 —— 对照 LongMemEval-S 前沿方法

**日期：** 2026-09-06

## 1. 我们当前的栈（已经相当精巧）

| 组件 | 函数 | 它做什么 |
| --- | --- | --- |
| 会话质心 | `retrieveTopKSessions` | 会话 = 回合向量的均值池化 |
| 多查询 | `retrieveByQueries` | 查询扩展会话召回 |
| **回合粒度召回** | `retrieveSessionsByTurns` | 以会话的**最佳匹配回合**为其打分 |
| 混合回合召回 | `retrieveTopKByQueriesHybrid` | 语义 + 稀有关键词词汇召回 |
| 词汇 | `extractLexicalKeywords` / `countLexicalMatches` | 稀有关键词文档频率过滤 |

## 2. 相对前沿的那一个具体缺口

EmergenceMem（86%）和 AgentOS（85.6%）都通过 NDCG 从会话各回合的**排名**
为会话打分（“1/log2(1) + 1/log2(3) + 1/log2(4)”），因此一个在 top-K 中有
*多个*回合的会话，其排名高于一个只有单个略强回合的会话。
我们的 `retrieveSessionsByTurns` 只以**单个最佳回合**为会话打分
（`bestBySession.set(i, max(score))`），丢弃了它会话中其余的
证据。

- 交叉编码器重排（Emergence 也使用）需要一个外部模型，且
  在这个纯 TS 栈中超出范围。
- 按类别的读者路由已由我们按能力码的
  提示词近似（IE/MR/KU/TR 各有自己的构建器）。

**建议：** 用对每个会话在 top-K 中回合的排名折扣
DCG 聚合，替换最大回合的会话分数。这是一个纯的、
可单元测试的函数，且它是我们缺失的、直接映射到 MR/TR 缺口的
那项单一前沿技术。

## 3. 权衡（为何这需要一次 A/B）

`max` 偏爱有一个强证据回合的会话（单事实题）；
DCG 偏爱有多个证据回合的会话（多证据题）。
LongMemEval-S 的 MR 混合了两者，因此该改动必须在机制
端点（MR/TR 弃权 + 证据会话的检索）上度量，而非假定。
