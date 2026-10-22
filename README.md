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
| [06 代码与文档一致性审计](docs/06-code-docs-consistency-audit.md) | 代码真实状态核对：哪些能力被验证、哪些未接入评测路径、偏差清单与证据 |
| [07 SOTA 推进计划](docs/07-sota-roadmap.md) | 可执行的超车路线：优先序、前置契约、验收判据与消融设计（v2.0） |
| [08 阅读器判断再研究](docs/08-reader-parity-analysis.md) | 证伪「阅读器是约束」：架构归因 4.7 倍于阅读器归因，附可复现脚本 |
| [09 进度追踪报告](docs/09-progress-and-delivery-report.md) | 每轮迭代的交付、验收证据、发现的 BUG、对计划的修正与诚实差异清单 |
| [10 A2 收口结果](docs/10-a2-closure-results.md) | 发布级 LongMemEval-S 全量测量（run `35523328949`，N=500）：主结果、独立复算、增量归因、召回曲线与优先级结论 |
| [11 供应商限流审计](docs/11-provider-throttling-audit.md) | 那次 429 的根因**不是配额耗尽**：错误码 1305 是并发上限，附三个复合缺陷、诊断产物的来源缺口，与五项按依赖排序的修复需求 |
| [12 浏览器端、存储联邦与私有/共享分诊](docs/12-browser-and-federation-design.md) | 四种部署拓扑、零新增子包的包布局、三值分诊、知识卡片与读侧策略（**设计阶段**） |
| [13 竞品与文献综述](docs/13-competitive-and-literature-survey.md) | 按域（浏览器存储/向量/端侧推理/记忆作用域/人机协同/评测集）的现状、借什么、不借什么 |
| [14 证据登记与 POC](docs/14-evidence-register-and-poc.md) | 23 条结论的证据等级与出处、四个 POC 的方法与结果、6 项未取证缺口 |
| [15 指标、测评集与消融计划](docs/15-metrics-benchmarks-and-ablation-plan.md) | 每个功能的 L1/L2/L3 指标、10 个机制的消融设计、实现阶段的准入门槛 |
| [poc/](poc/README.md) | 四个可复跑实验的源码与结果（`npm run all`） |

## 约定

- 内部文档使用中文；
- 代码注释、外部文档、commit message 一律使用英文，见 [AgentiX-E/cortex](https://github.com/AgentiX-E/cortex)。

关于 **05 分析记录**的语言选择：该目录由英文原始记录翻译而来，遵循本仓库的中文约定。

## 记录完整性守卫

翻译保真度不能靠人工纪律维持，因此由 `tools/check-analysis-record.sh` 机械校验。
它自身可失败，这一点由 `tools/check-analysis-record.test.sh` 保证——该套件会重现守卫
存在的每一种失效场景，并断言守卫确实报告了它：

```bash
tools/check-analysis-record.sh --sources <英文源目录>
tools/check-analysis-record.test.sh --sources <英文源目录>
```

守卫包含四项检查：

| 检查 | 捕获的失效 | 为什么数值比对查不到 |
|---|---|---|
| 守卫自测 | 某项检查的模式已静默失配 | 不适用（元检查） |
| 检查器回归套件 | 容差被放宽或无差别拒绝 | 不适用（元检查） |
| 结构完整性 | 空文档、残留英文、冻结引用被本地化 | 未翻译的文档与源文件完全相同 |
| 数值保真 | 数值被篡改、丢弃、改精度或改符号 | 反过来说：它抓不到"照抄原文" |

其中「未翻译」这一项尤其依赖 CJK 判定：一个从未翻译的文档与源文件逐字节相同，
数值比对会以构造性方式通过。因此该检查把中文字符类写作 Unicode 属性 `\p{Han}` 而非
范围 `[一-鿿]`——后者在 `en_US.UTF-8` 下是*排序*范围，`grep` 会报
`Invalid collation character` 并且**一个字符都匹配不到**，从而让每个英文文档都通过。

数值检查的标准是**每个文档的数值 token 多重集完全一致**——整数、小数、百分比、pp 增量、
指数与带符号值必须逐一复现，只有语言相关的裸小整数计数允许单向调和。

当前状态：守卫自测 7/7，检查器回归 12/12，文档 94/94，语言相关计数调和 194 项。
