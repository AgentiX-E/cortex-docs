# 分析工作区 — LongMemEval-S SOTA 冲刺

本目录是 Cortex 记忆层上 LongMemEval-S SOTA 迭代的**原始证据链**（2026-09 至 2026-10）。
它不是文档，不需要逐篇阅读：结论已被抽取进 [`docs/04`](../../docs/04-execution-tracking-report.md)，
这里保留的是每一份判决的原文、脚本、run id 与日志，供复核。可复现代码与冻结的基线位于
`/workspace/cortex`（参见该目录下的 `SOTA-BASELINE.md`）。

> 路径已变更：本目录原为 `docs/05-longmemeval-sota-analysis/`。目录内正文中出现的
> `docs/07`、`docs/09` 等引用指向**历史文档编号**，其全文可用 git 取回，见仓库根 `README.md`
> 的「历史归档」一节。

## 目录结构

原始工作区中，验收判决位于 `verdicts/` 子目录。发布到本仓库时文档被平铺到顶层；脚本与派发文件保持原有分层。

| 路径 | 内容 |
| --- | --- |
| `*.md`（顶层） | 验收判决、根因审计、计划与研究笔记（原 `verdicts/`） |
| `scripts/` | 可复现的分析脚本（`*.py`、`*.mjs`）——它们读取下载下来的运行产物 |
| `dispatch/` | A/B 派发 + 产物下载脚本（`*.sh`） |
| `run-ids/` | GitHub Actions run id（`*.tsv`），用于重新下载产物 |
| `logs/` | 缓存的脚本输出（`*.txt`）——可由脚本重新生成 |
| `plans/` | 迭代规划记录 |

脚本注释中出现的 `verdicts/<name>.md` 是原始工作区的路径，在本仓库中对应同名的顶层文件。

## 数值保真度

本目录的文档是英文原始记录的中文译本。译文与源文之间的数值一致性由
`../../tools/check-numeric-fidelity.mjs` 机械校验：比较两份文档的数值 token 多重集，
任何未解释的差异都会导致失败。

```bash
node tools/check-numeric-fidelity.mjs --file <源文> <译文>
node tools/check-numeric-fidelity.test.mjs
```

## 重新下载运行产物

下载得到的 `benchmark-*.json` 产物（此前约 1 GB，位于 `ab_*/` 目录下）已作为可再生的
中间产物被删除。要复现任意一项分析：

1. 从 `run-ids/<experiment>_run_ids.tsv` 中选取 run id。
2. 运行对应的 `dispatch/download_ab_<experiment>.sh`（如有需要，编辑 run-id 来源）
   ——它会下载每个产物并校验 `questionCount == 500`。
3. 运行对应的 `scripts/ab_<experiment>_analysis.py`。

## 关键判决（验收记录，最新的在前）

| 文档 | 迭代 | 结论 |
| --- | --- | --- |
| `longmemeval-sota-research.md` | SOTA 格局 | 定位 83.55%（高于论文 Oracle） |
| `mr-dcg-verdict.md` | DCG 会话打分 | **拒绝**（MR −3.9pp），已回退 |
| `wronganswer-rootcause-verdict.md` | 错答根因 | 阅读器语义天花板，无评测缺陷 |
| `mr-operand-expansion-verdict.md` | 推导操作数扩展 | **接受**（Alex born 4/4） |
| `mr-duration-age-routing-verdict.md` | 时长/年龄推导路由 | **接受**（2× 4/4 弃权→正确） |
| `ku-no-qualifier-verdict.md` | KU 无限定词选择规则 | **接受**（弃权 −10.11pp，+4.17pp） |
| `age-operand-retrieval-audit.md` | 年龄操作数检索失败 | 已定位根因（活动 vs 操作数扩展） |
| `mr-aggregation-abstention-audit.md` | MR 聚合弃权 | 已定位根因（路由缺陷簇） |
| `tr-two-event-verdict.md` | TR 双事件时序修复 | 接受 |
| `embedding-cost-audit.md` | 嵌入成本 | P0/P1 已落地，P2 部分落地（无效） |

各文档正文中可见确切的置换检验 p 值、逐运行的分离情况以及归因残差。
