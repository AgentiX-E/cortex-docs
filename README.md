# AgentiX-E Cortex 内部文档

本仓库为 [AgentiX-E/cortex](https://github.com/AgentiX-E/cortex)（Node.js/TypeScript 智能体记忆系统）的**内部中文文档**。

## 文档索引

| 文档 | 内容 |
|---|---|
| [01 竞品分析与产品白皮书](docs/01-competitive-analysis-and-product-whitepaper.md) | 竞品全景、功能列表、复刻学习整合、创新超越、行业标杆路径 |
| [02 技术设计与实现](docs/02-technical-design-and-implementation.md) | 架构、子包、抽象层、核心算法、npm 包选型、底层实现 |
| [03 实现推进与验收计划](docs/03-implementation-and-acceptance-plan.md) | 迭代计划、测试方法、≥95% 覆盖率、权威测试集、公平科学验收 |
| [04 知识字典](docs/04-knowledge-dictionary.md) | 心智模型、算法、数学工具、工程概念、参考文献、自学路径 |
| [05 LongMemEval-S SOTA 分析记录](docs/05-longmemeval-sota-analysis/00-ANALYSIS-README.md) | 94 篇验收判决、根因审计与计划，附可复现脚本索引 |

## 约定

- 内部文档使用中文；
- 代码注释、外部文档、commit message 一律使用英文，见 [AgentiX-E/cortex](https://github.com/AgentiX-E/cortex)。

关于 **05 分析记录**的语言选择：该目录由英文原始记录翻译而来，遵循本仓库的中文约定。
翻译保真度由 `tools/check-numeric-fidelity.mjs` 机械校验，配套回归测试见
`tools/check-numeric-fidelity.test.mjs`：

```bash
node tools/check-numeric-fidelity.mjs <源目录> <译文目录> --summary
node tools/check-numeric-fidelity.test.mjs
```

验收标准为**每个文档的数值 token 多重集完全一致**——整数、小数、百分比、pp 增量、
指数与带符号值必须逐一复现，只有语言相关的裸小整数计数允许单向调和。当前状态：
94/94 文档通过，回归 12/12 通过。
