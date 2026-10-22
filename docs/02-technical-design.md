# Cortex 技术设计方案

> 对象：`AgentiX-E/cortex`。内部设计文档。**本文回答"怎么造"，不回答"造到哪一步"**
> （进度见 [04](04-execution-tracking-report.md)，排期见 [03](03-execution-plan.md)）。
> 证据标记：`[POC-n]` = 本仓 `poc/p0n-*` 可复跑实验；`[实测]` = 基准运行；`[文献]`/`[文档]`/`[厂商]` 同 01。

---

## 0. 决策清单

每条决策都能指到一个 POC、一个官方限制或一次实测。**没有出处的决策不进这一节。**

| # | 决策 | 反面（我们拒绝的） | 依据 |
|---|---|---|---|
| 1 | 四个包不变：`core` / `memory` / `ai` / `storage` | 新增第 5 个包放浏览器后端 | 浏览器差异全在"句柄与 VFS"，是一个 subpath 的宽度 `[POC-1]` |
| 2 | `cortex-node` → `cortex-storage`，五个 subpath | 单一入口按环境分支 | 打包器能静态裁剪，native 依赖全部 optional peer `[文档]` |
| 3 | `cortex-llm` → `cortex-ai`（`./local`/`./web`） | 保留 `-llm` 名字再加 embedding 子包 | 名字必须覆盖 embedding / rerank / 端侧推理 `[文档]` |
| 4 | 记录层 = SQLite-WASM + OPFS-AHP | DuckDB 作记录层 / PGlite 作默认 | 写形态是点写；DuckDB 的 HNSW 落盘官方称可能损坏；PGlite 整库入内存 `[文档]` |
| 5 | 向量 = 精确扫描 + 固定缓冲 top-k | 浏览器 HNSW | 60k×384 只需 22.3 ms p50 `[POC-1]` |
| 6 | dtype 按**内存**选，不按时间选 | "int8 更快" | 时间差 <2× 且不单调，内存差 8× `[POC-2]` |
| 7 | 披露 = 规则 → 用户；模型只提议 | 模型判断 scope | 69% / 25% 波动 / 提示词无效 `[文献]`；0/12 `[POC-4]`、`[POC-5]` |
| 8 | `defer` 默认私有 | `defer` 落共享 | 落共享立刻泄漏 3/12 且不可逆 `[POC-5]` |
| 9 | 两库物理分离 + 表前缀命名空间 | 单库权限位 | 企业单图假设不成立 `[文档]` |
| 10 | 共享窗口中若有非 shared 行 → **抛错** | 过滤掉继续 | 过滤会让写侧缺陷看起来边界完好 `[POC-5]` |
| 11 | 跨库事务**拒绝** | 假装两阶段提交 | 两个 SQLite 文件没有共同提交点 `[POC-3]` |
| 12 | 重排实现但默认关闭 | 默认开 | 两臂 Δ ±1.33 pp、p=0.7539 `[实测]` |

---

## 1. 架构与包布局

```
packages/
  cortex-core/      契约 + 纯算法（零 I/O），双端
                    + FederatedStorage（纯路由）
                    + TriageRules（确定性规则，纯函数）
                    + KnowledgeCard / ScopePolicy 类型
  cortex-memory/    组合层：把 core 的能力组合成 MemorySystem（不消费 Storage）
  cortex-ai/        ← cortex-llm 更名
                    ".":        远程 provider 契约
                    "./local":  transformers.js v4（本地 embedding / rerank）
                    "./web":    webllm / chrome-ai（离线演示档）
                    + TriageProposer（产出卡片，不落库）+ PiiDetector
  cortex-storage/   ← cortex-node 更名
                    ./sqlite  ./pg  ./opfs  ./idb  ./analytics
```

依赖方向（严格单向，无环）：

```
cortex-core  ←  cortex-memory  ←  { cortex-ai, cortex-storage }   ←  cortex-eval (dev)
```

**一条必须记住的事实**：`cortex-memory` **不消费 `Storage`** —— 契约与两个实现都在，消费方为零。
因此四种部署形态的工作量主要在**组合层与读侧策略**，不在新目录。

### 1.1 为什么不是第五个包

浏览器的差异不是"另一套能力"，而是"同一套 SQL 在另一种句柄语义上跑"。把它做成包，会让
`cortex-storage` 与 `cortex-browser` 共享 90% 的 SQL 而各自维护 schema；做成 subpath，schema
只有一份，差异被关在 VFS 里。`[POC-1]` 的 Worker + AHP 池是这条判断的实现形态：约 120 行。

**代价（诚实写出）**：subpath 的入口必须能被静态分析。任何 `if (isBrowser)` 的运行时分支都会
把 native 依赖拉进浏览器包，因此**体积守卫是这条决策的组成部分，不是附加项**：浏览器入口
≤300 KB 且不含 native 依赖，CI 里用打包产物断言，而不是靠 review。

### 1.2 依赖分层与 optional peer

`better-sqlite3` / `pg` / `@sqlite.org/sqlite-wasm` / `@duckdb/duckdb-wasm` 全部声明为
**optional peerDependencies**：装了才用，没装则对应 subpath 在 `import` 时给出明确错误
（"this subpath needs X" 而不是 `MODULE_NOT_FOUND`）。

---

## 2. 抽象层

### 2.1 Storage

```ts
interface Storage {
  put(table: string, key: string, value: unknown, opts?: { tags?: string[]; ttlMs?: number }): Promise<void>;
  get<T>(table: string, key: string): Promise<T | undefined>;
  del(table: string, key: string): Promise<void>;
  query<T>(table: string, predicate: QueryPredicate): Promise<T[]>;
  transaction<T>(fn: (tx: StorageTx) => Promise<T>): Promise<T>;
  close(): Promise<void>;
}
```

六个方法、无 `scope` 字段。**加一个 `scope` 会把策略词写进存储原语**，并迫使每个既有后端改契约；
命名空间前缀（`private/facts`、`shared/facts`）承载同样信息，而且这正是 Mem0（四维 id）与
Redis Agent Memory（命名空间）已经在用的地方 `[文档]`。

### 2.2 Vector

```ts
interface VectorIndex {
  add(id: string, vector: Float64Array, meta?: unknown): Promise<void>;
  search(query: Float64Array, k: number, filter?: Filter): Promise<VectorHit[]>;
  remove(id: string): Promise<void>;
  size(): Promise<number>;
}
```

固定缓冲 top-k 是**契约的一部分**（见 §4.1 的簿记教训）：实现不得在候选上调用 `sort()`。

### 2.3 LLM / Embedding

```ts
interface LLM { complete(prompt: string, opts?): Promise<string>; completeStructured<T>(prompt: string, schema: JsonSchema, opts?): Promise<T>; }
interface EmbeddingModel { embed(texts: string[]): Promise<Float64Array[]>; dimension(): number; }
```

`provider-agnostic` 是硬要求：任何组件（含分诊提议器、重排、裁判）都只依赖这两个接口，
**不允许出现某个 provider 的类型**。统一转 `Float64Array`，不让 float32 截断污染下游统计。

### 2.4 Graph

```ts
interface MemoryGraph {
  addEdge(a: string, b: string, weight: number, kind?: EdgeKind): void;
  neighbors(id: string): Iterable<{ id: string; weight: number }>;
  spreadingActivation(seeds: string[], maxDepth: number): Map<string, number>;
  shortestPath(a: string, b: string): string[] | null;
}
```

### 2.5 FederatedStorage（纯组合，零 I/O）

路由规则：表名前缀决定 store（无前缀 = private，**默认必须是安全的那一侧**，否则忘记写前缀
的调用方等于发布）。前缀是路由标记，**不是库内命名空间**：`private/facts` 与 `shared/facts`
在各自库里都叫 `facts`，否则跨库读要知道两套名字。`[POC-3]` 的首版正是踩了这个坑
（`queryAcross` 返回空），修正后 9 条断言全绿。

`queryAcross` 为每行附加 `origin: 'private' | 'shared'`。这个标签不是装饰：私有任务把"我的"
与"团队的"混在一个窗口里，提示词/引用列表必须能说清哪条是哪条。

---

## 3. 存储引擎选型

### 3.1 候选与硬事实

| 引擎 | 持久化 | 向量 | 全文 | 体积 | 关键风险 |
|---|---|---|---|---|---|
| **SQLite-WASM + OPFS-AHP** | 真文件，Worker 内同步句柄 | `sqlite-vec`（pre-v1）或 blob + 精确扫描 | **FTS5 内建** | ~1 MB | Safari 的 252 句柄上限 `[文档]` |
| **DuckDB-WASM + OPFS** | 2026-09 起支持 `opfs://`（WAL + checkpoint） | `array_cosine_similarity`；`vss` 的 HNSW 默认只许内存库，落盘需实验开关，官方原文："WAL recovery is not yet properly implemented … data loss or **corruption of the index**" `[文档]` | FTS 扩展受限 | 3–8 MB | npm `latest` 曾"建了文件从不写入"，须锁 1.32.0 或 ≥1.33.1-dev64.0 |
| **PGlite + pgvector** | IndexedDB VFS（官方推荐）/ OPFS-AHP | pgvector 外置包（42.9 KB） | `tsvector` | 重（启动 1–2 s） | IDB VFS 整库入内存、每次查询整文件刷盘；**OPFS-AHP 明确不支持 Safari** `[文档]` |
| **sqlite-vec + wa-sqlite** | 同 SQLite | `vec0` 虚表 | 需另配 | 小 | 官方 JS 文档只覆盖 Node/Deno/Bun，浏览器要自己拼三件套 `[文档]` |

### 3.2 决策：SQLite-WASM 作记录层，DuckDB 作侧车

三条理由，按强度排序：

1. **写形态**：产品的写入是"一轮对话一次 upsert + tag + ttl"，是 OLTP 点写。列存引擎在点写上
   是逆着设计走的。
2. **崩溃恢复**：标签页被杀死是常态而非异常。把一个官方声明"异常关闭可能损坏索引"的结构放进
   这种宿主，是设计错误而不是权衡。
3. **实测**：`[POC-1]` 跨**浏览器进程重启**保住 10,000 行，摘要逐位相同 `128079214`。

**DuckDB 的正当位置**：`import('@agentix-e/cortex-storage/analytics')`，只在"导入历史对话 /
生成记忆画像"时加载。这是列存甜区，也是当前完全缺失的能力（今天只有 KV）。

### 3.3 `[POC-1]` 的方法与边界

**方法**：持久化 profile 启动两次。第一次写 10,000 行（480 字符 payload，带 tag 索引，单事务）→
`wal_checkpoint(TRUNCATE)` → 全表回读算 FNV-1a 摘要 → **关闭浏览器进程**。第二次新进程读同库、
再算摘要。摘要与行数同时相同才记"持久"。

| 量 | 值 |
|---|---|
| 写入 | 56,850 行/秒 |
| checkpoint | 0.8 ms |
| 主键点读 | 0.047 ms |
| tag 查询 | 3.2 ms |
| 10k 全表回读 | 60 ms |
| profile 体积 | 10.9 MiB |
| 摘要（两次） | `128079214` = `128079214` |

**Safari 已经测了（`[POC-1]` 的 WebDriver 分支，macOS runner）**：Safari 26.6（WebKit 605.1.15）
通过 `safaridriver` 报告 `vfs: opfs-sahpool`、`sahPool: true`，写 1,000 行用 **72 ms**
（13,889 行/秒）、checkpoint **1 ms**、init 185 ms，回读 1,000 行摘要一致。

> **两份读数不能混为一谈**：Chromium 那份证明的是**跨进程重启的持久性**（10,000 行、摘要逐位
> 相同）；Safari 这份证明的是**句柄池能装上、能读写**（单会话、1,000 行、**没有**重启测试 ——
> WebDriver 会话不是持久 profile）。**PGlite 文档记录的 252 句柄墙，没有挡住 sqlite-wasm 的池**，
> 但这不等于"Safari 上数据一定能活过重启"。

**仍然证明不了**：多标签页并发写、配额耗尽时的行为、以及 Safari 上的跨重启持久性。

**一条工具链事实（不是浏览器事实）**：Playwright 自带 WebKit 在本 runner 上**无法启动** ——
`Protocol error (Page.overrideSetting): Unknown setting: PushAPIEnabled`，有头无头都一样，
属于包与浏览器构建的协议错配。因此它只作诊断，不参与判定；判定由真 Safari 给出。

**一个实现层面的坑值得留档**：`oo1.OpfsDb` 在 3.54.1-build1 里**不是构造器** —— 该 bundler
构建未注册 `opfs` VFS。改用 `installOpfsSAHPoolVfs` 后可用；同时 `sqlite3-*` 的路径要挂到
origin 根，否则 async proxy worker 以文档相对路径解析会 404。

---

## 4. 向量检索

### 4.1 dtype 是内存决策，不是时间决策

`[POC-2]`（Node，纯 JS，插入式 top-k，60k×384）：

| dtype | 存储 | p50 |
|---|---|---|
| f64 | 176 MiB | 22.9 ms |
| f32 | 87.9 MiB | 37.5 ms |
| int8 + scale | 22.2 MiB | 44.7 ms |

时间差小于 2 倍**且不单调**（int8 在纯 JS 里最慢，因为没有 i8x16 点积），**内存差 8 倍**。
所以：**dtype 按内存预算选，时间按"同数量级"处理**。任何"int8 更快"的说法必须限定在 wasm SIMD 上，
而那是**本设计未测**的部分。

**方法教训（保留在脚本 docstring 里）**：第一版 f64 读到 16.2 ms、f32 读到 37.9 ms —— 宽存储反而
快 2.3 倍，明显不可能。原因不是 dtype，而是 **top-k 的簿记**：每命中即 `Array.sort()`。改为固定
插入缓冲后，同一批向量上 f64 落到 **22.9 ms**、f32 落到 **37.5 ms**（即上表），三者的差异回到
同数量级。**基准的簿记可以伪装成算法。**

### 4.2 运行时不能互相代理

同一扫描在 Chromium 是 **22.3 ms p50 / 33.4 ms p95** `[POC-1]`，比 Node 的 f32 37.5 ms 快 1.7 倍。
**文档只引用浏览器数字，Node 作为上界。** 这条写进方法规则，因为"在 Node 里量浏览器"是这类
设计最常见的伪证。

### 4.3 为什么拒绝浏览器 HNSW

60k 上构建是秒级到分钟级，收益是 20 ms → 5 ms。在交互预算里这 15 ms 换不来一个"崩溃可能损坏、
失效需重建"的结构。**留作 P3**：`sqlite-vec` 的 `vec0` 虚表（含向量类型与元数据列），前提是
先解决浏览器加载路径。

---

## 5. 披露分诊

### 5.1 为什么线必须画在这里

CIMemories 的三条实测 `[文献]`：

1. 前沿模型在只用"三个人格标注者一致同意的**简单题**"上，属性级违规最高 **69%**；
2. 违规随任务数与重复次数累积：GPT-5 从 **0.1% → 9.6%**（1→40 任务），同 prompt 重复 5 次到 **25.1%**；
3. 加隐私提示词**不解决问题**：模型退化成"全说"或"全不说"（GPT-4o 违规 14.8% 但完整性仅 43.9%）。

一个错误率这样、不可复现、且提示词不可修复的判断，不能是"能不能离开设备"的最后一句话。

### 5.2 四层，顺序不可交换

```
候选事实
 ├ 1 确定性规则（§5.3；可审计、可单测、零成本）
 ├ 2 本地 NER（transformers.js v4，不出设备；"确定层 + 模型层"两层结构）
 ├ 3 模型提议（只产出卡片：scope / reason / redactions；confidence 只用于排序）
 └ 4 用户盖章（默认 private；shared 必须显式点一下；dismissed 为终态）
```

第 2 层的价值不是分类，而是**脱敏预览**：把小模型标注的人名/地名/机构标出来，让卡片显示
"发出去的样子"。Rampart 的公开形态是 14.7 MB token-classification ONNX（MiniLM-L6，17 类实体，
7 种拉丁字母语言），并明确声明**非拉丁文字召回约 14%** `[厂商]` —— 这个限制必须写进产品文案，
而不是等用户发现。

### 5.3 规则表（可读一屏，顺序即优先级）

| 序 | 规则 | 目标 | 触发即终止 |
|---|---|---|---|
| 1 | `credential` | private（**且不建卡**） | 密钥/口令/token/私钥/SSN/PIN |
| 2 | `strong-pii` | private | 邮箱、电话、卡号、证件号、门牌地址 |
| 3 | `money` | private | 金额、收入、预算、债务、房租、付款 |
| 4 | `health` | private | 诊断、用药、就诊、饮食限制、运动、体重 |
| 5 | `family` | private | 家人与伴侣、纪念日 |
| 6 | `career-status` | private | 晋升、薪酬、离职、解雇、面试 |
| 7 | `third-party` | private | 同事/上级/朋友/房东等人 |
| 8 | `org-knowledge` | **shared** | `our team`、`the project`、`the client`、roadmap、sprint、onboarding、deliverable |

**私有一律先跑**，所以"看起来是组织知识、但提到了钱"的句子留在私有。这个顺序就是 fail-closed
的全部论证，`[POC-4]` 测的就是它是否成立。

### 5.4 实测，以及它改变了什么设计

`[POC-4]`：60 条真实用户语句（LongMemEval-S），**先**按公开政策人工标注 12 private / 8 shared /
40 defer，**再**写规则（避免循环）。

| 指标 | 值 | 读法 |
|---|---|---|
| **false-share** | **0 / 12**，Wilson 95% 上界 **24.2%** | 安全方向；但 12 个样本给不出"低于 1%"的承诺 |
| false-private | 4 / 8 | 代价是用户多点一次，可恢复 |
| **coverage** | **26.7%** | 规则只决定四分之一 |
| 三次一致率 | 85.0% | 上下文，不是目标 |
| 10 轮重复 | **逐条一致** | 与模型的 25% 波动形成对照 |

**最重要的数字是 coverage。** 73% 的候选事实只能变成卡片，于是产品主界面是**卡片队列**，
而不是"分类器准不准"。这条结论直接改了优化目标：

- 上游**抽取要更少更准**（Mem0 的 selective extraction 报 80% token 削减、6 pp 精度损失 `[文献]`）；
- 卡片的**批量操作**（接受/编辑/忽略/合并）比分类器调优更影响体验；
- `defer` 必须**默认私有**，因为"没决定"不是"同意"。

**一个被 POC 抓到的规则 bug**：`career-status` 最初写成 `/\braise\b/`，命中"…a 5 kilometer walk
with my colleagues … to **raise** funds for a local food bank"，把一次团队慈善步行判成职业事实。
修法是加词义约束（`pay raise` / `pay rise`），**指标未变**（该行仍因提到同事而私有），但审计
理由变对了。这类 bug 只有跑真实语料才会出现。

### 5.4.1 在 1,467 条候选事实上复核（`[POC-6]`）

60 条标注集能回答"策略对不对"，回答不了"覆盖率是不是小样本的偶然"。CIMemories 的 10 个 persona
提供了 **1,467 条已经是原子事实的语句**（每条带 `information_domain`），且其数据文件就在仓库里，
可用 api.github.com 取得 —— 不需要 Hub，也不需要新标注。

| 量 | 值 | 读法 |
|---|---|---|
| coverage | **28.4%**（95% CI 26.1–30.7） | 与 60 条上的 26.7% 一致：四分之一是真的 |
| 按领域 | finance 90.8%、mental_health 37.7%、housing 29.8%、employment 19.2%、health 11.3%（修补前） | `money` 规则在财务事实上一击即中；`health` 最弱 |
| leak | **NOT MEASURED** | 发布规则 `org-knowledge` **0/1,467 命中** —— 结构性零 |

**这一轮抓到的真实缺陷**：健康规则对**生理测量**完全沉默 —— "blood pressure 138 over 86"、
"liver function test showed ALT 28 and AST 22"、"I average 7.5 hours of sleep"。它们不泄漏
（`defer` 落私有），代价是用户多卡片，所以此前的 false-share 审计看不见它们。补上 vitals 词族后
coverage 24.9% → **28.4%**，而 p04 三项指标一位未动 —— 修补由政策辩护，不由语料调参。

**这一轮否掉的诱惑**：不要把 0/1,467 写成"上界 0.26%"。被测机制一次没触发，零就是空白。
因此 `p06` 在报告 leak 之前**先报发布规则的命中次数**，为 0 就把 leak 打成 `NOT MEASURED`。

### 5.5 知识卡片

```ts
type KnowledgeCard = {
  id: string;
  text: string;                       // 一条原子事实
  scope: 'private' | 'shared' | 'both';
  source: 'declared' | 'inferred';    // UI 必须分开显示
  origin: { sessionId: string; turns: string[] };   // 可点开溯源
  reason: string;                     // 为什么是这个 scope（一句话，可读）
  redactions: Array<{ span: [number, number]; label: string }>;
  confidence: number;                 // 只用于排序
  state: 'proposed' | 'accepted' | 'edited' | 'dismissed' | 'stale';
  decayAt?: number;
  createdAt: number; updatedAt: number;
};
```

五条硬规则：

1. **`credential` 永不建卡**：连"待确认"都不进，因为它不该存在于任何列表里。
2. **`dismissed` 是终态**：否则用户会学会无视队列（Hyperagent 把这条写成显式设计）。
3. **卡片可导出**（markdown/JSON）：不可导出即锁定 —— ChatGPT 2025 记忆上线后被批评最狠的一点。
4. **`stale` 期间检索排除**：过期事实不参与回答，直到用户复核。
5. **编辑即重算 `reason`**：卡片上的理由必须与内容一致，否则它是装饰。

借什么 / 不借什么：借 Hyperagent 的"接受前什么都不生效 + 三档归属 + 合并重复"，借 AideAI 的
敏感度分级与"Is this still accurate?"，借 memory card 五原则（可见/可编辑/有作用域/可过期/可导出）；
**不借**"账号级列表即全部"（列表是审计面，**写入点的确认**才是控制面），**不借** hover 才出控件。

### 5.6 端到端，以及三条消融

`[POC-5]` 把规则、两个库、读侧组装器接起来，在同一 60 条标注上跑四种用户策略：

| 策略 | leak | 上界 | reach/shared | reach/private | noise |
|---|---|---|---|---|---|
| `rules-only`（出厂默认） | **0 / 12** | 24.2% | **4 / 8** | 12 / 12 | 0 / 40 |
| `oracle`（完美确认卡片） | 0 / 12 | 24.2% | **8 / 8** | 12 / 12 | 0 / 40 |
| `defer-shared`（**A4**：一行代码） | **3 / 12** | 53.2% | 7 / 8 | 12 / 12 | 38 / 40 |
| `no-triage`（**A1**：不要规则层） | **12 / 12** | 100% | 8 / 8 | 12 / 12 | 40 / 40 |

三条读数，每条都改了设计：

1. **边界成立，代价是可达性**：出厂默认零泄漏，但共享任务只能看到一半本可共享的事实。
   **这不是缺陷，是队列存在的理由** —— `oracle` 那一行就是队列的上限价值（+4 条）。
2. **A4 的代价是 3 条不可逆泄漏**：`defer` 落共享只多买到 3 条可达事实，代价是发布 3 条私有
   事实，且没有事后审计能收回。**因此这一行代码不能合并。**
3. **A1 证明规则层是承重的**：没有它，12/12 私有事实进共享库。

**守卫的定价方式（方法上最重要的一条）**：`[POC-5]` 的 scope 守卫在写侧正确时是**冗余的**，
所以一次干净运行对它是零证据。唯一能证明它承重的办法是**故障注入** —— 绕过路由，把一条私有行
直接写进共享库：guard on 抛 `ScopeViolation`（拒绝组装提示词），guard off 同一行进窗口。
**一个只在正常路径上被看到通过的检查，与一个不可能失败的检查无法区分。**

---

## 6. 读写边界

### 6.1 四种拓扑

| 拓扑 | 引入 | 数据在哪 | 缺省行为 |
|---|---|---|---|
| A 纯浏览器 | `storage/opfs` + `ai/remote` 或 `ai/local` | 只在用户设备 | 全私有；无共享知识 |
| B 纯服务端 | `storage/sqlite` 或 `./pg` | 只在服务器 | 全共享；无跨设备 |
| C 双端（读合并） | A + B + `FederatedStorage` | 私有本地、共享远端 | 私有任务读两库；共享任务只读远端 |
| D 双端（写分诊） | C + 分诊 | 同上，写入时按卡片决定 | `defer` 一律落本地 |

C 与 D 的区别只有一处：C 是"已经知道哪些是共享的"，D 是"写入时决定哪些可以变成共享"。
两者的读侧策略完全相同，所以 C 可以先用 `[POC-3]` 的语义实现并测透。

### 6.2 为什么路由在 core，不在 memory

`cortex-memory` 的入口是 `answerSessions(question, sessions)` —— **证据是参数，不是全局状态**。
这条边界让"哪些证据可以进入窗口"成为调用方的决定，于是读侧策略不需要产品知道"私有/共享"这个词。
把 scope 塞进 `cortex-memory` 会让它同时承担"记忆怎么用"与"数据能不能出去"两个正交职责，
并破坏单变量实验纪律（配置行必须能说清这一轮动了什么）。

`FederatedStorage` 与 `BruteForceVectorIndex` 同属一类：**对契约的纯组合、零 I/O**，可用两个
真实 `Storage` 实现完整测试。`[POC-3]` 的 9 条断言就是它的验收单。

### 6.3 读侧策略（`[POC-7]` 之后改写）

1. **私有行永不进入"将发给第三方"的窗口** —— 不是靠模型自觉，是靠不查询那个库。
2. 共享任务只从远端取；私有任务取两库并集并按 id 去重（**owner 的副本优先**）。
3. 跨库读取必须带 `origin` 标签，因为"这条来自团队知识"需要显示给用户，而不是让读者从表名推断。
4. 共享窗口里出现非 `shared` 行 → **抛错**，不是过滤（§5.6 的守卫）。

**一条被实测逼出来的修正**：初版策略假设"共享库 = 私有证据流中可共享的那部分"。在真实运行
展示过的 59,675 条轮次上，那部分只有 **0.52%**，并且 **63.6%** 的问题一条都没有 `[POC-7]`。
所以正经的形态是：

| 侧 | 内容从哪来 | 为什么 |
|---|---|---|
| 私有库 | 抽取的全部候选事实 | 记忆的默认归宿；`defer` 也在这里 |
| 共享库 | **只来自被用户确认的卡片** | 过滤得到 0.52%，确认才能得到"够用" |

推论：拓扑 C/D 的价值不在"自动分流"，而在**把共享变成一次显式授权**；自动分流那部分只适用
于语料里本来就充满组织语言的负载（工作协作），而本仓库还没有那样一份语料 —— 这是 04 §7 的 G2
要的第二样东西。

### 6.4 输出侧：把"顺口说出"变成一次可拒绝的检查

写侧边界成立不等于不泄漏。读者可以在共享任务里引用一条私有事实 —— 它不在窗口里，但模型记得
（权重里、或上一轮上下文里）。这是本设计此前**唯一没有覆盖**的泄漏面。

设计（三层，从便宜到贵，全部复用同一张规则表）：

| 层 | 做什么 | 拒绝方式 | 成本 |
|---|---|---|---|
| O1 草稿扫描 | 把即将发出的回答过一遍 `TriageRules`；命中任一 private 规则 → 不给用户看，先要一次确认 | 拒绝发布，附"这一段包含 X" | 纯函数，<1 ms/段 |
| O2 归因检查 | 回答里的每条 `Used from memory` 引用必须能在**本次允许的窗口**里找到 | 找不到 = 来源不明，标红 | 一次集合查找 |
| O3 密文回显 | 若回答逐字复现了窗口**之外**的私有行（≥N 字符连续匹配），视为泄漏 | 拦下并要求改写 | 需要私有行的指纹索引 |

**它买不到什么**：改写与概括。模型把"我的信用卡号是 4111…"说成"我的卡尾号 4111"时 O1/O3 都
可能放过。所以这一层的承诺只能是**"减少"而不是"消除"**，并且必须与 §6.3 的写侧边界分开陈述 ——
把两者混成一句"我们不泄漏"，就是本报告一直在防的那类措辞。

**为什么仍然值得做**：O1 是纯函数、零依赖、可单测；O2 在一次装配里就能得到；两者把"顺口说出"
从"无检查"变成"有一次拦截"。O3 需要指纹索引，标为 P2。

**验收（实现阶段）**：O1 在 p04 的 60 条上必须零误拦共享事实（否则用户会关掉它）；O2 在任何
窗口上必须 100% 可解释；O3 用注入测量召回。

**未覆盖**：改写式泄漏、跨会话记忆残留（模型在上一轮见过私有行）。

### 6.4 拒绝而非降级

| 场景 | 行为 |
|---|---|
| 未知 scope | 抛错（`"both"` 不是存储）`[POC-3]` |
| 跨库事务 | **抛错**，消息给出替代（单库事务 + 读时对账）`[POC-3]` |
| OPFS 不可用 | 降级 IDB，并**报告实际用了哪一级** |
| `defer` | 落私有，不落"待定" |
| 本地 NER 未下载 | 卡片显示"未脱敏预览"，不静默发送 |
| dimension 不匹配 | 抛错 + 迁移提示，不静默算余弦 |

---

## 7. 认知层算法（设计面）

> 本节描述**设计意图**。实现状态见 01 §4；除阈值式弃权外，以下能力**均不在评测路径上**。

### 7.1 价值驱动写入 + 弃权

记忆条目 = `{ content, value, confidence, source, timestamps }`；写入决策 `write = U > threshold`，
效用可插拔（启发式 VoI / 习得策略）；检索决策返回 `null` 当 `max U < τ`，τ 用留出集校准；
置信度用 Platt/temperature 校准。**当前 `defaultValueFunction` 是三项启发式
（`confidence × sourceTrust × recency`），不是 MDP 学到的。**

### 7.2 异步巩固

`w_ij ← w_ij + η·σ(共激活显著性)·(1−w_ij)`，全局突触衰减；显著性用统计显著性（观测/期望共激活）
抑制噪声关联；FSRS 稳定性随检索增益更新；跨层蒸馏用 Sinkhorn 最优传输约束；信用分配沿 DAG 用
TD(λ) 资格迹。**当前只实现前三项的前两项与阈值遗忘；`sinkhorn` 未接线；TD(λ) 不存在。**

### 7.3 双时态 + 冲突消解

事实 = `(s, p, o, valid_from, valid_until, system_from, system_until, source, confidence)`；
"当前有效值"走区间索引；冲突 = 时序优先 + 贝叶斯证据融合（来源可信度加权 + 后验更新）。

### 7.4 抽取保真（IB）

显式优化 `max I(M;未来) − β·I(M;原始)`，把"丢多少留多少"变成可求导目标。未实现。

### 7.5 数学工具

| 工具 | 用途 | 实现 |
|---|---|---|
| Sinkhorn | 巩固蒸馏、多样性 | `ml-matrix`，收敛检测须用**副本**（曾因别名恒真） |
| SVD / 特征分解 | 降维、谱聚类 | `ml-matrix` Jacobi |
| Welch's t-test / Wilson / McNemar | 显著性 | 自研，Kahan + Welford |
| FSRS | 衰减 | 自研（注意量纲，见 04 §4） |

---

## 8. 证据组装与提示词接口

提示词由三个**可各自移动**的部件组成：**证据**（哪些轮次）、**渲染**（`numbered` / `sourced`：
怎么印）、**问法**（`route` / `extractive` / `aggregate` / `computed` / `enumerated` / `sweep`：
模型被要求做什么）。

四条纪律，每一条都对应一次实测教训：

1. **触达必须是产物的一部分**（`ASK_ROUTES`）：一个 run 必须说清哪些路由的指令真的变了，
   否则"处理没有到达提示词"会被读成"处理无效"。已建成 8 ask × 6 路由的单条不变量测试，
   突变检验红 3 条。
2. **对照组必须逐字符成立**：`reviewPass: audit` 那次，对照组首次逐字符可比，才敢下"更差"的
   结论（73 道改变、修 7 坏 21、MR 84→70）。
3. **一句提示词的价值可以被定价**：aggregation 那次 fallthrough 撤掉了 merging sentence，
   TR 直接从 94.2 掉到 72.8、IE 136.2→127.5 —— 单句值 **TR −21.4 / IE −8.7**。该运行因此作废，
   但它把"别乱删句子"变成了一个数。
4. **预算重新选证据，而不是在提示词后追加**：`reviewPass` 用 `fitToBudget` 重新选，第一遍弃答
   时不做第二遍，触达是结构性的（长在 `answerSessions` 里），所以其它五条路由不可能被误配进来。

**证据角色的边界**：`CortexMemory` 接受 `evidenceRoles`（允许的角色）、`evidenceRolesRoutes`
（触达哪些路由）、`roleOf`（把一轮读成角色的回调）。格式知识由调用方提供 —— **产品不解析任何
数据集格式**。三种状态都被决定：缺席 = 不过滤且提示词逐字节不变；`roleOf` 返回 `undefined` =
**保留**该轮（分类器失败不能读成"没有证据"）；空集合 = **构造期拒绝**。

---

## 9. 选型矩阵（自研 vs 引入）

| 域 | 选择 | 为什么不是别的 |
|---|---|---|
| 存储（Node） | `better-sqlite3` | 同步、成熟、可加载扩展；`node:sqlite` 仍 experimental；DuckDB 非 OLTP |
| 存储（远程） | `pg` + pgvector | 标准；`pg-mem` 让测试用真实 SQL 而不 mock |
| 存储（浏览器） | `@sqlite.org/sqlite-wasm` | 官方、OPFS 两种 VFS；`sql.js` 无 OPFS；`absurd-sql` 维护弱 |
| 向量 | 自研暴力 + 固定缓冲 | 精确即可满足（22.3 ms）；`sqlite-vec` pre-v1 |
| 线代 | `ml-matrix` | 纯 JS、Float64、Jacobi SVD、双端；`mathjs` 缺 SVD；`tfjs` float32；`vectorious` 不能跨浏览器 |
| 图 | `graphology` | 纯 JS、零依赖、双端 |
| 本地 embedding | transformers.js v4 | 双端、离线；WebLLM 仅 WebGPU |
| LLM | 自建 fetch 适配器 | 只需两个原语；Vercel `ai` 抽象层重 |
| 测试 | vitest + v8 + fast-check + pg-mem + playwright | 属性测试抓"点检查抓不到的"（网格性质测试抓到递归不动点） |

**自研的边界**：算法核心（价值、弃权、巩固、双时态、冲突、OT、IB、FSRS、统计）全部自研 ——
这是护城河，也需要 Float64 与可解释性；基础设施（存储、线代、图、推理运行时）引入成熟包。

---

## 10. 端侧推理

| 运行时 | 形态 | 关键限制 | 出处 |
|---|---|---|---|
| **transformers.js v4**（4.3.1） | ONNX Runtime Web；默认 WASM(q8)，可选 WebGPU | WebGPU 官方 README 仍标"experimental in many browsers" | `[文档]` |
| ONNX Runtime Web | wasm / webgpu / webnn / webgl | WASM 多线程需 COOP+COEP（未开慢 3–4×）；>50M 参数 WebGPU 才有明显优势，<10M 两者接近 | `[文档]` |
| WebLLM 0.2.85 | 仅 WebGPU | 无 WebGPU 即不可用；60–100 tok/s | `[厂商]` |
| wllama | llama.cpp → WASM | CPU 5–15 tok/s | `[厂商]` |
| Chrome Prompt API | 浏览器内置 Gemini Nano | Chrome 148+ 桌面、>4 GB VRAM、约 22 GB 磁盘、会被驱逐；移动端与 FF/Safari 无 | `[文档]` |
| ~~MediaPipe LLM~~ | —— | 维护模式，后继 LiteRT-LM | `[文档]` |

**直接含义**：`cortex-llm` 依赖 `@xenova/transformers@2.17.2`，落后 v4 两个大版本，于是**拿不到
WebGPU、拿不到 q4、拿不到 v4 的 ModelRegistry 缓存**。这是 P0 级债务，不是优化项。

---

## 11. 供应商契约（限流、重试、错误码）

那次 429 被记成"配额耗尽，需要充值"。**该判断是错的**，而账户余额正好与"它错了"一致。
三个复合缺陷，**没有一个与计费有关**：

| # | 缺陷 | 后果 |
|---|---|---|
| 1 | 重试预算（31 秒睡眠）**短于服务商的 60 秒窗口** | 每次重试都落在拒绝它的同一个窗口内 |
| 2 | **`Retry-After` 从未被读取** | 客户端不知道要等多久，只能猜 |
| 3 | 64 条一批之间**没有客户端节流** | 以最大速率背靠背发请求，直到被限流 |

供应商侧硬事实 `[文档]`：单请求最多 **64** 条（项目 `EMBED_BATCH = 64` 正好在上限）、最多
3072 token（**未检查**，长对话 haystack 上会触发 400）、维度 256/512/1024/2048（用 1024）、
并发过高返回 **`1305`**（"访问量过大"）而非余额错误。

**契约（写入设计，不是建议）**：

1. 重试预算必须**长于**供应商窗口，且以 `Retry-After` 为准；
2. 批次之间必须有客户端节流（`EMBEDDING_BATCH_INTERVAL_MS`）；
3. 错误码必须分流：`1305` → 等待重试；`1113`（余额不足）→ **不重试**，因为重试只会再被拒；
4. 嵌入缓存必须跨 run 复用。曾有一次运行在**题目 0 之前**发出 11,476 次真实请求后撞 `1113`，
   而 preflight 在运行开头是 `ok` —— 钱是被**重复劳动**花掉的。

**为什么这条进设计文档**：它决定了"冷缓存 + 大 limit"这类实验能否被跑出来。把基础设施缺陷
误读成资源限制，会让整轮实测被推迟 —— 这已经发生过一次。

---

## 12. 数值精度与工程纪律

1. 所有向量/矩阵用 `Float64Array` / `ml-matrix`；统计用 Kahan 求和 + Welford 方差，避免 float32
   截断与灾难性抵消。
2. 统计函数必须有**性质测试**：SVD 重构误差、Sinkhorn 收敛到双随机、FSRS 单调性、t 分布对称性。
   **生成器比断言更容易骗人** —— 一个在 `fc.property` 里硬编码 `p = 0.5` 的性质测试，恰好
   绕过了小 `p` 的缺陷（审计 13 处调用：11 处 `p=0.5`、2 处被钳位短路、0 处小 `p`）。
3. 覆盖率四维度（语句/分支/函数/行）≥95%，**无 mock**（真实 SQLite、`pg-mem`、真实 WASM、
   真实小模型）。`v8 ignore` 注解不得用来买覆盖率。
4. CI 真实全绿：`lint && typecheck && test && format`；禁止 `continue-on-error`、`|| true`、
   `skip_tests`。`pnpm check` 必须自带 `build` 前置（曾经的缺陷：干净 clone 上 `typecheck`
   报 `TS2307` 并 exit 2，被陈旧 `dist/` 遮蔽）。
5. 每个新增测试必须能指名**它防的是哪个缺陷**，否则它只是分母。

---

### 12.1 测量宿主是设计的一部分

两条曾记为"本环境无法测量"的缺口，其实是宿主问题：Safari 需要 macOS，Hub 语料需要网络。
两者都可以交给 CI —— 但**不能想当然**：

| 事实 | 证据 |
|---|---|
| 本仓 private 时 Actions 作业**不启动**（3 秒失败、`runner_name` 为空、零 steps）；macOS 作业则长期 `queued` 且无 runner | `ci-smoke` 的一次 echo 作业同样失败；`39761665647` 复现两种形态 `[实测]` |
| 改为 public 后**全部作业都拿到 runner**，Safari 与语料两条链一次跑通 | `39763345040` / `39763828676` 全绿 `[实测]` |
| 改可见性需要 **Administration** 写权限，普通 `repo` 权限的 PAT 会收到 403 | `PATCH /repos/…` 返回 `Resource not accessible by personal access token` `[实测]` |
| 同 org 的 public 仓库运行正常 | `cortex` 同日运行 success `[实测]` |
| 因此阻塞是**可见性/分钟数**，不是"CI 跑不了 Safari" | 三者相互独立地排除了"MACOS runner 不存在"这一解释 |

设计含义：浏览器矩阵与语料获取都写成**可派发的工作流**（`.github/workflows/poc-platform-probes.yml`），
结果提交到 `ci-results` 分支而不是 artifact —— 因为本沙箱只能到达 api.github.com，
一个 git 文件是唯一不需要代理技巧的取回路径。

**一条必须保持的区分**：Playwright 的 WebKit 与 Safari 是两个东西（前者自带网络与存储管线）。
两者都在工作流里跑，结果**分开报告**；把 WebKit 的通过写成"Safari 可用"正是本项目一直在抓的
那类替换。

## 13. 已知债务与实现启动顺序

| 债务 | 严重度 | 影响 |
|---|---|---|
| `cortex-llm` 停在 `@xenova/transformers@2.17.2` | **P0** | 无 WebGPU / q4 / 缓存，端侧质量无法评估 |
| 认知层不在评测路径（价值写入、巩固、双时态、冲突、图） | **P0** | 净贡献未知，任何"护城河"陈述都不成立 |
| `sinkhorn` 未接线 + 收敛检测器曾恒真 | P1 | 接线那一刻才激活 |
| 默认配置下 `consolidate` 的遗忘时钟量纲错误 | **P0** | 会**删除全部记忆**（已定位） |
| `cortex-memory` 不消费 `Storage` | — | 不是缺陷，是设计事实；影响工作量估计 |
| 浏览器/联邦/分诊三块**只有设计与 POC** | — | 见 03 §2 的启动顺序 |
| Safari 已测但**无跨重启**读数 | P1（影响 iOS 承诺的强度） | WebDriver 会话不是持久 profile；实现阶段用真机补 |
| 规则层 leak 的比率仍只有 n=60 | P1 | 需要**同类语料**（职场发言），不是任意语料（§5.4.1） |

实现阶段的启动顺序（每步都有 POC 或单测可依据，不含"边做边定"的决定）：

1. `cortex-storage` 改名 + 五个 subpath + optional peer + **体积守卫**（≤300 KB、不含 native）；
2. `FederatedStorage` 进 core（`[POC-3]` 的 9 条断言直接变单测）；
3. `./opfs` 实现（`[POC-1]` 的 Worker + AHP 形状直接复用）；
4. `cortex-ai` 改名 + transformers.js v4 升级；
5. 分诊规则层进 core（`[POC-4]` 的规则表与 60 条标注变夹具）；读侧组装器进 core
   （`[POC-5]` 的 11 条断言变单测）；
6. 卡片与 HITL —— 三项前置（Safari 探针、规则层 n≥600、真实题库端到端）**均已关闭**，
   可与第 5 步并行；输出侧 O1/O2 随卡片一起实现（§6.4）。
