# 预登记：双时态时间轴的净贡献（`S18`）

> 状态：**已派发，未读数**
> 处理运行 `44680735798`（`fact_timeline=1`）；对照运行 `44680588835`（`fact_timeline=0`）
> 本文件在**任何答案被看到之前**写定，判据、人群、读数口径均不得在看到结果后修改。

---

## 1. 问题

台账第 19 行（`bitemporal timeline`）在第 141 轮从 `instrument` 推到 `product (gated)`：产品里有一条
`memory.ts → timeline.ts` 的可达路径，有开关、有测试、有手册条目。`gated` 的含义就是
**可达但未被测量**——用户能打开它，没人知道打开之后准确率往哪走。

第 139 轮已经证明它在**结构上安全**（它只印台账 `servedIds` 里的事实，变异检验转红），
但"不发表被拒绝的东西"与"发表的东西有用"是两件事。

## 2. 处理与对照

| | `fact_timeline=0`（对照） | `fact_timeline=1`（处理） |
| --- | --- | --- |
| 运行 | `44680588835` | `44680735798` |
| baseline 侧 | `semanticCarry=off` | `semanticCarry=off` |
| feature 侧 | `semanticCarry=on`，渲染不带日期 | `semanticCarry=on`，渲染带日期区间 |

两次派发都是 `pairing=carry`（`review_pass=supersede`、`turn_rendering=head`），所以两侧的差异只有
carry；两次派发之间的差异只有时间轴渲染。

**为什么要两次派发而不是一次**：`fact_timeline` 是 workflow 的全局输入，一次派发只能有一个值。
同一产物里没有第二条渲染路径，所以这是一个**跨派发**的配对，而不是 `S12` 那种"一次派发的两侧"。

**跨派发的漂移怎么办**：两次派发各带一对臂，所以存在两条独立读数：

```text
Δ_axis = feature(timeline) - feature(no-timeline)      # 处理效应
Δ_drift = baseline(timeline) - baseline(no-timeline)   # 漂移（对照臂不含处理，故其差只能是漂移）
Δ_net   = Δ_axis - Δ_drift                              # 校正后的净效应
```

`baseline` 侧不含时间轴（它是 `semanticCarry=off`），所以 `Δ_drift` 可读；这是这个设计唯一能做的漂移
校正，也是本仓 `PREREGISTRATION` §2.2 记录的 1.7–2.1pp 时漂移的处理方式。

## 3. 人群与规模

`CORTEX_CAPABILITY=KU`、`windows=2`、`limit=0`：本地语料的全部 KU corpora（72）× 2 窗口 = **144 题/侧**，
`ablation_runs=2`，`shards=4`，`workers=8`。

选 KU 的理由与工作流自身的注释一致：吸收只发生在 `reviewPass=supersede && route=knowledge-update`，
所以时间轴**只有在这条路由上才可能有内容**。其余四条路由这一次是内部对照（它们渲染不出区间）。

投影花费 **2.05 CNY/派发**，两次合计 **4.10 CNY**（读数前登记，事后按 provider 报告复核）。

## 4. 判据（全部预先登记）

| # | 判据 | 阈值 | 不成立时写什么 |
| --- | --- | --- | --- |
| **F1** | 净修复题数 `Δ_net` | **≥ +3**（144 题上的 2.1pp） | 机制留在 `gated`，默认 `off`，理由记为"未检出增量" |
| **F2** | 配对 McNemar `p` | **< 0.05** | 同上；若 `Δ_net ≥ 3` 但 `p ≥ 0.05`，写"点估计为正、不显著" |
| **F3** | 回退题数（处理对、对照错 → 反向） | **≤ 6** | 与 `S17` 的 6 处回退同尺度；超过则机制默认 `off` 并在 `RETRACTIONS.md` 记录 |
| **F4** | 漂移可分离性 | `|Δ_drift| ≤ 3` 题 | 超过则判 **indeterminate**，不发布净效应，只发布两条原始读数 |
| **F5** | 证据位移 | 记录 `deliveredChars` 的中位数与四分位 | 若中位数为 0，说明渲染没有真正改变送达文本，机制是"开关存在、文本未变"，必须写明 |

`F1`–`F4` 全部满足才算 **通过**；`F5` 是描述性读数，不设阈值——它的作用是防止"通过"建立在一个
没有真正改变提示词的开关上（这正是本仓 `S13` 抓到的形状）。

## 5. 这次派发**不能**回答的问题

| 问题 | 为什么不能 |
| --- | --- |
| 时间轴在其余四条路由的贡献 | 那些路由渲染不出区间（吸收只在 knowledge-update），读数为零是**构造性**的，不是"没有效果" |
| 时间轴是否改善 `MR`（当前最弱分类，71.69%） | MR 不走上限 `supersede` 的吸收路径，需要另一份机制 |
| 时间轴的**成本**是否可接受 | 两次派发的投影相同（2.05 CNY），但实际 token 差要等 provider 报告；渲染新增的字符会在 `deliveredChars` 里 |

## 6. 读数的来源约束

只读 **merged** 产物（`merged-evidence.json`）与 workflow 步骤 15 的 `reach` 行，不读单 shard：

- 单 shard 的题数不等于人群，`Δ_net` 会在 36 题上算，标准误是 144 题的三倍；
- `merged.parts[].bitstringsFrom` 会显示这一次是否走了"单重复重建"路径（这次是 2 次重复，不应出现）；
- 若 merge 拒绝，**不读任何数**，先修 merge 再重跑——`44676731032` 的教训。

## 7. 与台账的关系

| 结果 | 台账第 19 行 |
| --- | --- |
| `F1`–`F4` 通过 | `product (gated)` → `product`，默认值保持 `off`（安全性优先），完成度 18/27 → **19/27** |
| 任一不通过 | 留在 `product (gated)`，`RETRACTIONS.md` 记录读数；完成度不变 |

默认值不因通过而改成 `on`：`F1` 的阈值是 +3 题，不是"明显更好"；把默认翻开需要第二批人群的独立确认。
