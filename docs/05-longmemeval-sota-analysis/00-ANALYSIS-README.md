# 分析工作区 — LongMemEval-S SOTA 冲刺

本目录是 Cortex 记忆层上 LongMemEval-S SOTA 迭代的证据链。它**不是** git 仓库；
可复现代码与冻结的基线位于 `/workspace/cortex`（参见该目录下的 `SOTA-BASELINE.md`）。

## 目录结构

| 目录 | 内容 |
| --- | --- |
| `verdicts/` | 验收判决、根因审计、计划与研究笔记（`*.md`） |
| `scripts/` | 可复现的分析脚本（`*.py`、`*.mjs`）——它们读取下载下来的运行产物 |
| `dispatch/` | A/B 派发 + 产物下载脚本（`*.sh`） |
| `run-ids/` | GitHub Actions run id（`*.tsv`），用于重新下载产物 |
| `logs/` | 缓存的脚本输出（`*.txt`）——可由脚本重新生成 |

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
