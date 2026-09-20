# 进度追踪报告：B2 实测落地与守卫爆炸半径修复

本文件是**进度追踪报告**，记录每一轮迭代的交付、验收证据、发现的 BUG、以及对既有计划的修正。
与 `07-sota-roadmap.md` 的分工是：07 回答「要做什么、为什么、如何验收」，本文件回答
「实际做了什么、证据是什么、和计划差在哪」。

> **阅读约定**：本文件只写**已被证据支持**的内容。未运行的部分明确标注「未运行」，
> 不以「预计」「应该」替代实测。这是本文档存在的全部意义。

---

## 0. 本轮结论先行

| 项 | 状态 | 证据 |
|---|---|---|
| B1 交叉编码器重排 | 已实现、已接线、默认关闭 | `cortex@e0d820b`，新增 61 测试 |
| A4 覆盖率硬门禁 | 已交付 | 四个包均设 95% 阈值，已验证违反时退出码为 1 |
| B2 召回曲线测量仪器 | 已实现、已接线 | 新增 29 测试，`benchmark-recall-curve.json` |
| **B2 实测** | **已运行，已读出结论** | run `35498421148`；ceiling **93.02%**，gain 65.12% → 2.33%（k=1→20） |
| **池宽决策** | **已定论：不加宽** | 按 §2.5 预注册读法第 1 行 |
| **conjunction 守卫爆炸半径 BUG** | **已发现、已修复、已加 17 测试** | `cortex@fe0daa7`；见 §3 |
| **CI 可跑性** | **已确认：GitHub Runner 可用** | PAT 具备 `workflow_dispatch` 权限；org secrets 齐备 |
| B1 A/B | **未运行** | 需 rerank provider 凭据；透传已接好 |
| A2 全量重测 | 未运行 | 需 `LIMIT=0`；约 40 分钟墙钟 |
| A6 阅读器矩阵 | 未运行 | 需四个阅读器凭据 |

测试总数：**982 → 1048 → 1077 → 1094**。四个包全部通过，每维度 ≥95%。

> **本轮最大修正**：上一轮报告把 B1/B2 的实测列为「阻塞于 provider 凭据」。
> 这个判断是**错的**——凭据一直在 GitHub Org level 就绪，`workflow_dispatch` 权限也一直在。
> 我此前把它当作环境限制，而它只是我没有去验证的一个假设。结果是整整一轮实测被推迟。

---

## 1. B2 实测：这是本轮最重要的数字

### 1.1 实测结果

Run `35498421148`（commit `16ca1ea`），`LIMIT=60`，43 道可答题，
DeepSeek + Zhipu GLM embedding-3，temperature 0：

| k | recalled | recall | ceiling | gain |
|---|---|---|---|---|
| 1 | 12 | 27.91% | 93.02% | **65.12%** |
| 3 | 24 | 55.81% | 93.02% | 37.21% |
| 5 | 27 | 62.79% | 93.02% | 30.23% |
| 10 | 33 | 76.74% | 93.02% | 16.28% |
| 20 | 39 | 90.70% | 93.02% | **2.33%** |
| 50 | 40 | 93.02% | 93.02% | 0.00% |

### 1.2 按预注册读法得出的结论

观察到的形态是 **`gain` 大且 `ceiling` 已平坦** —— 预注册表的**第 1 行**。
对应行动：**执行 B1 的 A/B，不要加宽池。**

三条必须分开陈述的事实：

**一、`ceiling` = 93.02%（43 道可答题中的 40 道）。** 剩下 3 道（6.98%）的答案回合
**根本不在池内**，任何重排都够不到。这是诚实的地板，不是可以实现的目标。

**二、`gain` 从 65.12% 衰减到 2.33%。** 重排能占据的空间，只在「上下文窗口相对答案
排名**很窄**」时才是大的；到了系统实际工作宽度，这份空间**已经被宽度本身吸收掉大半**。

**三、cortex 在可用宽度上没有广度问题。** 这条**关闭了**「加召回通道」这一类提案的方向。
今后任何此类提案，必须针对剩下的 **6.98%** 论证自己，而不是针对 `recall@5`——
那是一个截断点，不是上界。

### 1.3 为什么预注册是必要的

单看 `recall@5 = 62.79%`，读起来像「管线丢了三分之一的证据」，足以支持加池**或**加重排，
二者不可区分。曲线同时给出了**上界**（93.02%，证据其实在）与**排序欠账的真实位置**
（在 k ≤ 10，而非在工作宽度）。

**如果先读数字再定读法，这个 62.79% 会被用来支持一个错误的方向。**

### 1.4 口径警示

60 题分层抽样，不是全量 500。3 道不可达题占 43 的 6.98%，换样本会以约 2.3pp 步进移动。
**曲线形态**（gain 陡降、ceiling 平坦）在此分辨率下稳健；**具体 ceiling 值不稳健**，
对外引用前必须以 `LIMIT=0` 重读。

---

## 2. CI 可跑性：上一轮的 blocker 判断是错的

上一轮把实测列为「阻塞」，理由是缺 provider 凭据。复盘后确认：

| 检查项 | 结果 |
|---|---|
| PAT 身份 | `Lambertyan`（id 35325629） |
| `workflow_dispatch` 权限 | **204 成功** |
| Org secrets | `DEEPSEEK_API_KEY` / `ZHIPU_API_KEY` / `HF_TOKEN` 齐备，历史运行成功 |
| 分支保护 | ruleset `master-protection` 存在但 `enforcement: disabled`；`branches/master/protection` → 404 |
| 产物取出 | artifact API 302 → `*.blob.core.windows.net`，pin 真实 IP 后可下载 |

**`LONGMEMEVAL_PATH` 不需要任何人来填。** `benchmark.yml` 第 84–92 步自行下载数据集，
第 107 步注入该变量：

```yaml
- name: Download LongMemEval-S
  env:
    HF_TOKEN: ${{ secrets.HF_TOKEN }}
  run: |
    mkdir -p "${{ github.workspace }}/data"
    curl -fL --retry 3 --retry-delay 5 \
      -H "Authorization: Bearer ${HF_TOKEN}" \
      -o "${{ github.workspace }}/data/longmemeval_s_cleaned.json" \
      "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json"

- name: Run benchmark
  env:
    LONGMEMEVAL_PATH: ${{ github.workspace }}/data/longmemeval_s_cleaned.json
```

`bench/run.ts:56` 读取它、`:58` 缺失即抛 `LONGMEMEVAL_PATH is required`、`:60` 只要求它是一个
JSON 数组。它是**运行时临时路径**，由 workflow 生成，永远不该人工填写。

**教训**：我把「沙箱内无法执行」错误地升级成了「无法执行」。两者的差别是
「换个执行环境」还是「真的做不到」，而我没有去验证就下了结论。

---

## 3. 本轮发现的 BUG：守卫的爆炸半径

这是**靠运行发现、而非靠读码发现**的缺陷——因为代码单独看是正确的。

### 3.1 现象

Run `35498421148` 在 11 分钟时失败：

```
conjunction ablation cohort is incomplete: 1/7 present, missing 6456829e_abs,
edced276_abs, e5ba910e_abs, gpt4_70e84552_abs, gpt4_c27434e8_abs,
gpt4_fe651585_abs. ...
    at runQueryExpansionDecompositionAblation (runner.ts:831:11)
    at main (bench/run.ts:397:37)
```

**守卫是正确的，且必须继续保持响亮。** R4 的 P2/P3 是针对**七个特定题目**预注册的；
`LIMIT=60` 的分层抽样只保留了 6 个控制中的 1 个，对这个子集打分就等于**用同一个名字
发布另一个实验**。拒绝执行是对的。

### 3.2 真正的问题

守卫的**判决**对，**在程序中的位置**不对。

`bench/run.ts` 在 conjunction 臂之前已经写好了其余全部报告，`main().catch` 只在最后
才持久化 embedding 缓存。于是这个 throw 一路把它们全部带走了：

| 后果 | 细节 |
|---|---|
| 主报告丢失 | `benchmark-report.md` / `.json` 在 08:08 已写盘，但未作为成功产物留存 |
| Markdown 报告丢失 | 同上 |
| embedding 缓存未持久化 | 11 分钟的付费嵌入调用无法被下次运行复用 |
| workflow 红 | `Run benchmark` = failure，读起来像「什么都没产出」 |

产物集之所以还保住了更早的报告，只是因为 `Upload benchmark report` 用了 `if: always()`
——这是**意外的第二道防线**，不是设计。

**缺陷类别**：一个前置条件检查被放在它所保护的工作**之后**，而程序在失败处理时会丢弃
已完成的工作。守卫是为了防止一个错误数字，结果它防掉了整个数字集。

### 3.3 修复（两部分，刻意分开）

**3.3.1 `bench/run.ts` 捕获守卫。** conjunction 臂包在 `try`/`catch` 中。守卫照旧抛出，
消息照旧进 stderr（`conjunction ablation skipped: ...`），其余报告与缓存**存活**。
这次跳过是被**记录**的，不是被**隐藏**的。

**3.3.2 `src/ablation-skip.ts` 记录原因。** 结构化记录——臂名、原始原因、缺失的
cohort 成员 id、分母——每次运行都写入 `benchmark-ablation-skipped.json`，**包括空数组**。

理由：没有它，一个找不到 `benchmark-conjunction-ablation-report.json` 的读者，
无法区分「因已声明的理由被拒绝」与「崩溃」或「从未接线」。产物集现在能解释自己的缺口。

### 3.4 为什么**没有**把守卫降级

最省事的修法是默认 `requireCohortCoverage: false`。这是**错的**：那正是守卫要防的
**空洞通过**——在 `LIMIT=60` 下 P3 退化为一个 0/1 的界，其单侧 95% 上界是 95%，
即**它不可能失败**。现在把严格行为暴露为 `REQUIRE_CONJUNCTION_COHORT`（默认 0），
使这个取舍**显式**，而不是用一个缺陷换另一个缺陷。

### 3.5 测试抓出的两个实现缺陷

**缺陷一（解析错误）。** `parseMissingCohortMembers` 最初用 `/\bmissing\s+([^.]*)\./`。
一个针对**非 cohort 错误**的测试当场拒绝了它：

```ts
parseMissingCohortMembers('the response is missing content.')
// 期望 [] — 实际得到 ['content']
```

未加锚定的模式会把**任何含 "missing" 一词的句子**当成 cohort 缺失，于是一个 provider
错误会被记录成「缺失名为 `content` 的题目」。改为锚定守卫自己的措辞
—— `present, missing <ids>.` ——既更精确，也自我说明。

**缺陷二（死分支）。** `match[1] ?? ''` 分支不可达（`match` 非空时该捕获组必然存在）。
已替换为直接断言 + 注释说明为何不需要回退，而**不是**用 `v8 ignore` 盖住死代码：
解析器里一条不可达分支，会掩盖未来某个把该组删掉的模式改动。

---

## 4. B1 与 A4（上一轮交付，本轮无变更）

### 4.1 读码后修正的三条计划前提

**修正一：管线不是「单通道浅检索」。** `retrieveSessionsForQuestion` 已用 RRF 融合
**4 条通道**。原 B2 表述为「加多通道并行检索」，会重复造一个已存在的轮子。

**修正二：真正的窄口是候选池宽度。** `retrieveTopKByQueries` 在**内部**就执行
`slice(0, topK)`，因此默认配置下重排**只能对 top-K 做排列组合**。已由
`rerankCandidatePool` 解除，并**固化为测试**——故意断言这个限制。

**修正三：弃权风险已经修好。** `maxHitScore()` 早已取代 `hits[0].score`，
且其注释明确写了「弃权信号必须与融合顺序无关」。原计划的预警属于**过度**。

### 4.2 上一轮发现的接线 BUG

首次实现只把重排接进 `retrieveSessionsForQuestion`，而 `answer()` 走的 `retrieveTurns`
**完全没有重排**。后果是：这个阶段「已实现、能被一个调用方触达、却在评测路径上静默缺席」。
修复不是再抄一份调用，而是抽出共享的 `applyRerank()`，使「某条路径忘了重排」在
**结构上不可表达**。

### 4.3 A4

四个包中有三个根本没有 vitest config，所以「≥95% 每维度」一直是**可以被静默违反的约定**。
现已全部加上 `thresholds`，并**实测验证**违反时进程退出码为 1。

---

## 5. 本轮测试与验收证据

| 包 | 测试数 | Stmts | Branch | Funcs | Lines |
|---|---|---|---|---|---|
| cortex-core | 110 | 98.73 | 97.63 | 100 | 98.73 |
| cortex-node | 16 | 100 | 98.61 | 100 | 100 |
| cortex-llm | 71 | 100 | 98.47 | 100 | 100 |
| cortex-eval | 897 | 99.87 | 98.60 | 100 | 99.87 |
| **合计** | **1094** | — | — | — | — |

新增模块 `ablation-skip.ts`：**100 / 100 / 100 / 100**（17 测试）。

**测试方法学**：全程 TDD 先红后绿；**不使用 mock**——仅伪造模型边界（网络调用），
排序算术、平局、去重、降级路径、解析锚定全部为真实测试。
`ablation-skip.ts` 的两处实现改动**都是被测试逼出来的**，不是先写实现再补断言。

---

## 6. 与 07 计划的差异（诚实清单）

| 计划项 | 计划内容 | 实际 | 差异原因 |
|---|---|---|---|
| B2 实测 | 「阻塞于 provider 凭据」 | **已运行** | 上一轮的阻塞判断错误；凭据一直就绪 |
| B2 产出 | 池宽决策数字 | **决策已定：不加宽** | ceiling 93.02% 平坦，gain 在 k≤10 内衰减完 |
| B1 A/B | 未运行 | **仍未运行** | 需 rerank provider 凭据（org 仅有 DeepSeek/Zhipu/HF） |
| 守卫行为 | 无此计划项 | **新增修复** | 靠运行发现的缺陷，计划阶段不可预见 |
| workflow 输入 | 无 rerank 透传 | **已补齐 5 个变量** | 使 B1 A/B 无需改 workflow 即可派发 |

---

## 7. 下一步（按优先级）

| # | 事项 | 前置 | 产出 |
|---|---|---|---|
| 1 | 确认 `fe0daa7` 运行验收：conjunction 缺席但其余报告存活 | 无 | 守卫修复的实测证据 |
| 2 | 执行 B1 A/B（`CORTEX_RERANK=on`，池宽不加） | `RERANK_API_KEY` org secret | 重排的存废判决（含负结论） |
| 3 | A2 全量重测于当前 HEAD | `LIMIT=0`，约 40 分钟 | 发布级 N=500 + Wilson 区间 + run id |
| 4 | A6 受控阅读器矩阵 | 四个阅读器凭据 | 在本管线上验证架构归因 |
| 5 | B3 专用抽取通道 | 1–3 完成 | 架构级改动，需先在单维度验证 |

> **纪律**：第 5 项在任何情况下都**不得**先于第 1–2 项。B3 是成本 × 通道数的架构级改动，
> 而 B1 的 A/B 尚未取得任何实测数据。在仪器刚读出第一个数字时投入架构级改动，
> 正是本仓库历史上多次回滚的模式。

> **给下一轮自己的提醒**：上一轮把「沙箱内不可执行」误判成「不可执行」，代价是整整一轮
> 实测被推迟。**先验证执行环境的边界，再声明 blocker。**
