# Cortex 浏览器端、存储联邦与私有/共享分诊（技术设计）

> 面向 AgentiX-E/cortex。内部设计文档，**设计阶段产物：不含实现**。
> 所有量化结论标注来源：`[POC-n]` 指 `poc/p0n-*` 的可复跑实验，`[论文]`/`[官方文档]` 指外部可信来源，
> 完整对照见 [14 证据登记与 POC](14-evidence-register-and-poc.md)。

---

## 0. 结论先行

1. **纯浏览器可行，且不需要新增子包。** 把 `cortex-node` 改名为 `cortex-storage`（`./sqlite`、`./pg`、
   `./opfs`、`./idb`、`./analytics` 五个 subpath），联邦路由放进 `cortex-core`（纯组合、零 I/O）。
   包数仍是 4 个（core / memory / ai / storage），没有第 5 个。
2. **DuckDB-WASM 不进默认构建。** 它只作按需 `import()` 的导入/分析侧车：它的甜区是列存扫描，
   而产品的写形态是 KV 点写；且它的 HNSW 在浏览器是"崩溃即可能损坏"的组合。
3. **向量不做近似索引。** 精确扫描在浏览器里 60k×384 是 **22.3 ms p50** `[POC-1]`，20k×1024 是 **18.7 ms** `[POC-1]`；
   索引的构建成本与失效风险换不来这点延迟。
4. **私有/共享不允许由模型决定。** CIMemories（FAIR Meta，ICLR 2026）实测前沿模型在"该不该说"上
   违反上下文最高 **69%**、且随使用累积（0.1%→9.6%→25.1%）、加隐私提示词会变得更差 `[论文]`。
   因此：**模型抽取，规则披露，用户盖章**。
5. **规则层只覆盖 26.7% 的候选事实** `[POC-4]`。这不是缺陷，是设计输入：**知识卡片队列不是异常路径，
   而是主路径**。于是"抽取得更少、更准"比"分类器更聪明"更重要。

---

## 1. 四种部署拓扑

| 拓扑 | 引入 | 数据在哪 | 缺省行为 |
| --- | --- | --- | --- |
| **A 纯浏览器** | `cortex-storage/opfs` + `cortex-ai/remote` 或 `cortex-ai/local` | 只在用户设备 | 全私有；无共享知识 |
| **B 纯服务端** | `cortex-storage/sqlite` 或 `./pg` | 只在服务器 | 全共享；无跨设备 |
| **C 双端（读合并）** | A + B + `FederatedStorage` | 私有在本地，共享在远端 | 私有任务读两库；共享任务只读远端 |
| **D 双端（写分诊）** | C + `triage` | 同上，写入时按卡片决定去向 | `defer` 一律落本地 |

**C 与 D 的区别只有一处**：C 是"已经知道哪些是共享的"，D 是"写入时决定哪些可以变成共享"。
两者的读侧策略完全相同，所以 C 可以先用 `p03` 的语义实现并测透，D 的分诊层独立演进 `[POC-3]`。

### 1.1 为什么路由在 core，而不在 memory

`cortex-memory` 今天的入口是 `answerSessions(question, sessions)`——**证据是参数，不是全局状态**。
这条边界让"哪些证据可以进入窗口"成为调用方的决定，于是读侧策略不需要产品知道"私有/共享"这个词。
把 scope 塞进 `cortex-memory` 会让它同时承担"记忆怎么用"与"数据能不能出去"两个正交职责，
并破坏单变量实验纪律（§7 的寄存器口径依赖"配置行能说清这一轮动了什么"）。

`FederatedStorage` 与 `BruteForceVectorIndex` 同属一类：**对契约的纯组合，零 I/O**，可用两个真实
`Storage` 实现完整测试。`poc/p03-federation` 的 9 条断言就是它的验收单 `[POC-3]`。

---

## 2. 存储引擎选型

### 2.1 候选与硬事实

| 引擎 | 持久化 | 向量 | 全文/BM25 | 体积 | 关键风险 |
| --- | --- | --- | --- | --- | --- |
| **SQLite-WASM（官方）+ OPFS-AHP** | 真文件，Worker 内同步句柄 | 需 `sqlite-vec`（**pre-v1 alpha**）或 blob+精确扫描 | **FTS5 内建** | ~1 MB | **Safari 的 252 句柄上限**（PGlite 文档记录同类 VFS 因此不可用） |
| **DuckDB-WASM + OPFS** | 2026-09 起支持 `opfs://`，带 WAL+checkpoint | `array_cosine_similarity` 是核心函数；`vss` 的 HNSW **默认只允许内存库**，落盘需 `hnsw_enable_experimental_persistence`，官方原文："WAL recovery is not yet properly implemented … you can end up with **data loss or corruption of the index**" | FTS 扩展（平台构建受限） | 3–8 MB | 版本悬崖：npm `latest` 曾"建了文件从不写入"，须锁 1.32.0 或 ≥1.33.1-dev64.0 |
| **PGlite + pgvector** | IndexedDB VFS（官方推荐）/ OPFS-AHP | `@electric-sql/pglite-pgvector`（42.9 KB） | `tsvector` | 重（启动 1–2 s），IDB VFS 整库入内存、每次查询后整文件刷盘 | 语义最正统，代价最重 |
| **sqlite-vec + wa-sqlite** | 同 SQLite | `vec0` 虚表 | 需另配 | 小 | README 声称支持浏览器 WASM，但**官方 JS 文档只写 Node/Deno/Bun**，浏览器集成要自己拼三件套 |

### 2.2 决策：SQLite-WASM 作记录层，DuckDB 作侧车

**理由一（写形态）**：产品的写入是"一轮对话一次 upsert + tag + ttl"，是 OLTP 点写；
列存引擎在点的写上是逆着设计走的。DuckDB 自己的定位就是分析。

**理由二（崩溃恢复）**：浏览器标签页被杀死是常态而非异常。把一个官方声明"异常关闭可能损坏索引"
的结构放进这种宿主，是设计错误而不是权衡。

**理由三（实测）**：SQLite-WASM 在 Chromium 里通过**浏览器重启**保住了 10,000 行，摘要逐位相同
（`128079214` = `128079214`），写入 **56,850 行/秒**、checkpoint **1 ms**、主键点读 **0.047 ms** `[POC-1]`。

**DuckDB 的正当位置**：`import('@agentix-e/cortex-storage/analytics')`，只在"导入历史对话/生成记忆画像"
时加载。这是列存甜区，也是当前完全缺失的能力（`cortex-node` 只有 KV）。

### 2.3 实测：dtype 是内存决策，不是时间决策

`[POC-2]`（Node，纯 JS，插入式 top-k，60k×384）：

| dtype | 存储 | p50 |
| --- | --- | --- |
| f64 | 176 MiB | 22.9 ms |
| f32 | 87.9 MiB | 37.5 ms |
| int8 + scale | 22.2 MiB | 44.7 ms |

三者的**时间差小于 2 倍且不单调**（int8 在 JS 里最慢，因为没有 i8x16 点积），而**内存差 8 倍**。
所以：**dtype 按内存预算选，时间按"同数量级"处理**；任何"int8 更快"的说法必须限定在 wasm SIMD 上，
而那是**本设计未测**的部分。

**同一算法在浏览器里更快**：60k×384 在 Chromium 是 **22.3 ms p50 / 33.4 ms p95** `[POC-1]`，
而 Node 的 f32 是 37.5 ms `[POC-2]`。**Node 不能当浏览器的代理**，文档只引用浏览器数字，Node 作为上界。

---

## 3. 分诊：抽取归模型，披露归规则与用户

### 3.1 为什么这条线必须画在这里

CIMemories 的三条实测 `[论文]`：

1. 前沿模型在只用"三个人格标注者一致同意的**简单题**"上，属性级违规最高 **69%**；
2. 违规随任务数与重复次数累积：GPT-5 从 **0.1% → 9.6%**（1→40 任务），同一 prompt 重复 5 次到 **25.1%**；
3. 加隐私提示词**不解决问题**：模型退化成"全说"或"全不说"，完整性崩塌（GPT-4o 违规 14.8% 但完整性仅 43.9%）。

一个错误率这样、且不可复现、且提示词不可修复的判断，不能是"能不能离开设备"的最后一句话。

### 3.2 四层，顺序不可交换

```
候选事实
 ├ 1 确定性规则（本文件 §3.3；可审计、可单测、零成本）
 ├ 2 本地 NER（transformers.js v4，不出设备；Rampart 式"确定层 + 模型层"）
 ├ 3 模型提议（只产出卡片：scope / reason / redactions；confidence 仅用于排序）
 └ 4 用户盖章（默认 private；shared 必须显式点一下；dismissed 为终态）
```

第 2 层的价值不是分类，而是**脱敏预览**：把小模型标注的人名/地名/机构标出来，让卡片能显示"发出去的样子"。
Rampart 的公开形态是 14.7 MB 的 token-classification ONNX（MiniLM-L6 微调，17 类实体，7 种拉丁字母语言），
并明确声明**非拉丁文字召回约 14%** —— 这个限制必须写进产品文案，而不是等用户发现 `[模型卡]`。

### 3.3 规则表（可读一屏，顺序即优先级）

| 序 | 规则 | 目标 | 触发即终止 |
| --- | --- | --- | --- |
| 1 | `credential` | private（**且不建卡**） | 密钥/口令/token/私钥/SSN/PIN |
| 2 | `strong-pii` | private | 邮箱、电话、卡号、证件号、门牌地址 |
| 3 | `money` | private | 金额、收入、预算、债务、房租、付款 |
| 4 | `health` | private | 诊断、用药、就诊、饮食限制、运动、体重 |
| 5 | `family` | private | 家人与伴侣、纪念日 |
| 6 | `career-status` | private | 晋升、薪酬、离职、解雇、面试 |
| 7 | `third-party` | private | 同事/上级/朋友/房东等人 |
| 8 | `org-knowledge` | **shared** | `our team`、`the project`、`the client`、roadmap、sprint、onboarding、deliverable |

**私有一律先跑**，所以"看起来是组织知识、但提到了钱"的句子留在私有。`[POC-4]` 测的就是这个顺序是否成立。

### 3.4 实测，以及它改变了什么设计

`[POC-4]`：60 条真实用户语句（LongMemEval-S），人工标注 12 private / 8 shared / 40 defer，
标注在规则写完之前完成：

| 指标 | 值 | 读法 |
| --- | --- | --- |
| **false-share** | **0 / 12**，Wilson 95% 上界 **24.2%** | 安全方向；但 12 个样本给不出"低于 1%"的承诺 |
| false-private | 4 / 8 | 代价是用户多点一次，可恢复 |
| **coverage** | **26.7%** | 规则只决定四分之一 |
| 三次一致率 | 85.0% | 上下文，不是目标 |
| 10 轮重复稳定性 | **完全一致** | 与模型的 25% 波动形成对照 |

**最重要的数字是 coverage。** 73% 的候选事实没有规则裁决，只能变成卡片。于是产品的主界面是卡片队列，
而不是"分类器准不准"。这条结论直接改了优化目标：

- 上游**抽取要更少更准**（Mem0 的 selective extraction 报告 80% token 削减、仅 6 个百分点精度损失 `[论文]`）；
- 卡片的**批量操作**（接受/编辑/忽略/合并重复）比分类器调优更影响体验；
- `defer` 必须是**默认私有**，因为"没决定"不是"同意"。

### 3.5 一个被 POC 抓到的规则 bug

`career-status` 最初写成 `/\braise\b/`，在 `[POC-4]` 里命中 "…a 5 kilometer walk with my colleagues …
to **raise** funds for a local food bank"，把一次团队慈善步行判成职业事实。修法是加词义约束
（`pay raise` / `pay rise`），**指标未变**（该行仍因提到同事而私有），但审计理由变对了。
这类 bug 只有跑真实语料才会出现——这是 POC 存在的理由，不是测试的替代品。

---

## 4. 知识卡片

### 4.1 结构

```ts
type KnowledgeCard = {
  id: string;
  text: string;                       // 一条原子事实
  scope: 'private' | 'shared' | 'both';
  source: 'declared' | 'inferred';    // UI 必须分开显示
  origin: { sessionId: string; turnIds: string[] };   // 可点开溯源
  reason: string;                     // 为什么是这个 scope（一句话，可读）
  redactions: Array<{ span: [number, number]; label: string }>;
  confidence: number;                 // 只用于排序
  state: 'proposed' | 'accepted' | 'edited' | 'dismissed' | 'stale';
  decayAt?: number;
  createdAt: number; updatedAt: number;
};
```

### 4.2 五条硬规则

1. **`credential` 永不建卡**：连"待确认"都不进，因为它不该存在于任何列表里。
2. **`dismissed` 是终态**：否则用户会学会无视队列（Hyperagent 的文档把这条写成显式设计）。
3. **卡片可导出**（markdown/JSON）：不可导出即锁定，这是 ChatGPT 2025 记忆上线后被批评最狠的一点。
4. **`stale` 期间检索排除**：过期的事实不参与回答，直到用户复核（AideAI 的做法）。
5. **编辑即重算 `reason`**：卡片上的理由必须与卡片内容一致，否则它是装饰。

### 4.3 竞品借鉴（详见 [13 竞品与文献综述](13-competitive-and-literature-survey.md)）

| 来源 | 借什么 | 不借什么 |
| --- | --- | --- |
| Hyperagent | 提案队列"接受前什么都不生效"；三档归属（你的/这个 agent 的/工作区共享）；合并重复 | 其 agent 运行时 |
| AideAI | 敏感度分级触发不同确认强度；"Is this still accurate?"；`Used from memory` 标注；Memory Center 五 tab | 其多 agent 结构 |
| Claude Projects | 记忆按 project 作用域；`pause` 与 `reset` 语义分开 | 闭源实现 |
| Letta | 一个 memory block 可挂多个 agent（共享块） | 其 agent loop 与状态机 |
| Mem0 | 作用域是四维（user/agent/run/app），不是二值 | 其云端抽取 |
| memory card 五原则 | 可见/可编辑/有作用域/可过期/可导出 | —— |

---

## 5. 读侧策略（写侧正确不等于不泄漏）

三条规则落在"谁组装 `sessions`"这一层：

1. **私有行永不进入"将发给第三方"的窗口**——不是靠模型自觉，是靠不给它。
2. 共享任务（起草邮件、给同事的答复）只从远端取；私有任务（个人复盘）取两库并集。
3. 跨库读取必须**带 `origin` 标签**（`p03` 的 `queryAcross` 已验证），因为"这条来自团队知识"
   需要显示给用户，而不是让读者从表名推断 `[POC-3]`。

**未覆盖**：输出侧泄漏——模型在共享任务里"顺口"说出私有事实。这需要输出审查层，本设计没有它，
所以**本设计不宣称安全**，只宣称"写侧边界成立、读侧入口受限"。

---

## 6. 包布局与依赖分层

```
packages/
  cortex-core/       + FederatedStorage（纯路由）
                     + KnowledgeCard / ScopePolicy 类型
                     + TriageRules（确定性规则，纯函数）
  cortex-memory/     不动（不消费 Storage；读侧策略由调用方组装 sessions）
  cortex-ai/         ← cortex-llm 更名 + 条件导出
                       ".": remote + 契约；"./local": transformers v4；"./web": webllm/chrome-ai
                     + TriageProposer（产出卡片，不落库）
                     + PiiDetector（本地 NER）
  cortex-storage/    ← cortex-node 更名
                       ./sqlite  ./pg  ./opfs  ./idb  ./analytics
```

依赖方向（严格单向）：

```
cortex-core  ←  cortex-memory  ←  { cortex-ai, cortex-storage }  ←  cortex-eval(dev)
```

`cortex-storage` 的 `better-sqlite3` / `pg` / `sqlite-wasm` / `duckdb-wasm` 全部是 **optional peer**，
浏览器构建只触达 `./opfs`，打包器不会拉 native 依赖——这一点用体积守卫强制（§8 验收）。

---

## 7. 失败与拒绝语义（沿用本项目的"拒绝而非降级"）

| 场景 | 行为 |
| --- | --- |
| 未知 scope | 抛错（`"both"` 不是存储）`[POC-3]` |
| 跨库事务 | **抛错**，消息给出替代方案（单库事务 + 读时对账）`[POC-3]` |
| OPFS 不可用 | 降级 IDB，并**报告实际用了哪一级** |
| `defer` | 落私有，不落"待定" |
| 本地 NER 模型未下载 | 卡片显示"未脱敏预览"，不静默发送 |
| dimension 不匹配 | 抛错，给迁移提示（重嵌/重建索引），不静默算余弦 |

---

## 8. 验收（本轮设计阶段的"完成"定义）

| 项 | 判据 | 状态 |
| --- | --- | --- |
| OPFS 跨浏览器重启持久 | 摘要逐位相同 + 行数相同 | ✅ `[POC-1]` |
| 向量扫描可交互 | 60k×384 p50 ≤ 50 ms、p95 ≤ 100 ms | ✅ 22.3 / 33.4 ms |
| 联邦边界 | 9 条语义断言全绿，含两条拒绝 | ✅ `[POC-3]` |
| 规则层 false-share | 上界 ≤ 25%（n=60）；扩到 n=600 后再收紧到 ≤5% | ✅ 24.2% |
| 规则层可复现 | 10 轮逐条一致 | ✅ |
| Safari 可用性 | 探针：Safari 上安装 SAH-pool 并写入 1 万行 | ❌ **未测，唯一硬缺口** |
| 体积守卫 | 浏览器入口 ≤ 300 KB 且不含 native 依赖 | 待实现 |
