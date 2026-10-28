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
| 8 | `defer` 默认私有 | `defer` 落共享 | 修补前的表上泄漏 3/12 且不可逆；补满召回后同一语料 0/12（04 §9.9） |
| 9 | 两库物理分离 + 表前缀命名空间 | 单库权限位 | 企业单图假设不成立 `[文档]` |
| 10 | 共享窗口中若有非 shared 行 → **抛错** | 过滤掉继续 | 过滤会让写侧缺陷看起来边界完好 `[POC-5]` |
| 11 | 跨库事务**拒绝** | 假装两阶段提交 | 两个 SQLite 文件没有共同提交点 `[POC-3]` |
| 12 | 重排实现但默认关闭 | 默认开 | 两臂 Δ ±1.33 pp、p=0.7539 `[实测]` |

---

## 1. 架构与包布局

```
packages/
  cortex-core/      契约 + 纯算法（零 I/O），双端            [现状]
                    + FederatedStorage（纯路由）            [待实现]
                    + TriageRules（确定性规则，纯函数）      [现状]
                    + TriageWriter（唯一写入口，见 §5.4.2）    [现状]
                    + KnowledgeCard / ScopePolicy 类型      [待实现]
  cortex-memory/    组合层：把 core 的能力组合成 MemorySystem（不消费 Storage）  [现状]
  cortex-ai/        ← cortex-llm 更名（已完成）
                    "."          远程 provider + 重排 + retry（只需 fetch）   [现状]
                    "./local"    transformers.js 4.x（本地 embedding / rerank，
                                 optional peer @huggingface/transformers）  [现状]
                    "./web"      浏览器内置模型（globalThis.LanguageModel，
                                 零依赖）                                  [现状]
                    + TriageProposer（产出卡片，不落库）+ PiiDetector       [待实现]
  cortex-storage/   ← cortex-node 更名（已完成）
                    "."         空入口（零导出；见 §1.2）
                    "./sqlite"  better-sqlite3（optional peer）   [现状]
                    "./pg"      pg（optional peer）              [现状]
                    "./opfs"    SQLite-WASM + SAH pool            [现状]
                    "./idb"     IndexedDB 降级层（无事务，见 §3.4）[现状]
                    "./analytics" DuckDB-WASM 侧车                [待实现]

  一条结构性事实：**四个后端共用一个 `SqlStorage`**（`src/storage/sql-storage.ts`），
  它只依赖 `SqlSession`（exec/run/all/close）。后端的差异归结为"谁来跑 SQL"：
  `better-sqlite3` 在进程内、`EngineRpcSession` 在 Worker 另一侧、`node:sqlite` 在测试里。

  另一条同形的结构事实：**`cortex-ai` 是一个库、三份依赖画像**。入口守卫按画像逐个走 import
  闭包：`.` 与 `./web` **禁止**触达 `@huggingface/transformers`，而 `./local` 是**正对照**
  （它本来就该触达）。把三者合成一个入口的后果不是"包大了一点"，而是每个只调 HTTP 的服务都被
  迫带上 ONNX runtime 与 90 MB 权重。
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
**optional peerDependencies**：装了才用，没装则只有真正 `import` 那个 subpath 的构建会失败。

**一条必须写清楚的更正**：设计初稿说"没装时给出 `this subpath needs X`"，**这一点做不到**——
ESM 的静态 `import` 在链接期就失败，早于任何我们自己的代码。实际行为是 Node 自己的
`Cannot find package 'better-sqlite3' imported from …/dist/storage/sqlite.js`：它点名了包和文件，
信息量其实够用，而包装它需要把静态 import 换成运行时 `require`，那会同时失去类型与 tree-shaking。
所以这里不承诺自定义错误，只承诺**错误出现在正确的 subpath 上**。

**根入口是空的，这是设计不是占位**：`"."` 只导出 `export {}`。如果根再导出两个 backend，
任何 `import '@agentix-e/cortex-storage'` 都会把 native addon 拉进构建——那正是改名要解决的问题。
因此体积守卫在这里是**入口闭包守卫**：`tools/entry-guard.mjs` 走 import 闭包，禁止可移植入口
触达 native 或 `node:` 内建；它的**对照项**是 `./sqlite`（本来就该触达 `better-sqlite3`），
对照项一旦"干净"就说明走查坏了，根上的绿也就没有意义。

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

### 2.5 FederatedStorage（纯组合，零 I/O）—— **已在 `cortex-core` 落地**

路由规则：表名前缀决定 store（无前缀 = private，**默认必须是安全的那一侧**，否则忘记写前缀
的调用方等于发布）。前缀是路由标记，**不是库内命名空间**：`private/facts` 与 `shared/facts`
在各自库里都叫 `facts`，否则跨库读要知道两套名字。`[POC-3]` 的首版正是踩了这个坑
（`queryAcross` 返回空），修正后 9 条断言全绿。

`queryAcross` 为每行附加 `origin: 'private' | 'shared'`。这个标签不是装饰：私有任务把"我的"
与"团队的"混在一个窗口里，提示词/引用列表必须能说清哪条是哪条。

实现时被**测试逼出来**的两条设计（第 1 版都没有）：

| 问题 | 第 1 版 | 现在 | 为什么 |
|---|---|---|---|
| 行身份 | 用位置 `#0`、`#1` 兜底 | `value.id` 是字符串才有 key，否则 `undefined` | 两个库里同一位置是两行不同事实，位置键会把不相干的事实**静默合并** |
| 合并偏好 | 在合并循环里比较 origin | 先把两库结果按 `private < shared` **排序**，再"先到先得" | 原写法留下一个只有 `queryAcross` 反转输出才走得到的分支：今天不可达，明天一旦可达就是错的 |

**`transactionIn(scope, fn)` 的回调拿到的是路由事务**（表名照旧带前缀），并且**拒绝路由到另一侧的表**：
在 private 事务里写 `shared/facts`，说明调用方对边界的理解与事实不符，该在写入点就说，而不是等成泄漏。

### 2.5.1 ReadSideAssembler（哪一行能被哪个任务读到）—— **已落地**

两条规则，各自独立失败：① 共享任务**只读共享库**（不查询私有库，所以私有行不可能"因为谁忘了过滤"而出现）；
② 共享窗口里每一行都必须**自称 shared**，否则**抛错**而不是过滤掉——过滤会让写侧缺陷看起来边界完好。

守卫在写侧正确时是冗余的，所以干净运行对它是零证据：`[POC-5]` 里用**故障注入**定价
（绕过路由把私有行写进共享库：guard on 抛 `ScopeViolation`，guard off 同一行进窗口），
这条在 `cortex-core` 的测试里原样保留。

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

### 3.4 产品化的浏览器层（实现第 3 步，已落地）

`./opfs` 与 `./idb` 不再是设计稿。这一节记的是**移植过程中被测量逼出来的东西**，因为那些
才是下次改这段代码时会踩到的部分。

#### 3.4.1 一个 `Storage`，三种执行体

| 层 | 位置 | 职责 |
|---|---|---|
| `sql.ts` | 双端同构 | schema（含 `kv_expiry` 索引）、四条语句、`kvQuery`/`selectPage` |
| `sql-storage.ts` | 双端同构 | `SqlStorage implements Storage`：懒过期、事务门、关闭语义 |
| `EngineRpcSession` | 主线程 | 把 `SqlSession` 的四条语句变成 Worker 往返 |
| `opfs-worker.ts` | Worker | 装 SAH 池、开库、把 `SqlEngine` 接到协议处理器 |
| `idb.ts` | 主线程 | 降级层：同一批 helper，换成 IndexedDB |

**为什么只写一份 `Storage`**：浏览器与服务端跑的是同一句 SQL、同一张表。写两遍就给了两次
"对懒过期、对事务回滚、对 tag 过滤与分页的先后顺序产生分歧"的机会，而分歧不可见 —— 各有一份
测试，各自都过。`src/__tests__/parity.test.ts` 用 200 条生成操作跑三条臂（`better-sqlite3` /
`node:sqlite` 直连 / `node:sqlite` 过 RPC），逐条比对返回值与最终表状态。**这个测试被验证过
会红**：在通道臂里丢掉一行，它报 `operation 24 (query) diverged at arm channel`。

#### 3.4.2 移植时抓到的七个缺陷

| # | 缺陷 | 为什么之前看不见 | 现在 |
|---|---|---|---|
| 1 | `SqliteStorage.transaction` **从未发过 `BEGIN`** | 所有事务测试都成功；失败路径只断言"错误传播" | 真 `BEGIN`/`COMMIT`/`ROLLBACK`；拒绝嵌套；拒绝事务外的写；排队串行化；回滚也失败时抛 `AggregateError` |
| 2 | 前缀过滤用 `LIKE`：`_`/`%` 当通配符、ASCII 大小写折叠 | 只有 key 里恰好含这些字符或大小写不同才暴露 | `substr(key, 1, ?) = ?`，两个引擎都断言 |
| 3 | `(table_name, expires_at)` **无索引**，而清理在每次读写都跑 | 单条读写看不出；批量写才显形（2,000 行 **161 行/秒**） | 加 `kv_expiry`；测试断言 `EXPLAIN QUERY PLAN` 用该索引（不是断言耗时） |
| 4 | 关闭 storage **不终止 Worker**，池仍装着 → 同页第二次打开装不上第二个池，**静默降级到 IDB** | 只有"打开-关闭-再打开"才触发 | 会话拥有 endpoint 生命周期，`onClose` 里 `terminate()` |
| 5 | Worker 模块加载失败时**谁都不回消息** → 页面永久挂起 | 在浏览器里表现为"卡住"，无控制台线索 | 就绪前排队、失败逐个回错误码、`error` 事件 abort、启动与超时赛跑 |
| 6 | `?sqlite=` 被当作 URL **base**，相对路径抛 `Invalid base URL` | 只在用相对路径时炸，且报错位置在 `locateFile` | 在 Worker 里先按 `location.href` 解析成绝对 URL |
| 7 | 浏览器套件在 OPFS 失败时**把 IDB 的结果贴上 opfs 标签** | 套件自己的标签逻辑 | tier 成为运行该矩阵的**前置条件**，不匹配就单列一条失败 |

第 3 条尤其值得记：**它是一个"只在批量时才出现"的性能缺陷，而正确性测试永远看不见它。**

#### 3.4.3 实测读数（Chromium 145，2,000 行，发货代码）

| 量 | 值（三次运行） | 说明 |
|---|---|---|
| VFS / 引擎 | `opfs-sahpool` / sqlite-wasm 3.54.1 | `journal_mode = delete`（实测读出，非设定） |
| 逐条 `put` | 9.5–11.2 s（**178–211 行/秒**，4.7–5.6 ms/笔） | 每笔一次完整提交 |
| 同一批走 `transaction` | **157–175 ms（11,442–12,763 行/秒）** | 差 **54–72×** |
| 全表读回 | 15.7–22.8 ms | |
| 跨浏览器重启摘要 | `4000247205` = `4000247205` | 两次启动，同一 profile，四次运行都相同 |

> **两个数都不是"引擎性能"，是提交次数**。原型（`[POC-1]`）写 10,000 行用单事务，得到 56,850 行/秒；
> 产品的逐条 `put` 是每笔一次提交，只有三位数。**两者测的不是同一件事**，把它们并排放进一张表
> 会得到一条假结论 —— 这正是本报告反复在防的那类错误。

**一个被否掉的"优化"**：先怀疑是 `journal_mode` 不是 WAL，于是加了 `PRAGMA journal_mode=WAL`
—— **吞吐没变**（201 行/秒）；再加 `synchronous=NORMAL` 也只到 249。所以瓶颈不是同步策略，
而是该 VFS 本来就走回滚日志、每笔都必须完整提交。代码因此**不设 pragma**，改为把
`journal_mode` 写进 `describe()` 的返回值，让那句"为什么单条写这么慢"在读数里自解释。

**结论写进 API 契约**：批量写必须走事务。这不是调优建议 —— 54–72 倍是数量级差异。

#### 3.4.4 降级层的诚实边界

| 项 | `./opfs` | `./idb` |
|---|---|---|
| 事务 | 真事务 | **拒绝**（`TransactionUnsupportedError`），因为 IDB 事务跨越 `await` 会提前自动提交 |
| 查询 | SQL（tag 在 JS 过滤后分页） | 同一套 `selectPage`，索引 `by_table` 取表、`by_expiry` 取过期行 |
| 前缀语义 | `substr` 字面比较 | `startsWith` 字面比较（刻意一致） |
| 何时用 | 默认 | OPFS 不可用（隐私模式、旧浏览器、配额） |

**`openBrowserStorage` 的契约**：返回 `{ storage, tier, engine, refused }` —— 落到哪一层、
为什么没落到更想要的那层，都要能被调用方拿去展示。**配置错误不算不可用**：请求 `opfs` 却没给
`sqliteModuleUrl` 时立刻 `TypeError`，**不**降级 —— 否则每个开发环境都在跑生产不会跑的那条路。

#### 3.4.5 只在那台机器上才能测的部分，怎么测的

三个文件（`opfs.ts` / `opfs-worker.ts` / `idb.ts`）需要 `Worker`、OPFS、IndexedDB，Node 里都没有，
jsdom 式的 shim 只会断言 shim。所以它们**不计入 Node 覆盖率**，而由
`packages/cortex-storage/test/browser/probe.mjs` 覆盖：把**构建产物**加载进真 Chromium，
**同一个 profile 启动两次**，断言 **24 条命名检查**（API 矩阵 ×2 层、降级路径、配置错误、
关闭后拒绝使用、跨重启摘要）。

判定标准只有一条：**这条检查在真实平台上跑过，且能失败**。第 7 条缺陷正是这套检查第一次跑红
时抓到的 —— 它当时"通过"了 23 条，而标签是错的。

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

### 4.4 升级不动数学，动的是默认值（实现第 4 步，已实测）

把 `@xenova/transformers` 2.17.2 换成 `@huggingface/transformers` 4.3.1，是第一件必须量化的事：
**已存的向量还能不能用**。

`test/parity/run.mjs` 在**同一批权重、同一批 15 条文本**上比对三条臂（`Xenova/all-MiniLM-L6-v2`，
384 维，权重经 `hf-mirror.com` 取得）：

| 对比 | min cos | 中位 | < 0.999 的条数 |
|---|---|---|---|
| **发货适配器（fp32） vs v2（`quantized: false`）** | **1.000000** | 1.000000 | **0 / 15** |
| 发货适配器（fp32） vs v2 **默认**（量化） | 0.988242 | 0.990055 | **15 / 15** |

**读法**：库的升级本身是**逐位等价**的（1.000000，不是"约等于"）。真正会动的是**默认值**——
v2 默认量化权重，v4 默认 fp32。一个"照默认升级"的调用方会得到维度正确、单位长度、**与已存向量
不可比**的结果，而任何下游指标都只会表现为"检索变差了"。

因此本设计把三件事**显式钉住**，而不是依赖默认值：

| 钉住的项 | 值 | 不钉会发生什么 |
|---|---|---|
| `dtype` | `fp32` | 见上表；跨版本不可比 |
| `pooling` | `mean` | 未池化时输出 `[n, seq, dim]`，下游按 n 行读会错位 |
| `normalize` | `true` | 余弦退化成点积，长度进入排序 |

**推论（产品层）**：v2 时代产生的任何向量**必须重嵌**，因为它们是量化权重下的结果。这不是"建议
重建索引"，是**同一个模型名、不同权重**——0.988 的余弦意味着检索排序会真的改变。

### 4.4.1 同一轮里抓到的更严重的一个：重排曾经是空转

`text-classification` 管线会对模型的 logits 做**按标签的 softmax**。重排用的交叉编码器只有
**一个标签**，于是 softmax 恒等于 1.0 —— 所有候选并列，重排"成功"且什么都不做。

| 输入（query = "what is the capital of France"） | 原始 logit | 管线给的 score |
|---|---|---|
| "Paris is the capital of France." | **1.954** | 1.0 |
| "Berlin is in Germany." | −4.028 | 1.0 |
| "The weather is nice today." | −5.625 | 1.0 |

**为什么之前没被发现**：v2 的管线把结果**按输入嵌套**返回（`[[{...}], [{...}]]`），我们的适配器
长度检查通过、但 `entry.score` 是 `undefined`，于是抛错并回退到下一 provider —— 一个**响亮的失败**。
v4 改成扁平数组，形状正好对上契约，失败就变成了**沉默**。**同一个缺陷，换版本后从可诊断变成不可
诊断。**

**修法**：不经过管线，直接 `AutoTokenizer` + `AutoModelForSequenceClassification` 读原始 logits。
`CrossEncoderReranker` 仍然负责"要不要 sigmoid"这一层语义。验收不是"跑通"，而是**分数互不相同且
顺序正确**：1.954 > −4.028 > −5.625（相关 > 同主题干扰 > 无关）。

---

### 4.5 实现（第 14 步）：选哪个模型是一份记录，不是一条分支

三个问题被问到了一起：**0.5B 是哪个模型、为什么不是 DeepSeek 或智谱、该不该有一个配置项在"本地
零网络"和"API 大模型"之间切换并比较**。前两个的答案决定了第三个必须做成什么样。

#### 0.5B 是什么，为什么先是它

`onnx-community/Qwen2.5-0.5B-Instruct`，q4 ONNX，经 `@huggingface/transformers`（transformers.js）
在 CPU 上跑，约 400 MB，本机每张卡 **6–10 s**。

它是**能在这台机器上把 60 条语料跑完的最小东西**，而第 9 步要测的是**闸**，不是模型质量：那一轮
最重要的读数是"v1 提示词里的例句被原样返回 44/60 次，四道闸把它们全部按 `ungrounded` 拒掉"。
一个 70 B 的模型不会复制例句，也就测不出闸是否承重。**选择一个小模型是测量设计，不是产品决策。**

#### 为什么不是 DeepSeek，为什么不是智谱

| 候选 | 能不能用 | 为什么这一轮没用 |
|---|---|---|
| **DeepSeek**（生成） | **能，且已经实现**：`OpenAICompatibleLLM` 走 `/chat/completions`，`--llm remote` 就是它 | **没有 key**。本机环境里没有 `CORTEX_LLM_API_KEY`，而仓库从不存 key（政策，不是疏忽）。所以 remote 这一行是**未测**，不是"不支持" |
| **智谱 embedding-3**（嵌入） | 协议兼容（`OpenAIEmbedding`），但**类型不对** | 提议要**生成**：把一句话拆成原子、给出遮罩跨度。嵌入做不到这件事。cortex 里嵌入的位置是检索/重排，由本地 cross-encoder 重排器覆盖；更根本的是，把用户原句发去嵌入 API 与"本地零网络"直接冲突（**注意：此处初稿曾以"429 配额已耗尽"为理由，那是个被 §5.3 审计推翻的说法——429 是并发上限，见 `cortex/docs/AUDIT-ZHIPU-429-ROOT-CAUSE.md`。理由只需要"零网络"这一条，而它本来就已经足够**） |

**所以"用不用大模型"不是一个是非题，是一个配置。** 而配置一旦存在，就必须能被审计——否则两个
读数会在同一张表里假装可比。

#### 配置的形状：两个具名 backend，没有第三个

```ts
type LlmProfile =
  | { backend: 'local';  model: string; dtype: string; weightHost: string; inferenceNetwork: 'none' }
  | { backend: 'remote'; model: string; baseUrl: string;                    inferenceNetwork: 'required' };
```

四条设计决定，每条对应一种已经见过的失效：

| 决定 | 没有它会怎样 |
|---|---|
| **没有 `auto`，也没有回退**：`remote` 缺 key 是**错误** | 静默降级到本地，会让一份记录声称 `deepseek-chat`，而实际每个原子都出自 0.5B，且**没有任何数据能看出替换发生过**。这与第 9 步"失败不降级为空提议"、第 10 步"读侧抛 `ScopeViolation` 而不是过滤"是同一条规则 |
| **一次报全部缺失变量** | 三个 `if` 逐个报，装环境变成猜谜：修一个、重跑、发现下一个。第一版演示正是这么写的 |
| **profile 里没有 key 这个字段**，key 由 `readApiKey(env)` 单独取 | 脱敏靠打印时记得剥掉，就是一次 `console.log` 的距离。**结构上没有**，才是真的没有 |
| **`http://` 只允许 loopback** | `http://api.deepseek.com` 是个合理的笔误，后果是 bearer token 明文上线：静默、远端、不可撤回 |

`remote` 的模型名**没有默认值**：把某个厂商的名字写进默认值，是一种没人做过的锁定。

#### 记录进入读数的三处

| 位置 | 内容 | 为什么 |
|---|---|---|
| 演示/工具的 stdout | `profile: local … dtype=q4 inference-network=none` | 一份 transcript 如果不写配置，两段长得一样的输出就无法区分 |
| `cards.json`（A3 的输入） | `profile` + `promptVersion` | 这两个字段是 A3 的**处理**本身。第一版 `prepare` 只记了 profile，于是 v2 与 v3 两个文件无法区分——**这个缺陷是在写文档时被自己的工具抓到的** |
| `KnowledgeCard.proposal.provider` | `local` / `remote` / `null` | 卡片是配置相遇的地方，也是唯一的审计面。"哪个配置产生了这条已发布的事实"必须能从导出里回答 |

#### 实测一：本地推理真的不出网

`packages/cortex-ai/test/profile/network.mjs` 在**导入任何东西之前**接管 `globalThis.fetch`，把每个
请求归到 `load` 或 `infer` 阶段：

| 阶段 | 调用数 | 耗时 |
|---|---|---|
| load（加载权重，已缓存） | **0** | 6.9 s |
| infer（一次完整 `propose`） | **0** | 9.8 s |

**这比一句声明值钱**：`@huggingface/transformers` 自带 `fetch`（冷启动要下权重），所以"依赖里没有
HTTP 客户端"本来就不成立；成立的、也是产品真正承诺的，是**推理阶段零请求**——权重已在磁盘上之后，
用户打的那句话不可能离开这台机器。

#### 实测二：离线入口里其实藏着 HTTP 客户端（两处）

给 `tools/entry-guard.mjs` 加上**文件级禁令**（"这个入口不得触达 `retry.ts` / HTTP 适配器"）之后，
它在真实树上失败了，而且失败了两次：

| # | 位置 | 症状 |
|---|---|---|
| 1 | `parseJson` 定义在 `llm/openai-compatible.ts`，而 `./local` 与 `./web` 都从那里 import | 两个离线入口把 `retryableFetch` 一并拖进闭包。纯函数放进了重文件，**每个 import 它的人都变重，而且什么都不报错** |
| 2 | 修掉第 1 处后守卫**再次失败**，点名 `src/retry.ts` | `CrossEncoderReranker` 与 `OpenAICompatibleReranker` 同住 `rerank/rerank.ts`，而 `./local` 再导出前者 |

两处都修了（`src/json.ts`；`src/rerank/cross-encoder.ts`），旧名字仍从原模块再导出，调用方无感。
**运行期的请求数在两处都是 0**——所以这个缺陷永远不会表现为一次泄漏，只会表现为一个装着用不上的
客户端的包。**依赖就是包，包就是承诺。**

#### 实测三：剂量是容量问题，不是提示词问题

第 13 步预检发现 20 张卡里只有 1 张真被拆开，于是 A3 没有开跑。这一轮做一个**单变量**实验：同一个
checkpoint、同一份语料、同一套闸，只改提示词里"怎么切分"那一条（v2 → v3，v3 把"通常不止一条"
换成"第二个从句有自己的主语或动词就拆"，并要求先数从句）。

| 项 | v2 | **v3** |
|---|---|---|
| 拆成 ≥2 条（处理） | **1 / 20（5.0%）** | **1 / 20（5.0%）** |
| 单条、有改写/裁剪 | 5 | 4 |
| 单条、与原句相同 | 14 | 15 |
| 覆盖度（原子字符数 / 原句字符数，均值） | 0.920 | 0.932 |
| 覆盖度最小值 | **0.416** | **0.296** |

**净零，但不是零**：三处移动方向相反——

| 卡 | v2 | v3 |
|---|---|---|
| `g00` | 1 条 | **2 条**（"…using Python" + "So I'm interested in applying…"） |
| `g04` | **3 条** | **1 条**（丢掉了后两条） |
| `g18` | 裁掉了 "By the way, speaking of TV shows," | 保留了它 |

所以 v3 买到一次拆分、丢掉一次拆分，同时**引入了"返回原句的真子集"这个新失效**：原子仍然逐字接地
（闸不会拦，也不该拦），但提议**没覆盖整句**。这正是"闸管风险、不管有用性"的又一处证据。

**可复现性**：v2 用改动前的提示词重跑一遍，20 张卡的原子与第一次**逐字节相同**——greedy 解码在该
checkpoint 上是可复现的，因此 v2 与 v3 的差别只能来自提示词。

**v3 随后在六十条语料上被否证并回退**：同一 checkpoint 上，可用提议从 **45/60 降到 41/60**（配对：
只在 v2 成功 5 条、只在 v3 成功 1 条，精确 McNemar **p = 0.22**），剂量仍 5.0%。没有收益、总量更低、
规则更长——回退，数字留在 `proposer.ts` 里那条规则的上方。失败的那次读数作为
`live-result-v3-local.json` 留在仓库，删掉它会让判断无法追溯。

**结论**：0.5B 不切分是**容量**，不是措辞。要拿到剂量，就得换更大的模型——本地上 1.5B q4 需要
1,705 MB 权重，这台机器从镜像取到 **0.28 MB/s**，35 分钟拿到 579 MB 后停手；接 API 只需要三个环境
变量。**这就是 remote 这一档存在的理由，而且现在它有一条命令的入口。**

#### 四种配置的现状

| 配置 | 模型 | 推理出网 | A3 剂量 | 60 条可用提议 | 每句耗时 | 状态 |
|---|---|---|---|---|---|---|
| `local` 0.5B q4 | `Qwen2.5-0.5B-Instruct` | **无（实测 0 次）** | 5.0% | 45/60 | 5.88 s | ✅ |
| `local` 1.5B q4 | `Qwen2.5-1.5B-Instruct` | 无 | — | — | — | ⛔ 权重 1.5 GB 未取全（0.28 MB/s） |
| `remote` | `deepseek-chat` | **必需** | **75.0%** | **52/60** | **0.91 s** | ✅ |
| `remote` 嵌入 | 智谱 `embedding-3` | 必需 | —（嵌入不拆句） | — | 1.49 s / 3 句 | ✅ |

**未测的一行不写 0，写"未测"**：把缺失当成零，是这份文档里反复出现的那个错误。第 14 步的 remote 行
就是这样写的；第 15 步把它填上时，同一个 20 张卡的夹具从 5.0% 变成 **75.0%**——**剂量门第一次通过**，
A3 从"排期上做不了"变成"只差一个人点 40 次"。

远端只能在 CI 上测：key 是 org 级 secret，本机没有、仓库永远不会有。这不是绕路，而是配置设计的直接
结果——`resolveLlmProfile` 只从环境读，而环境在 runner 上。**同一份仪器、同一套闸、同一版提示词，
唯一变化的变量是 backend**，这正是第 14 步把配置做成记录所换来的东西。

#### 一次"没被执行过的仪器"的第一次执行

`measure-models.yml` 第一次 dispatch 就失败了两步，原因在脚本而不是工作流：两步把**绝对路径**传给
`--out`，而脚本写的是 `join(HERE, out)`——`join('/a','/b/c')` 是 `'/a/b/c'`，绝对段被追加而不是替换，
文件写进了包内一个不存在的目录。同一份 dispatch 里 A3 dosage 那一步成功，因为它直接用了
`dirname(config.out)`。修法是 `resolve`。

这件事值得记在架构文档里，因为它是本仓反复出现的同一类：**每个组件单独看都对，合起来才错**。而且它
只在仪器第一次真正运行时暴露——此前这条路径只有"读代码"这一种验证方式，而读代码看不出 `join` 与
`resolve` 的差别，除非你正好在想绝对路径。

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
| 4 | `health` | private | 诊断、用药、就诊、饮食限制、运动（含步行）、热量与摄入、体重、生理测量 |
| 5 | `family` | private | 家人与伴侣、纪念日 |
| 6 | `career-status` | private | 晋升、薪酬、离职、解雇、面试 |
| 7 | `third-party` | private | 同事/上级/朋友/房东等人 |
| 8 | `org-knowledge` | **shared** | `our team`、`the project`、`the client`、roadmap、sprint、onboarding、deliverable |

**私有一律先跑**，所以"看起来是组织知识、但提到了钱"的句子留在私有。这个顺序就是 fail-closed
的全部论证，`[POC-4]` 测的就是它是否成立。

#### 5.3.1 顺序是论证，那就不能只是数组下标（实现第 5 步）

这张表在 POC 里是数组，**顺序只存在于阅读者的眼睛里**。有人把 `org-knowledge` 移到第一行，整个
fail-closed 论证就反了，而任何一条单句测试都不会红 —— 只有同时命中两条规则的句子会变，而那些
句子正是最不常被抽到的。所以产品代码在**导入时**校验表本身：

| 校验 | 不校验的后果 |
|---|---|
| 所有 private 规则在 shared 之前 | 一条 shared 规则上移 = 反向 fail-closed，静默 |
| id 唯一 | 有争议的判决无法归因到唯一一条规则 |
| 没有 `g` / `y` 标志 | `test()` 在带状态的正则上推进 `lastIndex`，同一句话第二遍会答"不匹配" |
| 每条规则都有政策句 | 被质疑时没有可引用的一句话 |

`assertRuleTable()` 在模块加载时对内置表跑一遍，所以**改坏的表根本到不了调用点**。四条各有单独的
反例测试（注入一张坏表看它抛什么），而不是"文档里说了要按顺序"。

### 5.4 实测，以及它改变了什么设计

`[POC-4]`：60 条真实用户语句（LongMemEval-S），**先**按公开政策人工标注 12 private / 8 shared /
40 defer，**再**写规则（避免循环）。

| 指标 | 值 | 读法 |
|---|---|---|
| **false-share** | **0 / 12**，Wilson 95% 上界 **24.2%** | 安全方向；但 12 个样本给不出"低于 1%"的承诺 |
| false-private | 4 / 8 | 代价是用户多点一次，可恢复 |
| **coverage** | **31.7%** | 规则只决定不到三分之一 |
| 三次一致率 | 90.0% | 上下文，不是目标 |
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
| coverage | **29.2%**（95% CI 26.9–31.6） | 与 60 条上的 31.7% 同量级 |
| 按领域 | finance 90.8%、mental_health 37.7%、housing 29.8%、employment 19.2%、health 11.3%（修补前） | `money` 规则在财务事实上一击即中；`health` 最弱 |
| leak | **NOT MEASURED** | 发布规则 `org-knowledge` **0/1,467 命中** —— 结构性零 |

**这一轮抓到的真实缺陷**：健康规则对**生理测量**完全沉默 —— "blood pressure 138 over 86"、
"liver function test showed ALT 28 and AST 22"、"I average 7.5 hours of sleep"。它们不泄漏
（`defer` 落私有），代价是用户多卡片，所以此前的 false-share 审计看不见它们。补上 vitals 词族后
coverage 24.9% → **28.4%**（**那一轮的表**），而 p04 三项指标一位未动 —— 修补由政策辩护，不由语料调参。

**这一轮否掉的诱惑**：不要把 0/1,467 写成"上界 0.26%"。被测机制一次没触发，零就是空白。
因此 `p06` 在报告 leak 之前**先报发布规则的命中次数**，为 0 就把 leak 打成 `NOT MEASURED`。

### 5.4.2 写侧：一处决定，一个字段（实现第 5 步）

在实现第 5 步之前，"这条事实进哪个库"是 `[POC-5]` 原型和下一个调用者之间的默契。现在它是一函数，
边界成为 (`TriageWriter`, `ReadSideAssembler`) 这一对的属性，而不是每个调用点的自觉。

三条决定，每条都有对应测试：

| # | 决定 | 不这么做的后果 |
|---|---|---|
| 1 | **`visibility` 永不写 `defer`**：存进去的是 `private`，规则层的话记在独立的 `triage` 字段 | 把 `defer` 写进被强制执行的那个字段，所有 `visibility === 'private'` 的过滤都会静默漏掉延迟行，而且读侧守卫报出的会是**错误的缺陷** |
| 2 | **分诊失败 = 私有行**，并把失败原因记在 `triage.failure` | 让异常逃逸，等于把"这条事实该怎么办"推给每个调用点；而安全的答案要在所有地方重写一遍 |
| 3 | **晋升先写共享、再删私有** | 两个库无法原子写（`transactionIn` 明确拒绝跨作用域）。删失败时行在两个库里都有，读侧偏好私有副本 —— **看起来没生效**，可见且可重试；反过来则是行在两处都没有，静默丢数据 |

**`triage` 是不可变的**：一条被晋升的事实保留"规则层当时说的是 `defer`"，另加 `confirmedAt`。
如果晋升后把 `triage` 改写成"某条规则判了 shared"，审计链就断了 —— 而审计链是规则层能站得住的
唯一理由。

### 5.4.3 实现（第 17 步）：规则的否决可以被推翻，但它必须留下记录

第 6 步发现过一个空白：一条被规则判为 privé 的句子**不会变成卡片**，于是"要不要分享"这个问题的
答案永远由规则给出，所有者没有发言权。`g42`（一句健康相关的句子）就这样在私有库里躺了十几轮。
本产品的每一条边界都有门，唯独这一条没有。

门不等于洞。三件事让它成为门，每一件都是决定而不是默认：

| 决定 | 没有它会怎样 |
|---|---|
| **要一个令牌，不是一个布尔值** | `true` 是一个接线时顺手就能传的值；`"rule-override"` 必须被**打出来**。令牌还会写进记录，于是审计能看见"当时确认了什么"，而不是去猜 |
| **记录写在移动之前** | 进程在两步之间死掉时，剩下的是一条"未完成"的记录和一条仍在私有库里的行——**失败是可见的**。反过来则是一条已经公开、却没有说明为什么可以公开的行 |
| **记录在自己的表里、在私有库中** | 释放不是接受。读卡片表的人不该在那里找到它；共享任务也不该读出"这个人被推翻过哪条规则" |

#### 它拒绝什么，以及为什么先拒绝再验令牌

三种拒绝，各自一段完整的话，顺序不能换：

1. **`defer` 行**：没有规则触发，就没有什么可推翻的。defer 是**问题**，卡片队列才是回答它的地方。
2. **没有规则 id 或没有政策句的行**：注入的表可以产出这种形状。没有政策句的警告是一句没说任何
   东西的警告，而"私有但无规则"是分类器缺陷，不是决定。
3. **不存在的行**——包括每一条凭证。`retention:'never'` 在入口就执行了，一条能把它复活的释放
   路径会把这个唯一绝对的策略撤销掉。

**先拒绝，再验令牌**：对一个本来就不能释放的行说"令牌错了"，会把调用者送去修错的东西。

#### 两条比成功路径更重要的测试

- **未完成**：让共享库的写入失败，断言留下的是 `completedAt: null` 的记录 + 仍在私有库的行。
  这条分支走不到成功路径，所以必须由故障注入来覆盖。
- **摘要**：`digestAlgorithm` 随值一起存，运行时没有 `crypto.subtle` 就**拒绝**而不是降级——一条
  标着 `sha-256` 却存着别的东西的记录，比没有记录更糟，因为标签正是审计者信的那部分。

#### 幂等

第二次调用返回同一条记录，而不是报告第二次推翻：网络错误后的重试不是第二个决定。`promote` 与
`release` 共用一个 `cross()`——它们的差别只有一个字段（`confirmedAt` / `releasedAt`），而"先写共享、
再删私有"这个顺序**不能有第二份实现**，因为两份精心选择的顺序里，总有一份会先写错。

`releasedAt` 与 `confirmedAt` 分开，理由同样是审计：确认回答的是规则层问过的问题，推翻回答的是
规则层拒绝问的问题。一个分不清两者的读者，会在每条被释放的行上找不到那张卡。

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

### 5.5.1 实现（第 6 步）：五条规则各自被什么守住

`CardQueue` 落进 `cortex-core`。**实现的是设计的一个子集，而少掉的两个字段要说明理由**：

| 设计字段 | 状态 | 理由 |
|---|---|---|
| `id` / `text` / `state` / `reason` / `rule` / `origin` / `createdAt` / `updatedAt` / `decidedAt` / `decayAt` | ✅ 已实现 | `reason` 与 `rule` 来自规则层的 `triage` 记录，**不重新生成** |
| `redactions` | 🔶 移位实现（第 9 步） | 它属于**提议**而不是卡片顶层：模型给出 `{start,end,kind}` 跨度，经越界/空/重叠/类别四道校验后保留，`droppedRedactions` 记录被丢的个数。见 §5.5.2 |
| `confidence` | ❌ 仍然不实现 | 第 9 步之后理由更强：模型自评没有校准来源，而提议层能给的、可复核的量是**每道闸拒了几个**，那个数字重跑一遍还是同一个 |
| `scope: 'private' \| 'shared' \| 'both'` | ❌ 收窄 | 卡片只问一件事：**这一条能不能公开**。`both` 在没有任何"家庭/团队"作用域之前没有含义 |

状态机（`dismissed` 是唯一的终态）：

```
proposed ──accept──▶ accepted ──expire──▶ stale ──refresh──▶ accepted
    │                    ▲
    ├──edit──────────────┘（改后仍可发布时）
    └──dismiss──▶ dismissed（不可复活）
```

五条规则各自被什么守住，以及对应的测试：

| 规则 | 实现方式 | 测试 |
|---|---|---|
| 凭证永不建卡 | 它根本不是"不建卡"而是**不落库**：`retention: 'never'` 让 `admit` 直接返回 `stored: false` | 两个库、两张表全文搜索都不含那串字符 |
| `dismissed` 终态 | `accept`/`edit` 遇到 `dismissed` 抛错 | 两条断言 + 幂等的 `dismiss` |
| 卡片可导出 | `toMarkdown()` / `toJSON()`，**含已拒绝的卡**（导出是审计面） | 摘要按生命周期排序、管道符转义、两次导出逐字节相同 |
| `stale` 不参与回答 | 过期时同时改卡片状态与**事实上的 `stale` 标记**，读侧过滤 | 过期后两个窗口都读不到；`refresh` 后回来 |
| 编辑即重新判定 | `edit()` 走 `revise()`：**只在可发布时落库** | 粘贴卡号/邮箱 → 拒绝且那串字符不在任何表里 |

**这一轮抓到的最重的缺陷，是文档与代码互相矛盾**：`credential` 的政策句写着"never stored, not even
as a card"，而写侧一直把它**私密存下来**。两份产物里，写侧是弱的那一份，却也是被执行的那一份。
修法不是改政策句（那正是用户被告知的东西），而是加 `retention: 'never'`：命中它的句子被分类、
被报告、**不被写**。60 条语料里没有凭证类句子，因此**三项读数一位未动**（19/60、0/12、4/8）。

**编辑路径值得单独说**：一次编辑是**一句新话**，所以它要重新判定。用户把"我这周做了三件事"改成
"我这周做了三件事，顺便我的卡号是 4111…"，若因为"他已经确认了这张卡"而发布，等于把"同意一个
摘要"当成"同意一个秘密"。拒绝时**新文本也不留**：导出读的是卡片，一段被拒绝的编辑里仍然有一个秘密。
为此 `revise()` 与 `admit()` 故意不对称——前者只在可发布时落库，后者永远落库（除非 `retention`）。

### 5.5.2 实现（第 9 步）：提议层 —— 模型可以提议，不能决定

卡片此前显示的就是用户的原句。这是正确的，也几乎无用：**一段话就是一张卡**，于是"要不要分享"
变成对一段话的全有或全无。提议层让模型把它拆成同事能据以行动的**原子**，并标出原子内部应当
在预览里遮住的片段。两件事都不是决定：**它不返回 scope、不写库、不标记任何东西为已发布。**

#### 四道闸，每道对应一个已测量的失效

| 闸 | 规则 | 没有它会怎样 |
|---|---|---|
| **G1 内容接地**（第 21 步替换了"逐字接地"） | 原子可以删、可以改序、可以用词的变形，但**不能引入**原句没有的数字、人名、实词或否定 | 卡片会提供一个用户从没说过、却可以一键发布的句子。原先要求"逐字连续片段"，见 §5.5.5：那条规则让提炼在数学上不可能 |
| **G2 规则复判** | 每个存活的原子**重新分类**；被判 `private` 或 `retention:'never'` 的一律丢弃 | 把一个私密句拆成更小的私密句再逐条端上来 —— 那是**洗白**，不是抽取 |
| **G3 凭证不留文本** | 被丢弃的原子只记**规则 id 与政策句**，文本不进入提议 | 提议存在卡片上、卡片会被导出 —— 一段"为审计而保留"的密码仍然是一段密码 |
| **G4 跨度校验** | `{start,end}` 必须在范围内、非空、类别属于闭集、且两两不重叠；被丢的个数计入 `droppedRedactions` | 一个遮不住任何东西的遮罩，比没有遮罩更糟：它宣称"这里被藏住了" |

**G1 顺带关掉了提示词注入**，而且不需要为它专门写一个分类器：指令要求模型输出的那句话**不是**
用户原话的连续片段，于是和幻觉走同一道闸。它的**诚实边界**也一并写下：指令若要求模型**复述**
原句里的某个短语，产出的东西就是"用户确实说过的话"，此时只剩规则与用户那一次点击。两种情形
都有测试，后一种的测试名字就叫"keeps a copied phrase, and leaves it to the rules and the person"。

#### 为什么没有 `confidence`

设计要求一个 `confidence` 字段用于排序。**没有实现，而且第 9 步之后理由更强了**：模型对自身输出的
自评没有任何东西校准，它会是"恒为 0.6、写进文档、却没人能复核"的字段。可复核的量是**每道闸拒了
几个**（`withheld`）—— 同一个输入重跑一遍，这个数字不变，审查者能自己复算。03 §4.2 把前一种叫
**结构性零**。

#### 失败不是同意

`propose()` 返回判别联合：

```ts
type ProposalResult =
  | { ok: true;  proposal: TriageProposal }
  | { ok: false; failure: { reason: 'provider-error' | 'malformed' | 'empty' | 'all-withheld'; detail: string } };
```

危险的做法是 catch 住错误、返回一个空的 `facts: []`；调用方读 `facts.length` 会把它当成
"没什么可分享的"，这正好是本系统要防的方向。失败时卡片保留**用户自己的句子**，与提议层存在之前
完全一样。

#### 发布路径不变，这是有意的

点击某条原子发布时走的是 `CardQueue.edit()`，因此**规则在点击那一刻再判一次**。理由不是防御性
编程：表可能在提议与点击之间被改过，而"被上个月的表认可过"不是"这个月可以发布"的同意。测试用
两个队列共享同一对存储来复现这件事（上月写侧 + 本轮写侧），断言拒绝理由是本月的规则 id。

`attach()` 另外做了三件拒绝：**已决卡片不可再挂提议**（已发布事实的内容是历史）、**空提议不接受**、
**未经接地的提议不接受**（这一条覆盖"有人手工拼一个提议以跳过模型"的未来调用方）。

#### 真实模型读数（0.5B 端侧，60 条标注句）

`packages/cortex-ai/test/proposer/run.mjs`，权重经镜像取得，`greedy` 解码，记录在
`test/proposer/live-result.json`。

| 项 | v1 提示词 | **v2 提示词** |
|---|---|---|
| 产出可用提议 | **4 / 60** | **45 / 60** |
| 回复无法解析 | 12 | **0** |
| 全部被拒 | 44 | 15 |
| 保留原子 | 4 | **48**（自 51 个候选） |
| 拒绝分布 | `ungrounded` 57、`rule:health` 1 | `rule:health` 10、`rule:money` 4、`ungrounded` 3、`too-short` 2 |
| 每句耗时 | 4.68 s | 5.88 s |

**两版之间只改了一件事**：v1 在提示词里放了一个**例句**（"I moved to Berlin in March and I work at
Acme" 是两条）和一个句子形态的模板占位符；0.5B 模型把**例句原样返回了 44/60 次**。v2 里没有任何
句子形态的可复制物（占位符是三个点），同一个模型从 4 条跳到 45 条。**这不是提示词工程的手感，
是一次单变量测量**：闸没变、模型没变、语料没变。

分层读数（v2）：`defer` 40 条 → **37 条**出提议、40 个原子；`shared` 8 条 → 6 条；`private` 12 条
→ **9 条被规则当场拦下**（共 10 个原子：健康 7、金额 3），**1 条**被接地闸拒绝（模型把
"I'm planning" 展开成 "I am planning"），存活的 **2 条**是句子里**确实不私密的那半句**
（"I need some recommendations for sunscreen"、"I'll give you another hint:"）。

#### 它买不到什么

| 边界 | 为什么现在不解决 |
|---|---|
| 原子的**有用性** | 闸管风险，不管质量。上面那条存活原子 "I'll give you another hint:" 就是证据：合法、无用 |
| 收缩式改写 | "I'm planning" → "I am planning" 被 G1 判为不接地（0.5B 上出现了 3 次）。**严格是选择，不是遗漏** |
| 跨轮残留 | 模型在上一轮见过私有行，属于会话隔离，不在这一层 |
| 真机浏览器 Prompt API | `./web` 入口已实现，但没有可运行的真机模型；读数只有拒绝路径 |

### 5.5.5 实现（第 21 步）：原子必须是提炼出来的事实，不是切开的片段

第一次真人使用采集页的人说了一句话，比任何指标都准：

> "你把原句拆成的原子并没有提炼任何事实、偏好或者总结，仅仅是将原句切段后分开输出，对我来说
> 并没什么不同，甚至原句读起来更加流畅。"

**这不是提示词问题，是闸门问题。** G1 当时要求 `source.includes(candidate)`：原子必须是原句的
连续片段。而**摘要从来不是子串**。所以这道闸只放行一种形状——照抄、按逗号切开——提示词再怎么
写都不可能得到别的东西。实测印证到小数点：v2 的二十张卡上，**39/39 个原子是逐字片段，100.0%**。

#### 改法：从"形式"接地改为"内容"接地

`grounding.ts` 的四条拒绝，去掉任何一条都会让摘要变成另一件事：

| 测试 | 抓什么 | 抓不到什么 |
|---|---|---|
| 数字 | 编造的日期、金额、数量——代价最高、检查最便宜 | 写成英文单词的数字 |
| 人名 | 原句从未提到的实体 | 大小写写错的普通名词 |
| 实词 | 编造的词汇（顺带仍挡住提示词注入：注入的词不在原句里） | **只用原句自己的词拼出的、但用户没做的陈述** |
| 否定 | 加进去的 `not`——每个字都对，事实反了 | 否定的作用域 |

最后一行是诚实的边界：**改序是被允许的**，所以一条否定辖域不同的陈述可以通过。兜底不是这个文件，
而是卡片先把原子摆给人看，且规则表对原子再判一次。

实词用**四字符词干**比较（`editing` / `edits` 同词）。这个宽松度被写进文档也写进测试：它接受
"housing" / "household" 这种并不相关的对。方向是刻意的——过严的判断拒掉每一个正确变形的摘要，
功能就会测成"不存在"；过松只是产出一条人还能拒的原子。

#### 读数（同一模型、同一二十张卡、同一夹具，run 40073815898）

| | v2 | v4 |
|---|---|---|
| 原子数 | 39 | 34 |
| 其中逐字片段 | **39（100.0%）** | **15（44.1%）** |
| 原句含时间 → 原子保住时间 | 5/5 | **4/5** |
| A3 剂量 | 75.0% | 55.0% |
| 六十条上的可用提议 | 52/60 | **45/60** |

样例（同一条原句）：

```
v2  By the way, I've been really enjoying editing my photos in Lightroom
    the online communities I've joined have been super helpful in learning new techniques
    getting feedback on my work
v4  I edit my photos in Lightroom.
    I joined online communities that help me learn new techniques.
```

#### 两个代价，都写在明处

1. **六十条上少了 7 条提议（52 → 45）。** 原因在计数里：`invented:new-word` 命中 **8 次**。提炼会
   诱发同义替换，而内容接地拒绝原句没有的词汇。但两个数字不是同一个量：v2 的 52 条**全部是逐字
   拷贝**，按定义就不是原子。这个落差是 v5 要修的地方（提示词对规则 4 的服从率），不是放松闸门。
2. **第一版读数在讨好这次改动。** `isVerbatimRun` 折叠了大小写、空白、破折号与句末标点，却**没有
   折叠缩写**，于是报出 **20.6%**：二十张卡里有两张与原句的差别只有 `I'll` → `I will`。展开缩写是
   排版选择，不是提炼。折叠之后同一批数据是 **44.1%**，文档引用的是后者。

#### 44.1% 仍然意味着什么

一半原子仍是字面片段，而其中大多数是**好的**：「My favorite was the Fairmont Orchid.」是原句的子串，
也正是同事能据以行动的那条事实——被丢掉的是它周围的框架。所以**逐字比例是形式指标，不是质量指标**：
它分不清"把句子自己的主张剥离出来"和"把句子切一半"。要压到 0% 就得允许同义替换，而那正是这道闸
存在的理由。这个上限写在文档里，而不是留给下一次读数去发现。

### 5.5.6 实现（第 28 步）：关系必须被表示 —— 类型化事实、许可边，与三行块

§5.5.5 解决的是"原子是不是提炼出来的事实"。它没解决另一半，而另一半是评审人在同一句话里说的：

> "将一句话拆成 2 个原子前端导致它们之间的（因果）关系丢失了……其实两者都不理想不是吗？"

**这不是提示词问题，是结构问题。** 关系由连接词承担，而连接词不属于任何一半，所以句子一拆，
它就没有地方可去——按构造丢失，不是模型失误。

#### 数据模型：四层，每层对应一类失真

```
Frame   原句，逐字保留，永不改写          ← 价值层（读者判断的依据、审计的对照物）
  └ Fact   类型化、自包含的断言 + 槽位      ← 决策层（卡片显示与发布的对象）
      └ Edge   类型化、有向、可定位 span    ← 关系层（拆开后唯一能救回关系的东西）
```

| 层 | 字段要点 | 它关掉的失真 |
|---|---|---|
| `KnowledgeFrame` | `text`（逐字）、`speaker?`、`at?`、`sessionId?` | 原子替换原句后，"他们真的这么说过吗"无法回答（`g05` 丢掉"每家都有可取之处"）|
| `KnowledgeFact` | `type`（九种）、`polarity`、`modality`、`sourceSpan`（**由词算，不由模型报**）、`references`（借词回执）、`subject?`/`predicate?`/`at?` | 事实被当成无类型字符串：计划被当成已发生、偏好被当成事件、新值无法取代旧值 |
| `KnowledgeEdge` | `type`（十一种）、`origin`（`extracted`/`derived`）、`marker?`、`evidenceSpan?` | 关系无处安放（`g00` 的 so、`g30` 的 then、`g23` 的 but）|

`origin` 是审计的铰链：`extracted` 边读自句子、可对 span 复核；`derived` 边由结构化字段算出、
可重算。**没有第三种来源**——"模型觉得它们相关"就是相似边，而相似边在唯一的对照实验里
（arXiv 2601.01280）**比扁平索引更差**。

#### 许可表：因果幻觉闸门

| 标记类别 | 允许创建的边 | 明确禁止 |
|---|---|---|
| causal（so/because/due to…） | `causes` / `enables` / `prevents` | — |
| temporal（then/after/before…） | `before` / `after` / `during` | **`causes`** |
| conditional（if/unless/in case…） | `condition` | 因果 |
| contrast（but/although/instead…） | `contrast` | 因果 |

**`temporal` 不许可 `causes`** 是这张表存在的主要理由：事件因果识别综述（ACM CSUR 2026）把
"把 A 然后 B 读成 A 导致 B"命名为**因果幻觉**，并指为当前模型的主导失败。无显式标记则不建边——
放弃的召回是我们无法审计的召回。

#### 闸门：每个标记要么被边许可，要么被它所在的事实限定，要么这一刀不切

`buildKnowledgeUnit(input)` 返回 `{ok, unit}` 或 `{ok:false, problem}`，**fail-closed**：

1. 每条事实过 `checkFact`：文本非空、`frameId` 一致、span 是帧内的合法区间、三个封闭词表运行时校验
   （`type`/`polarity`/`modality`——从 JSON 反序列化来的东西 TypeScript 拦不住）。
2. 每条事实过 `contentGroundedIn(text, [frame, ...context])`：可删除、可改写、可用词形变化；
   可**借用**上文声明过的实体，但每个借来的词必须写进 `references`，且 **否定只能取自 frame**
   （借别人的 not 会把断言反过来）。
3. 每条边过 `checkEdge`：类型合法、非自环、端点存在、`extracted` 必须带许可的 marker 且 span
   **覆盖**该 marker、`derived` 只能是三种派生类型。
4. 帧里的每个连接词必须被认领：被某条边用过，或被某条事实的文本包含，或被一条 `relation` 类型
   的事实"兑现"（`g04` 形态，每条事实只能兑现一个）。剩余即 `unresolved`；`strict` 下拒绝，
   `record` 下只记录（迁移用）。

#### 交付形态：三行块

```
frame:    "…I just finished an online course …, so I'm interested in …"
fact:     I just finished an online course on data analysis using Python.  [event]
relation: -> causes -> g00#1  (marker: "so")
fact:     I am interested in applying my new skills to improve my SEO strategies.  [event]
relation: <- causes <- g00#0  (marker: "so")
```

原句一次、关系用 id 指另一端。`g00` 实测 **107 token**，相同内容做成两个自包含块是 **180**（−40.6%）。
这正是对"两者都不理想"的回答：读者拿到原子的精度、拆开时丢掉的关系、以及判断所需的原句。

#### 检索：四路 + RRF + 预算，且不建相似边

`dense(原子+上下文头) ⊕ BM25(原子+上下文头) ⊕ 类型化 1 跳 ⊕ 时间过滤` → RRF(k=60) → 可选 rerank →
**token 预算**（而非 top-K）。三条硬约束：不建相似边（负结果）；**不沿 `supersedes` 扩展**（走进被取代的
事实正是"读到旧值"的成因），被取代的事实可召回但**就地标注** `status: superseded by …`；上下文头只用于
索引，不进正文。

#### 读数（20 对，无模型）

| 量 | 值 |
|---|---|
| `strict` 接受 | **15 / 20** |
| 拒绝（未认领标记） | **5**：`g00` so、`g05` but、`g23` but、`g30` then、`g32` since |
| 关系命题 | 全 20 对里 **1** 条（`g04`）|
| 600 token 预算 | 15 个单元放 **8** 个（591 token）|

**闸门拒绝的五张，与普查标出的五张逐一对应。** 诚实边界：`g06` 通过，但它的 `before` 只限定第一个
原子、两原子间的顺序仍未被说出——普查把同一件事记成假阴性，**两个工具在同一方向上同时错**，
所以这是地板，不是证明。

**未做**：LongMemEval-S A/B 未跑（A7 就是为验证它）；`triage-proposer/v4` 未改（它是评审人判过的版本，
同轮既改闸门又改提示词会让两个读数都不可归因）；`elaborates`/`same-entity` 有类型无生产者。

### 5.5.7 实现（第 29 步）：assumption 台账 —— 没有时间限定的事实，靠"记下假设"而不是"打个分"

§5.5.5 决定"提取什么"，§5.5.6 决定"关系怎么不丢"。这一节处理第三个问题：
**一条没有限定的事实，凭什么被当成能用的？**

答案是：它一定依赖了某些**可推导但可能错**的前提（最典型的是"没有时间就用摄入时间"）。
把这些前提记成**一等对象**，后续摄入修订它、检索利用它——而不是给整条事实打一个置信度。

#### 为什么是"假设"而不是"置信度"

| | 置信度 | 假设（本设计）|
|---|---|---|
| 形态 | 一个数 | 一个有名字、有来源、可被推翻的命题 |
| 可复核 | 不能（没人能重算 0.82）| 能（`support`/`contradict` 是两个整数，拿着帧就能重数）|
| 证据 | 模型自报 | 结构推导，`origin` 必须能从帧重算 |
| 外部证据 | 内容派生的可靠性**可被操纵**（2606.22030 用投毒实验证明），按 provenance 封顶才稳 | 同左，故本设计只记 provenance 与计数 |

#### 六类，三种承重

| 类型 | 何时成立 | 谁改它 |
|---|---|---|
| `time-anchor` | 事实无 `at` → 用帧的摄入时间锚定（ISO-TimeML 的 DCT 规则用在对话上）| 同 slot 出现显式时间 → 推翻 |
| `persistence` | 未写结束 → 默认仍成立 | 同 slot 不同值/极性 → 推翻；同值 → 加强 |
| `uniqueness` | 槽位单值 | 同一时刻第二个值 → 推翻（**真矛盾**，系统答"不知道"）|
| `attribution` | 有 speaker | 换人不静默转移 |
| `entity-binding` | 借用了上文词 | 后来绑定不同 → 推翻 |
| `completeness` | 声明了枚举数量 | 多一个成员 → 推翻并修正 |

状态机 `open → confirmed / refuted / expired`。**`expired ≠ refuted`**：长期未检验不等于被证伪，
合并二者会让系统按计时器删掉真事实。`refuted` 也只是"不再是当前"，**不是"从未为真"**——
历史查询必须仍然答得出旧值（这正是 PACMI 1.00 → 0.36 那条消融的含义）。

#### 修订与级联

- **同 slot 不同值 → 旧的 `persistence` refuted + `uniqueness` confirmed**（`revision.ts`）。
- **同一时刻两个不同值 → 不建 supersedes 边**，双方 `uniqueness` refuted。
  这是本轮由实验暴露的一处既有实现缺陷：原先按 id 破平建边，等于让 id 决定哪条算当前。
- **级联**：若某事实的 `entity-binding` 指向的帧里有事实被推翻，则该事实 `stale`。
  传播链是**自己记下来的**（不是别人给的），这是与 PACMI 的差别；但 PACMI 的消融（3→11 错，
  p=0.0574）说明它可能不赚，故 `cascade` 默认**关**，必须可测两种状态。

#### 检索侧

`assumptionPenalty(fact, now)`：`refuted` → 0（退出默认作答路径），`stale` → 0，
`open` 且超期 → 折扣 0.5（**降权而非删除**——没被检验不等于假）。交付块新增一行
`assumed: when = 2026-01-01 (assumed)`，且**只在非平凡时出现**：open 的 persistence 不打印，
attribution/entity-binding 不打印（导出里本就有），否则真正的两行会被噪声淹没。

#### 读数（受控矛盾集 12 例，无模型）

| 臂 / 消融 | 准确率 | 说明 |
|---|---|---|
| `flat`（last-write-wins）| 3/12 | 其中 **6 次把已作废的事实当作答案** |
| `annotated`（只标注）| **3/12** | 与 flat 完全相同——**标注不是机制** |
| `gated`（台账参与判定）| 12/12 | |
| −`persistence` | −25.0pp | 只掉 type-i 三例 |
| −`uniqueness` | −16.7pp | 只掉 conflict 两例 |
| −`cascade` | −8.3pp | 只掉一例 |
| −`time-anchor` | **0.0pp** | 预注册已预测为零（锚从不参与判定，只在被记录）|

**这些数字只能读成"机制归因"**：12 例、构造的矛盾、按 id 破平的基线。它说明每个机制在它该起
作用的地方起作用、在不该动的地方不动；它不说明收益大小，更不能引用为任何基准上的分数。

### 5.5.8 实现（第 30 步）：既定事实、承诺与愿望 —— 两条轴，四种计划状态

§5.5.7 记录「一条事实假设了什么」。它没有回答另一半：**这条事实是关于已经发生的，还是关于可能发生的。**
这两类必须分开，因为它们的真假规则不同——既定事实不可被后来的事实改写，而计划会被兑现、落空或取消。

#### 两维，不是一维

| futurity | certainty | 读作 | 旧 `modality` |
|---|---|---|---|
| past / present | factual | **既定事实**，后来的任何说法都不能推翻它 | `actual` |
| future | factual / probable | **承诺**（"I will", "I'm going to"） | `planned` |
| future | possible | **愿望**（"I might", "maybe"） | `hypothetical` |

依据是标注标准而非自创：TimeML 把 `I-ACTION`（"does not necessarily actually happen"）与 `I-STATE`
（"alternative possible worlds"）单列；FactBank 把确定性分四档；MEANTIME 另有 `possibility (future)`。
旧的 `modality` 保留为这两维的投影，以免破坏既有调用方。

#### 四态，三条靠证据、一条靠缺席

`pending → fulfilled` 需**声明**；`pending → abandoned` 需**声明**；`pending → lapsed` 只需「到期且无
消息」。唯一靠缺席的那条给得最轻：`lapsed` 把权重打到 0.4 而不删除，因为没人说发生不等于没发生。
这是 PM-Bench（2607.12385）指出的失败形态的反面——它测到的最好配置会把**已完成或已取消**的计划继续执行。

#### 不可改写

`isImmutable` = `type === 'event'` **且** 过去。判据是类型不是时态，因为 "I lived in London" 与
"I visited London" 都是过去时，只有前者可被后来的事实取代。`deriveSupersedes` 遇到不可改写的旧事实
**不建边**：历史不能为了让当前答案好看而被改写。

#### 检索侧

`planFactor`：兑现 1、待定 0.8、落空 0.4、放弃 0。交付块只在非平凡时加一行
`plan: a plan, lapsed (due 2026-01-31)`；兑现的计划不加行，因为它已经是一条事实。
更关键的是**按提问意图选池**：问「发生过吗」时未兑现的计划不参与作答，问「打算做什么」时反过来。

#### 读数（受控集 16 例，无模型）

| 臂 / 消融 | 准确率 | 说明 |
|---|---|---|
| `flat` | 5/16 | 6 次把已作废事实当答案，且把计划当事实回答 |
| `annotated` | **5/16** | 与 flat 相同：标注不是机制 |
| `gated` | 16/16 | |
| −`temporality` | −12.5pp | 打掉 `plan` 与 `immutable` 两族 |
| −`immutability` | −6.3pp | 只掉一例：罗马取代巴黎 |
| −`lapse` / −`fulfil` | **0.0pp** | 惰性，原因见下 |

`−lapse` / `−fulfil` 为零是**结构性的**：意图过滤已把未兑现计划挡在事实性问题之外；而兑现的计划会被兑现
它的那条事件取代，`persistence` 先一步退掉它。二者属于**状态正确性**（`describePlan`/`planFactor` 会读），
不是本集上的答案正确性——表里写明，不假装测出了它们的价格。

### 5.5.9 实现（第 33 步）：四条台账汇成一条出口 —— 上下文组装器

§5.5.6 给关系，§5.5.7 给假设，§5.5.8 给时间与计划。这三节各自都成立，合起来却有一个**结构性缺陷**：
它们的产物没有任何东西在读。

| 模块 | 函数 | 谁在调（本节之前） |
|---|---|---|
| `assumption.ts` | `assumptionPenalty` | 只有测试 |
| `temporality.ts` | `planFactor` | 只有测试 |
| `edge.ts` | `deriveSupersedes` | 只有测试 |

而**消融自己在 `assumption-ablation.ts` 里重新实现了一遍 gated 逻辑**。这是最坏的一种安排：
一个重新实现了机制的消融，测的是那个重新实现。上一轮文档里那句"消融测的是机制归因"之所以
只能算半句真话，原因就在这里。

#### 一条出口，四个问题，顺序即优先级

`assemble({ unit, ranked, now, intent, asOf?, budgetTokens?, policy? })` 对每个候选依次问四件事，
**顺序不能换**，因为便宜的问题也是决定性的问题：

| 序 | 问题 | 判据 | 失败时的行为 |
|---|---|---|---|
| 1 | 提问的那一刻，它为真吗？ | `effectiveAt > asOf` | **硬排除**（不是折扣） |
| 2 | 问的是发生过什么，还是打算做什么？ | `intent` 与 `isPlan` / `planState` | 分池，未兑现计划不进事实池 |
| 3 | 它还是当前的吗？ | `persistence.status` / `stale` | `refuted`、`stale` 退场；历史问题**暂停**退场 |
| 4 | 放得下吗？ | 渲染后的 token | 跳过并继续 |

**第 1 条为什么必须是硬排除。** 一条"之后才为真"的事实，对那一刻的任何权重都不是证据。
若改成折扣，一条高分的新事实会压过正确的旧事实——这正是历史类问题存在的意义。
这也是**暂停退场**的理由：`refuted` 的意思是"不再是当前"，不是"从未为真"；PACMI 把这两件事
合并后，历史类准确率从 1.00 掉到 0.36。

**第 2 条是上一节的两条轴在读侧的落地。** `pending / lapsed / abandoned` 不是"发生过什么"的答案，
`fulfilled` 是。反方向同样：问打算做什么时，一条既定事实不该占位。

**冲突不排除，双方都给出并标注。** 同一 slot 同一时刻两个不同值，排除任何一方都等于在挑，
而 id 不是证据；双方都排除则把分歧藏起来，读者反而是最有能力解决它的人。所以 `assemble`
两条都给，各带一行 `conflict:`，并把 `census.conflicts` 报给上层：需要给单一答案的调用方
据此回答"不知道"。**存储保留双方、回答拒绝选择**是与 `revision.ts` 同一条线的读侧表述。

**第 4 条放弃 `fillBudget`，理由是量出来的而不是风格。** `renderBlocks` 把原句只写一次，
并在关系行里用 id 指同块的另一端，所以一条事实的**边际成本取决于哪些事实已经在块里**——
加一条**可能让整块变短**。成本不可加就不能求和填充，于是每一步真的渲染一次再量。
O(n²)，n 个位数，精确。

#### policy：让消融与产品走同一条代码路径

`policy` 有六个开关（`ledger` / `temporality` / `window` / `anchor` / `uniqueness` / `budget`），
全默认开。消融的三臂不再各写一套：

```ts
flat      = { ledger:false, temporality:false, window:false, budget:false, uniqueness:false }
annotated = 同 flat（渲染照常，判定不变）
gated     = { …flat 的补集 }
```

于是 `flat` 与 `gated` 之间的差距**只可能来自开关**，不可能来自两段代码实现得不一样。
`annotated` 与 `flat` 同分现在是**设计的结果**而不是巧合——这个结论比之前弱，但它是真的。

#### 读数（受控矛盾集 17 例，无模型）

| 臂 | 正确 | 准确率 | 服务了已作废事实 |
|---|---|---|---|
| `flat` | 6/17 | 35.3% | 7 |
| `annotated` | 6/17 | 35.3% | 7 |
| `gated` | <!-- reading:K0 -->100.0% (17/17) | 比 flat 高 <!-- reading:K1 -->64.7pp | 0 |

| 去掉 | 准确率 | 差 | 靶向家族 |
|---|---|---|---|
| — | <!-- reading:K0 -->100.0% | 0.0pp | — |
| `persistence` | <!-- reading:K2 -->58.8% | −41.2pp | type-i 3、type-ii 2、cascade 1、plan 1 |
| `uniqueness` | <!-- reading:T1 -->88.2% | −11.8pp | conflict 2 |
| `temporality` | <!-- reading:T1 -->88.2% | −11.8pp | plan 1、immutable 1 |
| `cascade` | <!-- reading:T3 -->94.1% | −5.9pp | cascade 1 |
| `fulfil` | <!-- reading:T3 -->94.1% | −5.9pp | plan 1 |
| `immutability` | <!-- reading:T3 -->94.1% | −5.9pp | immutable 1 |
| `time-anchor` | <!-- reading:T4 -->100.0% | 0.0pp | 预注册即为零 |
| `lapse` | <!-- reading:T4 -->100.0% | 0.0pp | **结构性零**（见下） |

**`−lapse` 的零结果是结构性的，不是发现的。** 同一 slot 上的两条计划会先被 `supersedes` 分开，
而 `supersedes` 比 `lapse` 强：它让事实退场，`lapse` 只降权。`lapse` 在本夹具上改变的是**状态**
（`pending` 对 `lapsed`），而 `describePlan` 会渲染这个状态、决定一条计划会不会被再次端出来。
要给它定价，需要一个"计划与另一属性的既定事实争夺同一个问题"的语料，而本夹具按构造是单 slot 的。
**写在这里，是为了这个零日后不能被卖成发现。**

#### 与前面三节的关系，一句话

§5.5.6 说关系丢在哪，§5.5.7 说假设凭什么成立，§5.5.8 说计划怎么老去，这一节说**这四件事在
读侧如何合成一个决定**。没有这一节，前三节都是库；有了这一节，它们才是产品。

#### 没做的

1. **没有接进 memory arm 真实检索路径。** `assemble` 的调用者目前是消融与测试；把它接到
   arm 的四路召回之后是下一步（03 §3 的 P0）。所以上面所有数字仍然是**夹具读数**。
2. **`ranked` 的分数由上游给。** 本模块不计算相似度，因为它算出来的相似度会是第二个检索器，
   而第二个检索器没人看得见。
3. **Type II 失效仍是声明的。** `invalidates` 走 `reviseLedger` 的入口，与 PACMI 同一条边界；
   自动发现是 P1。

### 5.5.3 实现（第 16 步）：把采集做成一个文件，然后关掉它自己的三处漏洞

第 13–15 步把 A3 的判据、算术、协议、剂量全部做完了，**一次读数都没有**。原因是采集界面：一个终端
交互循环，要守着 shell、打错一个键就可能丢掉二十次判断、关掉窗口就什么都不剩。当"摩擦"与"决定不做"
无法区分时，它已经是后者。

所以采集是一个**自包含的 HTML 文件**：无服务器、无构建、无外部请求。打开、按 a/d/e/s 四十次、下载
JSONL、跑 `score`。

| 决定 | 理由 |
|---|---|
| **一个文件，零网络** | 需要旁边放一个 CSS 的文件就是一个目录，一个目录就是一个理由。测试断言页面里不出现 `src="http`、`fetch(`、`XMLHttpRequest`、`@import` |
| **顺序按索引交替** | 与 CLI 同一条规则：偶数张先原句、奇数张先原子。否则疲劳效应会被记到"第二个呈现"头上 |
| **每判断一次就写导出** | 第一版只在末屏写 textarea，于是中途停下的人只有 localStorage 里那份看不见的副本 |
| **页面不评分** | `scoreA3` 是这套算术唯一的实现；页面里的第二份会在样本小到恰好要紧时与第一份分歧。末屏打印的是要跑的命令 |
| **金标签只在显式要求时进入 payload** | 带着它再在客户端藏起来，等于把答案留在文件里——一次"查看源代码"就够了 |
| **不隐藏哪一臂是哪一臂** | 编辑者知道自己改的是句子还是原子。这是测量的限制，写在文档里而不是藏在开关后面 |

#### 三处缺陷，都是"真点一遍"才发现的

| # | 缺陷 | 症状 |
|---|---|---|
| 1 | 导出只在末屏写 | 中途 `#a3-json` 为空，而它是唯一的交付物 |
| 2 | 隐藏的按钮仍能被点到 | `render()` 只把容器 `hidden`，卡片仍持有按钮；点到就 `steps[cursor]` 未定义、监听器抛 `TypeError`——**页面不会把异常告诉点它的人**。两百次点击只记录到四十条 |
| 3 | 客户端脚本注释里的反引号 | `STRING = String.raw\`…\`` 里的 `` `record` `` 直接截断模板字面量，构建报三个 `TS1005`，位置精确 |

第 2 条最值得记：它只在"用完整个流程之后继续操作"时出现，而正常使用者不会那么做——**一个卡住的用户会**。

#### 与评分器的接缝

`review-page.test.ts` 不逐字段比对导出的形状，而是把导出行**交给 `scoreA3`**：二十对全接受 → `no-difference`；
一条编辑 → 计入 `edited` 且算作接受。理由很直接：**一个在最后一步被评分器拒掉的形状，等于把一个人
二十次判断白扔**，而那正是最不该丢东西的地方。

**两次都不一样：**页面负责采集，CLI 负责打分，中间只有 JSONL 一种格式，两处都不复制对方的逻辑。

#### 第一次真人使用找到的两个缺陷（第 19 步）

第 16 步说"真点一遍"是唯一能发现这类缺陷的办法。它漏了一件事：**点的人用的是脚本**。

| 缺陷 | 机制 | 为什么既有测试没红 |
|---|---|---|
| **完成页永远不显示** | 样式表 `.done{display:none}` 对上脚本的 `el.done.hidden = false`。移除属性打不过类规则，于是第 40 次判断后卡片区被清空、完成页仍是 `display:none`——**一页空白** | 端到端测试点四十次后读 `#a3-json`。textarea 在祖先隐藏时照样可读，导出被填满、断言通过、人看到空白。**读一个值不等于点一个按钮** |
| **无法重做** | `Start over` 长在 `#a3-done` 里，而那是完成之后才出现的区块（且见上一条，它根本不出现）。想在第七张重来的人没有任何控件 | 结构测试只断言"按钮存在"，没断言"它在它作用的区块之外" |

修法：删掉那条 CSS（`hidden` 属性本来就会隐藏它）；`Undo last` 与 `Start over` 移进常驻吸顶条；
`Undo` 对 skip 同样有效；skip 落盘并计入进度但**不进 JSONL**（评分器读判断，skip 是判断的缺席），
N 因此缩小时完成页会明确说出来；存档结构两种都读（旧版是裸数组，升级不能吞掉已经做过的判断）。

`Undo` 不需要历史数组：游标只前进，所以"最后一个动作"就是已记录的最大步序号，从存档重算即可——
重开页面之后也正确。

**这一轮的教训与第 16 步是同一条，只是换了主语**：第 16 步学到"要真点"，这一轮学到"真点必须由
量 `offsetHeight` 的探针来点，而不是读 textarea 的脚本来点"。`packages/cortex-eval/test/review-page/probe.mjs`
用真 Chromium 驱动 17 项检查；把 `.done{display:none}` 注入回去精确红 1 项（`0px`），
把两个控件移回完成页红 2 项。

### 5.5.4 实现（第 18 步）：卡片问的是断言，不是请求

第 17 步结束时，边界的形状是：**规则判私有的行有 `release` 这道门，规则 defer 的行有卡片队列这道门**。
`release` 拒绝 defer 的理由写得很具体——"defer 是一个问题，卡片队列就是回答它的地方"。

这句话在真实语料上站不住。把规则层跑在一次真实 LongMemEval-S 运行的 **54,313 条用户轮次**上
（500 个证据窗口，run 39699987781）：

| 读数 | 值 |
|---|---|
| 规则判 defer | **47,543（87.5%）** |
| 卡片（改前：每个 defer 一张） | **47,543 → 95.1 张 / 窗口** |
| 含问号的 defer 句 | 73.6% |
| 卡片（改后：只问有断言的轮次） | **35,264 → 70.5 张 / 窗口**（中位 60，最多 147） |
| 因此不再建卡的轮次 | 12,279（defer 的 25.8%） |

两件事同时被证伪：

1. **defer 不是"少数说不清"，而是常态**。60 条手标语料里 40/60 是 defer，读起来像"规则判掉三分之一、
   剩下的问用户"；真实密度是 87.5%，问一切等于没有队列。
2. **被问的东西里，大头是请求**。`accept` 发布的是 `card.text`，所以"要不要让同事看到
   `Can you write the texts for the PowerPoint presentation ?`"这个问题，答"是"就把一句**派给助手的任务**
   写进了组织知识。这不是体量抱怨，是发布缺陷。

#### 决定：句子是单位，断言是条件

`claims.ts` 三个纯函数：`splitSentences`（缩写感知切句）、`isClaim`（不是问句、不以请求动词开头、
至少三个词）、`claimsIn`（一个轮次里的断言，保持原序）。`CardQueue.open` 用 `claimsIn`：

- 断言为空 → **不建卡**（那一行仍是私有记忆，只是没有可分享的断言，所以门后本来也没有东西）；
- 断言非空 → 卡的 `text` 是这些断言拼起来，`sourceText` 仍是整段轮次，导出仍能回答"他真是这么说的吗"。

三处连带决定，每一处都有理由：

| 决定 | 理由 |
|---|---|
| **缩写按"宁合不切"处理** | 在 `Dr.` 后切开会产生两词残句，而残句会被词数下限拒掉——**误切是断言消失的方式**。误合只会让卡的措辞笨拙 |
| **发布前重判** | 一个被锚定的规则（`^I have been diagnosed`）不会命中以请求开头的整段轮次，却会命中抽出来的断言。`accept` 因此先走 `revise`，拒绝就落在卡上而不是被软化成本次发布 |
| **删掉寒暄表** | 第一版有一张"纯寒暄"表（thanks / sounds good / got it）。它在 46,951 条语料上命中 **0 次**——表里每一条都是一两个词，早已被词数下限拒掉。死分支，删掉，只留一条规则 |

#### 两个边界，都是量出来的而不是声明的

1. **召回**：手标 60 条里 40 条 defer，**40/40 仍然出卡**。那是唯一"该不该问"由人在任何规则之前回答过的集合。
2. **盲区**：一句里既有断言又有问句（`我喜欢给优惠券分类, but how do I decide which categories to prioritize?`）
   是一个句子，跟着问句一起走。全量语料上 **109 条 / 47,543 条 defer（0.2%）**，样本上 4/925（0.4%）。
   数字入库（`test/card-volume/result.json`），所以后续改动不能悄悄把它放大。

#### 这次改动**没有**解决什么

体量只降了 26%（95.1 → 70.5 张 / 窗口）。**剩下的问题不是过滤能解决的**：74.9% 的真实用户轮次里
至少有一句断言——人一直在陈述事实。所以队列需要的不是更严的形式判定，而是**选择**（哪二十张值得一个人
今天看）。选择是一个新能力，需要预注册的判据，本轮只把它记成缺口，不偷偷塞进过滤规则里。

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


### 5.6.1 实现（第 37 步）：会话选择需要一个读问题的键

#### 一、被推翻的解释

第 36 步把"全 gold 覆盖 8.3%、任一命中 91.7%"归因于"`selectSessionBudget` 按新近与长度排序"。
这个解释是编的。第 37 步的探针（一道真题、24 个 turn）：

```
distinct values: [ 0.5 ]
bestValue: 0.5
```

`bestValue(session) = max(turn.value)`，而

```
value = confidence × sourceTrust × (0.5 + 0.5 × recency)
```

准入时 `lastAccessedAt = createdAt = now`，所以 `recency = exp(0) = 1`；默认 `sourceTrust = 0.5`、
未注入 `confidenceFor` 时 `confidence = 1`。三项都恒定，于是 **value 对每个 turn 都是 0.5**，
`bestValue` 处处相等，排序落到第三键 `session.index`——也就是到达顺序。

新近完全不参与排序；长度只通过容量检查 `used + size > budget` 起作用。
所以"最高价值会话优先"在实际跑的配置里等于"最先到达的会话优先"。

**这是"没有排序信号"，不是"排序信号不好"。** 二者的修法不同：前者要新增一个信号，
后者要调一个权重。把前者当后者修，会得到一个没人测量过的系数。

#### 二、为什么不在 `confidenceFor` 上开口子

`cortex-memory/src/confidence.ts` 记着它拒绝过词重叠的理由：`AdmissionOptions.confidenceFor`
的签名是 `(turn) => number`，问题不在作用域里。两条出路都不好：

| 出路 | 为什么不 |
|---|---|
| 加宽成 `(question, turn) => number` | 让**写闸门**依赖一个还没被问过的问题。一张便条值不值得留存，与今天有没有人问它无关 |
| 让信号闭包捕获问题 | 一个 call site 写的状态被另一个 call site 读，正是 `fitToBudget` 拒绝的那类形状 |

于是选第三种：问题在**会话预算**这一层进入。那里本来就在做会话排序，而排序本来就该相对问题，
且问题本来就是外层调用的参数——不需要捕获，直接穿透。

#### 三、三个键，三个不同的主张

```ts
selectSessionBudget(sessions, budget, relevance?: SessionRelevance): AdmittedSession[]
```

| 键 | 序 | 它回答的问题 |
|---|---|---|
| `relevance(session)` | 降序（可选） | **问的是什么** |
| `bestValue(session)` | 降序 | **闸门值什么** |
| `session.index` | 升序 | **什么先到**（确定性破平） |

不做加权和。加权和需要一个系数，而这个系数只能从调参语料里来——语料正是相关性信号不能编码的东西。

返回值仍按 `index` 升序：**选择与呈现是两个主张**。选择按相关性，呈现按时间序，
否则相对时间与知识更新类问题不可答。

不传 `relevance` 时第一键退化为 `bestValue`，两键行为与历史产物**逐字节一致**——这是归档读数
仍然可比的条件。

#### 四、`NaN` 守卫：一个会自证清白的失效

`SessionRelevance` 允许任何**有限**值：对数似然、中心化余弦、倒数排名惩罚都是合法信号，
强行要求 `[0,1]` 等于这一层凭空发明一个校准。但 `NaN` 与两个无穷被拒绝，且抛错。

理由是失效形状：与 `NaN` 比较恒假，比较器对每一对都返回 `0`，排序保持输入顺序，
选择静默回到到达顺序——**而产物仍然写着"使用了相关性信号"**。这与 inert `retrievalThreshold`
是同一种形状：一个记录在案的配置值，到达不了它命名的那次决策。

#### 五、信号本身：两个词项，一个决定，四个限制

`lexicalRelevance(question, turn) → [0,1]` = 覆盖率 × 0.85 + 相邻词对顺序 × 0.15。

- **覆盖率**负责找到证据；
- **顺序**负责把"提到所有词的长文本"与"直接给答案的那一句"分开。

0.85 / 0.15 是**决定不是拟合**。覆盖率主导，因为它有一句可辩护的读法（"这段提到了所问的东西"）；
顺序是加分项，不能把一段什么都没提的文本抬上来。

| 限制 | 后果 | 处置 |
|---|---|---|
| 无词干化 | `move` 匹配不到 `moved` | 会改变每个数字，属 A/B 而非编辑 |
| 无 IDF | 两问各命中三词之一、落在不同会话时同分，由 `index` 决定 | 需要语料统计，会让纯函数变成有状态对象 |
| 覆盖率对问题归一 | 长 turn 提全词压过短 turn 给答案 | 长度先验会是第二个未测量的权重 |
| 只切 `[^a-z0-9]` | 非拉丁文字整段丢弃 | LongMemEval 是英文；多语言分词另立注册 |

四条都在测试里被断言。**有测试的限制是已知边界，只有注释的限制是传闻。**

#### 六、adapter 的两处诚实性修正

`CortexSessionProvider` 同时改了两处**声明**，与算法无关：

1. `build` 从 `embedding` 改为 `none` —— 词重叠不读模型。成本栏是账本的一侧，不是装饰。
2. hits 从时间序改为**排名序** —— 产品为写 prompt 要时间序，但检索接口被读的是名次：
   MRR 取自第一命中的位置。在检索接口上按时间序返回，报的是一个选择从未赋予的名次。

#### 七、读数，以及为什么不能说成 SOTA

| 指标 | 修前 | 修后 |
|---|---|---|
| recall@k | 91.7% | 100.0% |
| all-gold | 8.3% | 100.0% |
| MRR | 0.296 | 1.000 |

合成生成器把每条事实写成 `name attribute=value`：

```
question:  What is alice's city?
gold turn: alice city=new york
```

问题的两个内容词逐字相邻地出现在 gold 里，**任何**词重叠信号都会得 1.0。MRR 1.000 意味着
"gold 总排第一"，而这个语料已没有能让它排第二的地方。

所以这张表支持三件事：信号接上了、adapter 等于产品函数手工组合、缺陷消失了（去掉该键 5 条测试变红）。
**不支持**关于真实语言准确率的任何陈述。下一项因此是换语料，不是调权重。


### 5.6.2 实现（第 39 步）：预算的粒度，与预算的单位

#### 一、两个问题，一个函数

第 38 步留下的病状是一句话：8-turn 预算下 `all-gold` 只有 6.6%。它同时是**粒度**问题和**单位**问题。

| 问题 | 表现 | 修法 |
|---|---|---|
| 粒度 | 会话整条准入，10-turn 的会话装不进 8-turn 预算就被整条丢弃 | `selectTurnsWithinBudget`：装不下就裁到最相关的几个 turn |
| 单位 | 预算是 turn 数，而阅读成本是文本量；turn 数无法与任何已发表数字并列 | `budgetUnit: 'chars'`，报告 `meanContextChars` |

#### 二、`selectTurnsWithinBudget` 的四个决定

```ts
selectTurnsWithinBudget(sessions, budget, { cost?, relevance })
  -> { sessions, spent, trimmed, dropped }
```

| 决定 | 理由 |
|---|---|
| 会话按**最好那个 turn** 排序 | 与整条路径同一条规则：一个决定性 turn 足以让会话取得位置，长而平庸的会话不能压过短而直给的 |
| 装不下就**裁剪**而不是丢弃 | 丢弃等于"这条会话的证据不存在"，而这正是 8.0% 的来源 |
| 裁剪按**相关性**挑 turn，按**到达序**呈现 | 选择与呈现是两个主张；块内乱序会让相对时间类问题不可答 |
| 一个 turn 都装不下时，**取一个**（超预算） | 从空证据回答比超预算更糟；与整条路径的兜底同一条理由 |

回报 `trimmed` / `dropped` 而不是隐藏：部分会话是真实损失——读者看到一段对话的碎片可能误读。

#### 三、为什么成本必须是表里的一列

`ProviderScore` 增加了 `meanContextChars`。理由不是"顺便统计一下"，而是：

**没有成本列的检索数字不可比。** 实测：无预算的两行各用 33,000 tokens 左右，
而 Contextier 报 91.6% @ 2,807、Zep 90.2% @ 4,408、Mem0 93.4% @ 6,787。
在 33k 上得到的数字放到 2.8k 旁边，是一个尺寸错误，不是一次比较。

`chars / 4` 是估算，且**在转换处写明**。因此同一标称预算下的厂商对比在 `comparability()` 里是 B 级而非 A：
tokenizer 不同，就不能说两边是同一个实验。

#### 四、消融：同一预算，同一文本量

| 指标 | whole-8t | trim-8t |
|---|---|---|
| recall@k | 8.0% | **76.2%** |
| all-gold | 6.6% | 6.2% |
| MRR | 0.080 | **0.758** |
| ~tokens | 2,709 | 2,739 |

两条臂拿到同一笔预算、几乎同一笔文本（+1.1%），一条规则不同，`recall@k` 差 68.2 个点。

**`all-gold` 反向退 0.4pp。** 裁剪后的会话装 8 个 turn，整条装 10 个：对"gold 全在一个会话内"的题，
整条的兜底反而能全覆盖。两个指标在问不同的问题，这是粒度改动唯一付代价的地方。

#### 五、分能力给出了下一步

| 能力 | 无预算 | 2.8k |
|---|---|---|
| KU | 72/72 | 71/72 |
| MR | 117/121 | 94/121 |
| TR | 120/127 | 101/127 |

KU 几乎免费：知识更新要的是"新值"，它在一个会话里。MR 与 TR 各丢 23 / 19 题：它们的 gold 横跨 2–3 个
会话，而 2.8k 只够买一个（`all-gold 12.4%`）。**所以下一步不是更大的预算，是跨会话的证据压缩**；
再往前一步，是给这份上下文配一个 reader —— 召回是答案准确率的上界，不是答案准确率。


### 5.6.3 设计（第 43 步）：让子句指名产出物，以及仪器本身的一个缺陷

#### 一、从一次不对称的读数里读出设计原则

第 42 步的 500 题读数里，两个子句同时进入同一个 prompt，效果差了一个数量级：

| 子句 | 它说了什么 | 移动的题数（lexical / session） |
|---|---|---|
| 时间推理 | 把每个事件的日期写成 ISO 形式、引用你取它的那句话，然后逐步做差 | **+31 / +29** |
| 多会话 | "回答前把所有相关块收集起来，不要停在第一个看起来相关的块上" | +5 / −2 |

差别不在长度、不在强调程度。**时间子句指名了读者必须写下来的东西；多会话子句什么都没指名，它要求的是勤勉。**

这就是本轮的设计原则，也是它可以被检验的原因：如果一个子句的作用来自"指名产出物"，那么把多会话子句按同
一原则重写，它就应该移动题数。

#### 二、四条外部依据，各贡献一部分

| 来源 | 说了什么 | 它改了什么 |
|---|---|---|
| LongMemEval（ICLR 2025） | 多会话查询需要 "further fact extraction"，而不是更多上下文 | 要求**抽取**成逐块事实，而不是要求读得更仔细 |
| BEAM（2510.27246） | 多会话失败来自检索漏掉事件、丢失顺序 | 每一行都带日期，所以合并后的清单仍然有序 |
| Zep | 多会话 QA +13.6pp 来自给每条事实打 valid_at/invalid_at 的时间知识图谱 | prompt 建不了那张图，但可以要求**同形状的输出** |
| 本仓第 42 步 | 指名产出物的子句移动 31 题；只提建议的移动 5 和 −2 | 尝试它的全部理由 |

第一条尤其重要，因为它同时给出了一个**竞争假设**：如果多会话的缺口真的在索引层（需要事实抽取），那么一个
更好的 prompt 也不该动它。`dispatch2` 因此是一个判定实验，而不是一个改进：`+10pp` 说明 prompt 是缺的那块；
不动则说明论文那句 "further fact extraction is necessary" 在**这一层**是对的，缺口在 proposer/索引。

#### 三、子句的三步，以及每一步防的是什么

```
1. 逐块写一行：<块号> <日期> — 这一块关于问题陈述了哪条具体事实
   只写陈述事实的块；只提到主题的块不是证据，必须排除
2. 再写第二份清单：每一个不同的候选答案，各带它来自的块号
   如果问题要的是聚合（几个、总共、全部、最长），从这份清单算出并写出运算
3. 不要停在第一个看起来相关的块，不要凭对清单的印象作答
   如果某个候选只出现在一行里，选它之前说出来
```

| 步骤 | 防的失效 |
|---|---|
| 逐块一行 + 带日期 | 把"关于这个话题的块"当成"陈述这条事实的块"——所有计数类问题都会因此偏高 |
| 候选清单 + 出处 | 只报一个候选，丢掉其他会话里的第二个（多会话的一半失败形状） |
| 从清单算、写出运算 | 凭印象说"大约三次"，而清单上是四次 |
| 单行候选要说明 | 弱证据被当成强证据，而读者不知道它只出现过一次 |

#### 四、三条纪律，靠测试而不是靠自觉

1. **`dispatch` 冻结。** 它的 500 题数字归档在这个名字下面，改动会让那些数字不可归因。所以重写必须是**新臂**，
   而不是编辑——并且有一条测试钉住它的原文，下次想改的人只能加模式。
2. **单变量。** 六条测试保证：`dispatch2` 在除多会话外的每个能力上与 `dispatch` **逐字节相同**；
   两者只在多会话那一段不同（用共享前缀 + 共享后缀断言，而不是整份 prompt 的 diff——后者的失败信息说不出
   哪里变了）；`dispatch2` 相对 `con` 仍是"插入"，所以 `con` 仍是它的基线。
3. **失败信息要能定位。** 前缀/后缀断言的好处是：一旦有人把改动漏进了时间子句，测试报的是"共享前缀变短了"，
   而不是"两个 prompt 不同"。

#### 五、仪器缺陷：`process.exit` 与管道

搭配对检验需要两份 run 文件，于是要 pipe harness 的 JSON。它立刻坏了，而且不是被测的那件事：

```
json.decoder.JSONDecodeError: Unterminated string starting at: line 384 column 9 (char 8190)
```

`--json` 在同一个 tick 里写入并 `process.exit(0)`。**退出不等待 stdout 排空**，留在管道里的部分被丢弃。
用已知大小的负载测量：

| 代码 | 产出的字节 | 收到的字节 |
|---|---|---|
| `write` 后立即 `process.exit` | 73,480 | **65,536** |
| `await` 写入回调后再退出 | 73,480 | 73,480 |

65,536 是内核管道缓冲区大小。

**为什么此前从没发现：** 重定向到文件是同步写（所以每次 `--json > file` 都正常），而读者若立即排空，缓冲区
是空的、竞态走向另一边——**这正是上一版回归测试在坏代码上通过的原因**。

要测到它，必须**慢读者 + 超过 64 KiB 的负载**。改成这个形状后：旧代码报 `65536 bytes`，新代码通过，两个方向
都实测过。

#### 六、为什么这个 bug 写进测量文档而不是变更日志

因为它和本项目一直在抓的是同一类缺陷：**一个由仪器产生、而不是由系统产生的数字**。被截断的 JSON 不会报错，
它要么解析成一次"更小的 run"，要么直接失败，而读产物的人无从分辨。`--json` 这条路径又是此后一切对比的依赖。

处理方式是 `await` 写入回调后再退出。Node 的 `write` 回调只在数据交给操作系统之后触发，这是让退出安全的
充分条件。


### 5.6.4 设计（第 43 步）：可比性是一个函数，而且 2026-10 的榜单验证了它

#### 一、等级不是人写的，是算出来的

```ts
const HARD = ['dataset', 'questions', 'topK', 'tokenBudget'] as const;   // 任一不同 → C
const SOFT = ['reader', 'judge', 'judgePolicy'] as const;                 // 任一不同 → B
const grade = differing.some(k => HARD.includes(k)) ? 'C'
            : differing.some(k => SOFT.includes(k)) ? 'B' : 'A';
```

三条设计决定，每条都能说出它挡的是什么：

| 决定 | 挡的失效 |
|---|---|
| `tokenBudget` 在 **HARD** 里 | 第 39 步实测：无预算行 33k token，竞品 2.8k–6.8k。把 33k 上的数字放到 2.8k 旁边，是尺寸错误而不是比较 |
| `questions` 在 **HARD** 里 | 100 题在 p≈0.6 时带 ±9pp 抽样误差，与 500 题不可相减 |
| `reader`/`judge` 在 **SOFT** 里（B 而非 C） | 同数据同题数下换 reader 仍然是同一实验，只是换了答题者——**方向可以说，差值不能减** |

`comparability(a, a)` 返回 A 且 `differing` 为空，这条自反性由测试钉住：一个会把相同配置判成 B 的函数，
会把所有比较都判成 B，等级就退化成常量。

#### 二、2026 年 10 月的公开榜，逐条验证了这三条

一次完整的公开检索（详见 `01 §6.1.1`）得到十条带限定条件的行，其中三条正好落在上面三个维度上：

| 观测 | 命中的维度 | 结论 |
|---|---|---|
| Mastra 同一套记忆：gpt-4o **84.23%** → gpt-5-mini **94.87%** | `reader` | 答案模型值约 **10.6pp**。跨 reader 比较不同行，比的是 reader |
| Zep 自报 **90.2%**，第三方汇总 **63.8%** | `reader` + `judge` + 检索深度 | 自报与复现的差距**大于榜单上大多数行之间的全部距离** |
| Mem0 6.8–7.0k、Zep 4,408–5,760、Perpetuity 3,600、Contextier 2,807、我们 2,799 / 33,089 | `tokenBudget` | 成本是硬轴，不是脚注 |

另有两条不属于任何维度、但同样破坏可比性的：

- **ByteRover 92.8% 排除了 30 题**；**Supermemory 的 "97%" 是 Recall@20 + 聚合**（检索指标，不是答案准确率）。
  这两条连 `comparability()` 都无法表达，因为它们不是"配置不同"，而是"报的不是同一件事"。

#### 三、因此本项目的对外说法有一个固定形状

**在 2.8k token 上，我们比所有已发表系统都省，用 `deepseek-chat` 答对 55%。** 它们的 90–95% 是另一个
答案模型、另一个 judge、其中一行还换了题集。所以：

- 对 Contextier / Mem0 / Zep / Hindsight 的任何比较，等级是 **C**，**不得**说"我们落后 X"；
- 唯一 A 级横比需要自己跑竞品（H1），而它至今没有完成；
- 唯一 B 级参照是论文自己的"GPT-4o 读完整 115k 历史 = 60.6%"，因为**在同一 reader 下**我们读到
  33k 上 69.2%、2.8k 上 55.0%。

**最后那条是本项目目前最诚实的一句进度陈述**：用十分之一的上下文接近全上下文基线，
用百分之一（2.8k vs 115k 是 2.4%）超过它 8.6 个点——但仍是同一个弱 reader，所以它说明的是
"记忆层有效"，不是"系统领先"。


### 5.6.5 设计（第 44 步）：把"回想漏了什么"换成"逐行判定"

#### 一、上一轮留下的另一半预测

第 43 步的预注册把两个机制按**候选从哪来**分开，并只测了其中一个：

| 机制 | 候选来源 | 第 43 步的读数 |
|---|---|---|
| `dispatch2`（子句） | 遍历检索到的块 | **MR +17 / +16 题** |
| `enableAggregationCritique`（第二遍批判） | 问模型"你第一遍漏了什么" | 未测；且它是**又一次枚举** |

*Judging ≠ Enumerating*（arXiv 2608.01000）给了这一半一个明确的机制解释：模型被要求产出完整清单时会
**静默遗漏**——写几项就觉得写完了；而把同样的项**逐条**递过去问"这个算吗"，约 90% 会被确认。
所以修法不是"把'你漏了什么'问得更好"，而是**不问那个问题**。

#### 二、`per-item` 做的事

```
把上下文每一非空行编号 [1]..[n]
要求模型对每个编号输出恰好一行判定：
    <n>: COUNT       这一行陈述了问题所计的一项
    <n>: NOT-COUNT   没有
    <n>: DUP-OF <m>  它与第 m 行是同一项
然后两行汇总，且明确声明"从你刚写的判定导出"：
    MISSED: <标记为 COUNT 但草稿清单里没有的行号>
    EXTRA:  <草稿里有、但背后没有 COUNT 行的条目>
```

三个性质，顺序重要：

| 性质 | 为什么重要 |
|---|---|
| **覆盖可判定** | 少一个行号就是格式错误。"我没发现遗漏"则完全无法判定——这正是 recall 版可以静默失败的机制 |
| **合并项变成两条判定** | 已测得的 MR 失效是"归还旧物 + 取走新物被算成一项"；逐行判定会把两行都标 COUNT，汇总再报该草稿条目为 EXTRA |
| **汇总是对已写清单的算术** | 与 `dispatch2` 同一条原则，也是本项目反复重新发现的那条：**指名产出物的提示词移动题数，要求勤勉的不移动** |

`recall` 保持默认且保持可达，因为两者之差就是实验本身。

#### 三、四条接线纪律

| 纪律 | 做法 | 挡的失效 |
|---|---|---|
| 开关与模式分开记录 | `featureConfig.aggregationCritique` 与 `.aggregationCritiquePerItem` 两态都写 | 两个产物只差在一个各自省略的键上，无法归因（§20 已记过一次） |
| 模式只随开关转发 | 开关关时**不转发**模式 | 一个"配置了但不生效"的值，正是本项目反复抓的形状 |
| 字符串解析严格 | `parseCritiqueMode` 对未识别值**抛错**，不默认 | 工作流输入里的一个 typo 会产出"产物写 per-item、prompt 是 recall"的运行 |
| 解析函数放 `src/**` | 不放 CLI | `bench/**` 不在覆盖率内，写在那里的比较无法被任何测试覆盖 |

#### 四、可观测量的选择，以及一次差点写错的断言

接线测试的可观测量是**模型调用次数**而不是配置字段——一个转发给"系统其实不读"的选项同样会设置字段，
那正是 B7 死一轮的形状。

但 `per-item` 的 no-op 路径（批判返回 "Nothing to add" 时不应重问）**不能用调用次数断言**：
这条路径在回答前还有一次 query-expansion 调用，计数会差一。第一版测试断言 `prompts.length === 2`、
实测 3，这个错误本身是有价值的——它说明那条链上除了"回答 + 批判"还有一个我先没数进去的调用。
改成断言 revision prompt 不出现，直接测"no-op 是什么"而不是"no-op 值多少"。

#### 五、预注册：两条可证伪的预测

两次 500 题运行，同 reader、同 judge，只差模式：

| 臂 | 预测 | 什么会推翻它 |
|---|---|---|
| `recall` vs 出荷配置 | **MR 基本不动**——批判继承了它要修的枚举失效 | MR 移动 ≥10 题 |
| `per-item` vs `recall` | **MR 向 `per-item` 移动** | `per-item` 与 `recall` 持平或更差 |

两条都要越过第 43 步测得的噪声地板：**121 题的列在 prompt 完全不变时可摆约 10 题（7.9pp）**。
低于它的差不称差，且两条都会做同题配对检验，不靠总分。

**这两条预测至今未被检验，但位置是对的。** 最初的判断是"批判是 `cortex-memory` 的机制，所以两次
运行跑错了系统"——读代码否定了它：

```
$ rg -c critique packages/cortex-memory/src/memory.ts \
                     packages/cortex-eval/src/natural-language-memory.ts
packages/cortex-eval/src/natural-language-memory.ts:52
```

`memory.ts` 一个都没有。`enableAggregationCritique` / `critiqueAggregationLedger` /
`aggregationCritiqueMode` **只存在于参考管线**，所以 `benchmark.yml` 是能测它的**唯一** workflow，
§9.47 的两次运行位置正确。它们缺的不是位置而是**可观测性**：两次运行早于 `critiqueStats` 落地，
所以"两臂逐位相同"仍然无法区分为"从未到达 / 到达但没发现 / 到达但改了没影响答案"。
**这个实验需要的是一次带计数器的重跑，不是搬场**（§5.6.6.5 第 3 条）。

---

### 5.6.6 测量（第 45 步）：数字的身份必须写在数字里

#### 5.6.6.1 缺陷：一个仓库里的两个同名产物

`benchmark.yml` 与 `benchmark-cortex-memory.yml` 都在 `longmemeval` 上跑 500 题、
都用官方分题型 judge、都写一份 Markdown 报告，而**报告的标题逐字相同**：

```
# Cortex Benchmark Report
- Dataset: `longmemeval` (500 questions)
- Feature: `nl-abstain-feature` vs baseline `nl-naive-baseline`   ← 43.80%
```

```
# Cortex Benchmark Report
- Dataset: `longmemeval` (500 questions)
- Feature: `cortex-memory` vs baseline `reference-pipeline`        ← 80.80%
```

两个系统的差别不是提示词，是**证据选择**：

| | `benchmark.yml` | `benchmark-cortex-memory.yml` |
|---|---|---|
| 检索 | `retrieveTopKByQueriesHybrid`，`topK` 15 | 全 haystack 建索引，`relevanceTopK=256` |
| 证据室 | 产品默认 24,000 字符（对检索结果施加） | `maxPromptChars=48000`（对 256 宽池施加） |
| 角色过滤 | 无 | `user`（`multi-session,temporal`） |
| 轮次截断 | 无 | 400 字符（同上两条路由） |
| ask | `abstention-evidence-blocks` | `enumerated` |

于是同一个能力在两边的方向相反，而这是配置的直接后果：IE/KU 的答案是一句只出现一次的话，
15 轮检索必须把它排到第一（`40378588466` 的 379 条单会话记录上，gold 的区分词出现在交付上下文里的
比例是 **IE 38.0% / KU 22.5%**，而 **TR 79.5% / ABS 93.3%**）；MR 需要的是跨会话的**广度**，
参考管线按**会话**检索、逐会话截断、枚举，正好是 MR 的 ask 奖励的形状（84.30% 对 69.42%）。

#### 5.6.6.2 为什么这不是"更谨慎"能修的

那次误读的代价是一整轮：`benchmark.yml` 的 44.2% 被拿去与 `benchmark-cortex-memory.yml` 的 81.0%
比较，于是"端到端基线不可复现"成了一个 P0，随后做了数据集哈希、embedding 确定性检查、
12 MB 日志的 379 条逐题分析，并排除了四项技术原因。**每一项都正确，每一项回答的都是另一个系统的
问题。** 而决定性证据（`40088479628` 一次调用同时测两者：43.40% 对 80.80%，McNemar `p=1.694e-33`）
已经躺在磁盘上。

根因不是疏忽：报告里 `- Feature: … vs baseline …` 一直存在，就在准确率上方五行。**被引用的从来
不是那一行，而是标题和 `- 指标: 值`。** 一个五行的距离，就是身份丢失的全部距离。

#### 5.6.6.3 设计约束：身份写在数字里

| 位置 | 约束 | 为什么是这里 |
|---|---|---|
| 标题 | `# Cortex Benchmark Report — \`<feature>\`` | 目录、截图、粘贴的第一行 |
| 抬头 | `- System under test: \`<feature>\` vs baseline \`<baseline>\`` | 在所有数字之前，截图自带说明 |
| 可引用行 | `- Overall accuracy (\`<feature>\`): 80.80%` | **数字被单独摘走时唯一的载体** |
| 分节标题 | `## Per-capability breakdown (\`<feature>\` arm)` | 表格被整段引用时不丢身份 |

四条里只有第三条是不可省的。前三条是冗余，第四条是排版；第三条是**唯一在"只复制那一行"时仍然
有效的**保证。

判据写成三条断言，后两条比第一条重要：

1. 标题含臂名，且 `System under test` 行出现在任何数字之前；
2. **不存在**没有臂名的 `- Overall accuracy` / `- Abstention` 行（否定性质——一个只在某处写了臂名
   的渲染器仍然允许这种抽取）；
3. **两个不同的 feature 臂必须产出两个不同的标题**（配对性质——它使这次事故在结构上不可能重现）。

#### 5.6.6.4 同一原则在别处的两处应用

**验收矩阵**：`S1`–`S5` 与 `R1` 全部是 `cortex-memory` 臂的读数，页面上现在直接写出这一点，
并写明 `benchmark.yml` 的 43.40% 不得替代它们。

**阅读阶段 §4 的撤回**：`MEASURE-READING-STAGE.md` §4 曾把 81.0% 归给 `NaturalLanguageMemory`，
并据此把"适配器 60.0% 对 81.0%"的 21 点差距分解成查询扩展、重排、弃答恢复、生产提示词四项。
那四项读的是 `natural-language-memory.ts`——**43.40% 那个系统**的机器。**21 点是真的，它的分解不是**；
重新分解是新增待办，不是已完成的结论。

#### 5.6.6.5 遗留

1. **21 点差距需要重新分解**，对象是 `cortex-memory` 与最小适配器之间，而不是参考管线与它之间；
2. **MR 69.42% 是本仓唯一"已知有更好的答案"的能力**：同一 run 里参考管线 84.30%
   （`p = 2.935e-3`）。`PREREGISTRATION-CORTEX-MEMORY-ARM.md` §13.105 已为此注册六条预测；
3. **批判实验要带计数器重跑**（`benchmark.yml`，`aggregation_critique=1` 两臂 `recall` /
   `per-item`，500 题）。位置本来就对——批判只在参考管线里；缺的是把"两臂逐位相同"分成
   "从未到达 / 到达但没发现 / 到达但改了没影响答案"的那三个数。不重跑，§5.6.5 的两条预测
   既不算通过也不算推翻。

---

### 5.6.7 设计（第 45 步续）：缓存必须能说出自己是谁

#### 5.6.7.1 缺陷的形状：一句宣称了不存在性质的注释

`deserializeEmbeddingCache` 的 docstring 写着 "throws on a corrupt or incompatible buffer **so a
stale cache is never silently trusted**"，而它校验的是 `magic` 与 `version`。**两者都不记录后端**，
所以同宽度的两个模型在它眼里逐字节相同 —— 而宽度恰恰是 workflow 配置的东西。

`retrieval.ts` 写的头部：

```
magic(4) + version(1) + count(4) + dim(4)
```

四个字段里没有一个是"这些向量是谁算的"。**"兼容"被实现成了"格式对得上"，而读者需要的是"模型对得上"。**

#### 5.6.7.2 为什么这是测量缺陷，而不是缓存 bug

两个 benchmark workflow 的 Actions 缓存键是 `longmemeval-embedding-<语料哈希>-`。
**只要语料不变，一次运行就继承上一次运行的 haystack 向量，而查询向量每次都现算。**
后端一旦在两次之间移动（模型 id、endpoint、离线 `hash` 回退、同名模型背后的归一化），
读者就是在用新空间的查询检索旧空间。

**而这个状态里每一个计数器都是健康的**：

| 计数器 | 为什么它看不见 |
|---|---|
| `determinism max abs diff 0` | 它在**同一进程内**把同一段文本嵌两次再比。模型变了，两次都变，差仍是 0 |
| `returnedDimensions 1024` | 异构同宽模型照样通过 |
| `Restored N embedding vectors` | N 是条目数，不是关于来源的断言 |
| 分能力准确率 | 它是待解释的对象，不是识别原因的量 |

一个缺陷如果让所有诊断量同时保持正常，它就不属于缓存层，属于测量层。

#### 5.6.7.3 设计：身份写进字节，而不是写进文件名

| 决策 | 选择 | 理由 |
|---|---|---|
| 身份放哪 | **文件里**（v2 头部的 provenance 块） | 文件名带不动：`EMBEDDING_CACHE_PATH` 是 workflow 给的一个字符串，两个入口都不按模型拼它 |
| 写什么 | `{provider, model, baseUrl, dimensions}` | **产物里早就在印的四个字段**，没有发明新东西；`EmbeddingProvenance` 这个类型已经存在 |
| 比几个字段 | **全部四个**，错误里列出每一个差异 | 只比 `dimensions` 会放过六种差异里的五种，而那正是旧实现的错法 |
| 与 payload 互校吗 | **是** | 否则"把头部改成与调用方相同"就能让一个宽度不符的 payload 变得可读 |
| 写入端也断言吗 | **是** | 调用方的错误应当在写的时候带着两个数字失败，而不是一个进程之后变成 `Could not restore` |
| v1 怎么办 | **拒绝，不迁移** | 它只有 magic/version/count/dim，凭它没有任何证据判断来源；"假定就是现在这个"会在迁移处复制缺陷 |

**失败路径上的可解析性是设计的一部分。** 两个入口在 `main().catch(...)` 里也要持久化缓存——
一次在第 300 题死掉的运行仍然付过嵌入的钱。而那个作用域拿不到工厂的返回值，所以
`resolveEmbeddingProvenance(env)` 被拆成一个**纯函数导出**：它是环境的函数，不需要模型对象，
也不会因为凭据缺失而抛错（失败路径可能**正因为**凭据有问题才走到）。工厂改为调用它，
测试断言的是**四个环境上的等价性**而不是第二份规则的手写期望——第二份拷贝会通过自己的测试，
而它盖在缓存上的身份是错的。

#### 5.6.7.4 判据

13 条断言，第一条是**对照**（同 provenance 往返成功）——一个把可用路径改坏的"修复"与没有修复
无法区分。其余逐条覆盖差异的每一种，加上两条落在 `restoreArmEmbeddingCache` 层的：另一个模型写下
的文件恢复 **0** 并把每条 turn 推回 provider；只有 endpoint 不同时同样如此。

一条测试自身的教训值得留下：对照用例第一版断言了十进制字面量（`0.3`）并失败——格式存 float32、
读者展宽到 float64，**往返在 float32 下精确、在十进制字面量下不精确**。改成两边都过 `Math.fround`
再比，因为断言字面量等于钉住一个格式并不声称的精度。

#### 5.6.7.5 它不解释什么

**不解释 81.0% → 44.2%**（那是两个系统，§5.6.6）。它对"`benchmark.yml` 自己从 9 月 430/500
到 10 月 221/500"这个**配置未经证明相同**的观测是一个候选，判读方式是下一次 dispatch 的
`Restored 0 embedding vectors` 之后准确率是否向 86% 回归。缓存改动能做的最好的事，是让这个机制
**从"可以静默存活"变成"可以观测"**，而不是替它下结论。

---

### 5.6.8 设计（第 47 步）：预注册的前提本身就是一条断言

#### 5.6.8.1 事件：一个 P0 在被调度之前就死了

`cortex/docs/PREREG-DATE-FRAME.md` 是一个排到 P0 的实验，声称为 temporal 与 multi-session 两条
路由"加上日期框架"，因为它断言：

> **What the reader is told today / Nothing.** `prompt.ts` carries no statement of the
> conversation's date.

**这句话是假的，而且写的时候就是假的。** 把两条 prompt 渲染出来即可看到：

```
$ buildPrompt(q, [datedTurn], 'temporal', {questionDate:'2023/06/02'})

EVIDENCE:
1. [2023/05/20] user: I ran ten kilometres today.

QUESTION: How far did I run last month?

Answer the question using only the evidence above.
The question was asked on 2023/06/02. Resolve every relative expression ("last week", "two months
ago") against that date.
```

外部那篇工作给日期框架的定义是 **"当前日期写进消息 + 每个内容块自带日期"**，而这两半都在：
锚点句在，`[2023/05/20]` 前缀作为 `turn.content` 的一部分在**每一条路由**上都在。

| 路由 | 锚点句 | 每轮日期 |
|---|---|---|
| `temporal` | **在**（数据集给了 `question_date` 时） | 在 |
| flat（`abstention-evidence-blocks`） | 不在（`buildPrompt` 对非 temporal 丢弃 `questionDate`） | 在 |
| `multi-session` | 不在（`buildSessionPrompt` 根本没有日期参数） | 在 |

**处理组对一条已经收到该处理的路由不产生效应。** 而 P1、P2 都指向 temporal。

#### 5.6.8.2 代价，以及为什么撤回比跑完更值

| 如果跑 | 实际做的 |
|---|---|
| 一次 500 题 dispatch、约 55 分钟 runner | 两次 `buildPrompt` 调用 + 5 条断言 + 一次读 `prompt.ts` |

更值的是结论本身：**外部的 +9.3 不是我们还没拿到的增益，而是已经计入 74.02% 的东西。**
如果那套系统靠日期框架从 80.7 走到 90.0，而我们的 temporal 路由一直带着它却只有 74.02，
那么**日期框架不是 TR 的杠杆**。这是 P1 的"不达标即回退"条款早就写好的结论，只是用 0 次
dispatch 而不是 1 次拿到。

#### 5.6.8.3 设计约束：前提必须在 dispatch 之前被检查

| 检查 | 做在什么时候 | 为什么 |
|---|---|---|
| 机制所在的**包/文件**是否存在该符号 | 写预注册时（`rg -c <symbol>`） | 第 45 步的教训：把机制归错了包 |
| 该机制**是否已经在跑** | 写预注册时（渲染一次真实 prompt） | 本节的教训：把已安装的东西当缺失 |
| 对照组是否**有 headroom** | 写预注册时 | `entityIdentityClause` 的 +3 在一个 30/30 饱和列上无法复现 |
| 差值是否**越过该列噪声** | 读结果之前 | 127 题列可摆 10 题（7.9pp）；500 题总分四次重复跨 15 题 |

四条里前三条的成本都是"一条命令"级别。**把它们写成表格而不是写成原则，是因为原则这一轮已经
失效过一次。**

#### 5.6.8.4 同一轮的第二个产物：失败分解该记录什么

`MEASURE-SOTA-FAILURES.md` 从 `40088479628` 的逐题记录做出了分解。它同时暴露了**产物缺什么**，
两条都影响"下一次能不能少跑一轮"：

| 缺的字段 | 它挡住了什么 | 成本 |
|---|---|---|
| 基线臂的逐题记录（现在只有聚合） | "两个臂在**同一题**上为什么不同"——配对检验只给 p 值，不给原因 | 一个数组、0 次模型调用；但产物已是 50 MB |
| 每轮**渲染后**的字符数（只有 `evidenceChars` 与 `carried`） | "截断切掉了答案"只能推断，不能计数 | 一个字段 |

第二条尤其值得单独说明：`goldOverlap.carried` 是对 `assembled.carried` 算的，也就是**渲染进
prompt 的集合**，这一点是对的；但进入 prompt 时每轮要过 400 字符上限，而"答案被上限切掉"
没有字段可查。本轮用字符偏移间接量了：MR 只有 4 题、TR 0 题的答案句起点在 400 之后——**所以
上限不是原因，但这个结论是靠推断拿到的，不是靠计数。** 这与本仓已经修掉的两个仪器缺陷同形
（报告不写自己测的是哪个系统；缓存不写自己是哪个模型）。

#### 5.6.8.5 判据

| 断言 | 排除的是 |
|---|---|
| temporal 渲染锚点句与"resolve every relative expression" | 一个"加了日期"却没说怎么用的改动 |
| 每轮 `[date]` 前缀在证据块里 | 一个把日期当成 route 参数、从而丢掉块日期的改动 |
| 数据集没给日期时**不**渲染锚点 | 一个发明参考日期的降级路径 |
| flat 即使收到 `questionDate` 也不渲染锚点 | 路由泄漏（这是选项文档写明的性质） |
| multi-session 不渲染锚点 | 把"唯一真缺锚点的路由"说成"都有了" |

五条全部由 `cortex` 的 `date-frame-presence.test.ts` 钉住，**包括两条否定性质**——因为被撤回的
是一个关于"代码渲染了什么"的断言，只有否定性质能防止它再次出现。

---

### 5.6.9 设计（第 47 步续）：一个形状在被判分处最优，就会在不被判分处泛滥

#### 5.6.9.1 观测

把 45 次错误拒答里的 token 剥掉再量剩余内容，得到的是一个形状而不是四十五个理由：

| 能力 | 拒答 | 裸 token（≤40 字符剩余） | 该路由有恢复通道 |
|---|---|---|---|
| IE | 12 | **12** | 无 |
| KU | 2 | 0 | 无 |
| MR | 10 | **9** | **有** |
| TR | 21 | **9** | 无 |
| **ABS**（拒答即正确） | **30** | **29** | 无 |

`ABS` 的 30/30 与它 29 个裸 token 是同一件事：**这是合同奖励的答案形状。** 而在四条"gold 从不是
拒答"的能力上，同一形状制造了 30 个失败。

#### 5.6.9.2 为什么"再写一遍禁令"不是修法

`enumerated` ask 里已经有这句话：

> Do not reply `INSUFFICIENT_EVIDENCE` without first writing the Step 1 list: **a bare
> `INSUFFICIENT_EVIDENCE` with no list is not a valid response.**

它被违反 **21 次**（IE 12 + TR 9，两条从不重试的路由）。这不是措辞不够强，而是**这句话没有机械
后果**：解析层接受裸 token 为一个合法答案，于是禁令只是一句建议。本仓在提示词层面的全部经验都指向
同一句：**只提建议的提示词无效，要求写下中间产物的有效**——而"要求"之所以有效，是因为产物可以被
解析层检验。

#### 5.6.9.3 设计：把形状错误当成可重试的状态，而不是新的措辞

| 决策 | 选择 | 理由 |
|---|---|---|
| 判在哪一层 | **解析层**（`parse.ts` 的形状判定），不是提示词 | 只有能被机械检验的东西才构成约束 |
| 判据 | 在"gold 从不是拒答"的四条路由上，`INSUFFICIENT_EVIDENCE` 前面必须有一个可解析的列表 | 这就是 ask 已经写明的那条；区别是它现在有后果 |
| 后果 | **一次**纠正调用，与已有 `reviewPass` 同族 | 本仓已有先例：形状错就重问一次，而不是重发窗口 |
| 为什么不是 `planAbstentionRecovery` | 那个通道**构造上需要一个列表去引用**，对裸 token 天然失明；而且它的九次重试**本身也是裸的**（`attempted 10, answered 1` 与 MR 九次裸拒答精确对齐） | 复用它会得到一个"看不见目标"的修复 |
| 作用域 | 四条路由，`ABS` 明确排除 | `ABS` 的裸 token 是正确答案，改它就是改对一个正确行为 |

#### 5.6.9.4 这条与 5.6.8 的关系

5.6.8 讲的是**前提没被检查**；这一条讲的是**约束没被执行**。两者共同的上位原则只有一句：
**一个只会被读取、不会被执行的断言，在工程上等于不存在。** 前者被写进了预注册，后者被写进了
提示词——都是"写了就算"的地方。

#### 5.6.9.5 判据（未实施，先注册）

群体 **30**（21 次首答 + 9 次重试），上限 **+30**，是本轮所有候选里最大的一群。判据必须是
**配对不一致数**而不是总分：本臂四次真实重复跨 **15 题**（397–412），+3 与 +5 都淹没在里面。

| 预测 | 内容 | 推翻条件 |
|---|---|---|
| P1 | 机制：产物新增的 `bareDeclines` 计数器在四条路由上的读数由 21 降到个位数 | 计数不降 |
| P2 | IE 与 TR 的拒答数合计至少减 8 | 减 < 5 |
| P3 | `ABS` 仍为 30/30 | 任何下降 |
| P4 | 新增的纠正调用小于 40 次（群体 30，加少量误判） | 超过 80 次说明判据过宽 |

**本轮只注册，不实施**：`40498191604` 正在 multi-session 上测另一个干预，两个改动落进同一个读数
就无法归因。

---

### 5.7 实现（第 10 步）：接线 —— 三个缺陷只在整条链跑起来时出现

前三层（写侧、卡片、提议）各有测试，各自都是对的。把它们按真实顺序接起来之后，一次运行就暴露
了三件事，**没有一件能被任何单层的测试看见**：

| # | 缺陷 | 怎么暴露的 | 修法 |
|---|---|---|---|
| 1 | **一个引擎装不下两个库** | 会话最初只收一个 `Storage`，指望表前缀把两半分住。`FederatedStorage` 把前缀当**路由标记**剥掉，于是两半都写进同一张 `facts` 表；第一次共享查询就把私有行带了出来，`ReadSideAssembler` 当场抛 `ScopeViolation` 并点名 key | `DisclosureSession` 要求**两个** `Storage`（两个文件）；`03` 的"物理分离"由此从设计句变成类型约束 |
| 2 | **`./local` 没有生成能力** | 想用真模型跑通链路时才发现：离线入口能嵌入、能重排、能回答，**唯独不能提议**。第 9 步引入了一个只吃模型的组件，而"离线"那条入口产不出模型 | 新增 `createLocalLLM`（`./local`），与嵌入路径共用 `preparePipeline`，同一个 `dtype` 钉法 |
| 3 | **审计面丢掉了原句** | 发布原子之后，卡片 `text` 被改写、私有行被 `promote` 删掉，**没有任何地方记录"他原本说了什么"**。而导出正是本产品唯一的审计面 | `KnowledgeCard.sourceText`：开卡时写入、永不改写；导出在措辞变化时多一列 `source` |

第 3 条值得多说一句：它是**跑出来的**，不是读出来的。代码每一行都对——`edit()` 改用词、
`promote()` 搬行、`toMarkdown()` 打印卡片——三处合起来才产生"原句不存在了"。

#### 会话：顺序是一个属性，不是一处约定

```ts
const session = new DisclosureSession({ private: privateDb, shared: sharedDb, proposer });
const { admission, card } = await session.say('I moved to Berlin in March and now I work at Acme.');
const proposed = await session.propose(card.id);        // 只挂到卡片上，不发布
const published = await session.accept(card.id, { atom: 0 });   // 走 edit()，规则再判一次
const rows = await session.evidence('shared');          // 一个共享任务能读到什么
```

五条被这个对象固定下来的规则：先存再问；提议是内容不是同意；发布原子走 `edit`（因此点击那一刻
规则复判）；失败**返回**而不是吞掉；共享窗口只读共享库。

#### 一次真实运行（`tools/triage-demo.mjs`，每次命令一个进程）

```
$ say 'My password is hunter2, and the wifi code is on the fridge.'
withheld by credential: credentials are never stored, not even as a card
not stored anywhere, and no card exists for it.

$ say 'The project plan moves to Thursday, and the client gets the roadmap on Friday.'
c3  stored shared  (rule: org-knowledge)
no question: the rules already answered it.

$ propose c4 --llm local
    offered (triage-proposer/v2, onnx-community/Qwen2.5-0.5B-Instruct):
      [0] I've been really enjoying editing my photos in Lightroom
      [1] the online communities I've joined have been super helpful
      [2] learning new techniques and getting feedback on my work.

$ accept c4 --atom 0
c4  edited  published: I've been really enjoying editing my photos in Lightroom

$ ask shared
2 row(s) visible to a shared task
  c3  [shared]  The project plan moves to Thursday, and the client gets the roadmap on Friday.
  c4  [shared]  I've been really enjoying editing my photos in Lightroom
```

**这四行合起来就是产品承诺**：凭证不存在于任何库；规则已裁决的句子不问人；模型拆出的三条里
只有被点的那一条过去；而共享任务看到的正是那一条，不是整段。

#### 它买不到什么

| 边界 | 现状 |
|---|---|
| 图形界面 | 没有。`tools/triage-demo.mjs` 是**演示**，不是产品面；它自己也没有单测（覆盖的是它调用的会话） |
| 提议质量 | 仍是模型的事，且 0.5B 在这句话上只拆了一条（c1）——同一模型在另一句上拆了三条，**不稳定本身就是读数** |
| `--llm openai` 路径 | 需要 key，本机未跑；只验证了"缺环境变量时报错并说明"这条 |
| 共享侧的可达性 | 4/8（`[POC-5]`）没有变；接线不改变可达率，只让它可被操作 |

---

### 5.8 实现（第 23 步）：拒答闸门 —— 一条承诺，一个检查

#### 契约说了什么，代码信了什么

`enumerated` 契约的最后一句：

> Reply `INSUFFICIENT_EVIDENCE` only when the Step 1 list is empty. If it has at least one item,
> Step 2 must state the number computed from it.

`memory.ts` 的二次通过跳过一个拒答，理由是：

> an abstention is a decision, and this pass audits a list that does not exist.

这两句不能同时为真。**第二句从未被数过**，而它决定了 13–17 道题：

| run | MR 拒答 | 清单非空 | TR 拒答 | 清单非空 | ABS 拒答 | 清单非空 |
|---|---|---|---|---|---|---|
| `39367801501` | 10 | **10** | 20 | 7 | 30 | **0** |
| `39509698041` | 9 | **9** | 15 | 5 | 30 | **0** |
| `39699987781` | 9 | **9** | 23 | 4 | 29 | **0** |

ABS 那一列是这条读数的**对照组**：ABS 的正确答案就是拒答，而它不产生清单，所以一条关于清单的
规则结构上碰不到它。一个会改 ABS 的拒答 pass 是在回答"我不知道"才是正确答案的题。

#### 四态，不是布尔

`abstention-recovery.ts` 把"要不要再问一次"拆成四个可区分状态：

| 状态 | 含义 | 后果 |
|---|---|---|
| `disabled` | 这次运行没有要求 | 不改行为（默认） |
| `answered` | 读者答了 | 不碰——**已答对的题不可能被移动** |
| `no-list` | 拒答是诚实的，清单为空 | 不碰——这正是契约允许的状态 |
| `retry` | 拒答与自己的清单矛盾 | 再问一次 |

`answered` 这道守卫需要一条**特定的夹具**才能测到：模型既列清单又作答。用"裸答案"去测它，
`declinedItems` 本来就返回空，守卫写死成 `false` 测试也全绿——第一次注入就是这样存活的。

#### 二次询问为什么不重送证据

清单是读者自己的抽取。对计数题，清单长度**就是**答案，所以把清单引回去是对"读者认为哪些相关"
的完整重述，而不是一个新的提问。重送 48k 窗口会把它变成**第二次采样**——而 §13.100.2 已经量过
第二次采样会改掉 24/121 个 MR 答案。**纠正和重掷是两种治疗，只有前者能归因。**

仍然允许再拒：清单非空也可能什么都答不出（`d905b33f` 列了一条书的信息，并说明全书没有折扣数字）。
所以"清单长度即答案"只对计数题加，因为只有那里它不是猜测。

#### 为什么它是 `ReviewPass` 的一个取值，而不是一个新开关

第一版做成独立字段，仓库自己的守卫生效了：任何 workflow 都不许用满 `workflow_dispatch` 的 25 个
输入（"要拆工作流，不要删旋钮"）。于是改成 `ReviewPass = 'none' | 'audit' | 'recover'`——这个类型
从写下来那天就是为这件事准备的（"a second pass with a different question"）。它还表达了一件对的
事：`audit` 重问每一道已答的题，`recover` 只重问带着清单拒答的那一批，**两者是两种治疗，不是两个
旋钮**，所以它们是同一个字段的互斥取值。

#### 两条接线上的决定

1. **证据按"答案来自哪个提示"记录**。恢复提示不含 EVIDENCE 块，它引用的清单来自第一份提示，
   所以记录第一份——否则这道题在产物里会显示成"没有任何上下文却答对了"（run `38142407062`
   就是这个形状）。
2. **计数与 `abstentionReasons` 分开**。那个普查的语义是"一题一次"，四个路由是所有历史产物被
   读解的坐标；把重试折进去要么重复计一题，要么把重试藏起来。`recoveryCensus()` 报
   `attempted` / `answered`，是**关于治疗的数**，不是关于题的数。

#### 目标校准（同一轮）

公开读数（2026-10，厂商自报，口径不一，并列不归一）：Mem0 93.4% / Contextier 91.6%（2,807 tokens）/
Zep 90.2%；**Cortex 81.0%**。分能力：**KU 86.8% 已在其上**（85.9%），赤字全在 MR（69.6% vs 90.2%）
与 TR（74.6% vs 91.0%）。对标 224/500 的内部参考管线，是这个项目前二十二步最大的一个错误——
**基准错了，改善就没有方向**。

### 5.6.10 设计（第 49 步）：一个机制"配置了"与"触发了"在准确率里长得一样

#### 5.6.10.1 观测

`reviewPass: 'bare'` 跑满 500 题（run `40522788515`），读数 **80.80%**——与控制组 `39509698041`
**逐题相同**。产物里写着 `reviewPass=bare`，也就是说：**它记录了配置，没有记录事件。**

这个"相同"有两种完全相反的读法：

| 读法 | 下一步 |
|---|---|
| 机制触发了 21 次，一次也没救回 | 这条通道在当前提示词下无效，撤回 |
| 机制一次也没触发 | 接线断了，修接线 |

在没有计数器的情况下这两句话**不可区分**，而它们指向相反的行动。这不是"缺少可观测性"这种泛泛
之谈——它是**一个已经花了约 40 分钟 runner 时间的实验，无法给出结论**。

#### 5.6.10.2 设计：普查是可选能力，缺席与零必须可区分

沿用 `recoveryCensus()` 已经确立的三条决策，不发明新规则：

| 决策 | 处理 | 理由 |
|---|---|---|
| 系统没有这个访问器 | 报告里**不出现**该字段，也不出现该段 | 「这个构建不带这条通道」与「带了、触发零次」是两句不同的话 |
| 访问器抛异常 | 当作缺席，不失败整轮 | 可选能力坏掉不该毁掉一次已经花掉的测量 |
| 载荷不是两个非负整数 | 丢弃，不强制转换 | `NaN` 在表格里渲染成一个观测值 |

前两条的区分是本节的全部要点：`attempted: 0` 是一个**断言**（通道存在、种群为空），
字段缺席是另一个断言（通道不存在）。把两者合并成零，就回到了 5.6.6 那个"数字没有身份"的错误。

#### 5.6.10.3 为什么是独立字段而不是并进 `recovery`

两者的作用对象不同：`recovery` 处理"拒答与自己的证据清单矛盾"，`bareRetry` 处理"答案只有 token、
没有别的"。一个系统可以带其中一个、两个、或都不带。合并会允许一个读者把一次转换记到没有产生它的
那条治疗上——这正是 5.6.6 要防的那类错误，只是换成治疗而不是系统。

因此产物多一个段、JSON 多一个字段、渲染多一个脚注说明两处排除：**ABS 路由在代码里被排除**
（它的 gold 就是拒答，重试只会花一次调用把正确答案改成错误答案），**一次就答对的问题从不进入**
（所以 `attempted` 的上界是拒答数而不是题数）。

#### 5.6.10.4 协议侧同一课：三个判词不够，需要第四个

把竞品接上同一套管线后（run `40519523383`），mem0 印出 `0.0%` 与 `100 refusal(s), 0 empty result(s)`。
真因是向量库维度从未被声明（FAISS 默认 1536，嵌入器 1024），`add` 全面失败被 driver 记成
`skipped`，而**没有任何渲染读它**；库为空 → 每次 `search` 抛同一断言 → 被记成"拒答"。

协议原本有三个判词：运行失败 / 系统拒答 / 什么都没找到。缺的是第四个：**语料没进库**。
它与第三个的差别是全部要点——"检索不到"是关于系统的断言，"没东西可检索"是关于我的仪器的断言。

三处修复，每处一条无 key 可复跑的测试：

1. driver 把 `embedding_model_dims` 传给向量库，嵌入器未声明宽度时**拒绝猜**；
2. 进库为零 = **比较失败**，driver 判一次、协议层再判一次（规则属于所有 driver，不属于记得实现它的那些）；
3. 报告在计数非零时打印 `ingest: N of M session(s) stored, K refused` 与原因。

#### 5.6.10.5 上位原则

5.6.8 说"前提要被检查"，5.6.9 说"约束要被执行"，这一节说**治疗要被计数**。三者是同一句话的三层：
**任何只在文档里存在、在数据里不留痕的东西，在工程上等于不存在。** 提示词、预注册、开关、
以及"我跑过这个实验"——都属于这一类。

### 5.6.11 设计（第 50 步续）：S-1 时间信号，以及计划被实现改掉的三个地方

#### 5.6.11.1 计划写的是分桶，实现是衰减

`PLAN-RETRIEVAL-SIGNALS.md` §3 把 S-1 注册为"按距离分桶"。分桶是一个常量加一条 if 链，这也是
它成为首版草图的原因，但它是**不连续**的：相隔 1 天与 2 天同分，29 与 31 不同分。于是两条相隔
三天的 turn 可以跨档交换次序，而两条相隔两天的不能。**一个在桶内稳定、在边界任意的排序，
描述的是自己的阈值而不是语料。**

`0.5 ** (|Δt| / 半衰期)` 是同一件事，一个常量代替一张表，处处单调，且有一个读者已经知道的名字。
半衰期取 30 天，写在实现里而不是配置里，理由是它属于信号的定义而不是运行的选择。

**对称而非有向。** 早于问题与晚于问题同样远。有向衰减会把"越旧越差"和"越远越差"两句话编码进
一个信号，而 LongMemEval 的时间题两个方向都问（"相隔多少天"没有偏好方向）。

#### 5.6.11.2 只对已召回的 turn 加权，因为地板不能漏水

形态选择是**加法**（`cos + w × affinity`）而不是插值，因为 `w = 0` 时它逐字节等于余弦——
归档产物的每一次运行都是在这个状态下产生的，让 0 表示"和以前一样"是单变量实验的前提。

更关键的约束是**作用域**：加权只发生在检索器已经给出的 hit 上。`relevanceFor` 对榜外的 turn 返回
`-2` 这个地板值；若也给地板加 affinity，一条"同日但从未被检索到"的 turn 会压过一条已测量的 turn，
而读数看起来像时间信号在起作用，实际是地板在泄漏。20 条测试里有一条专门钉这件事
（`does not promote a turn it never scored`）。

#### 5.6.11.3 未标日期的 turn 得零分，不是低分

零是"不贡献"，该 turn 停在语义信号放它的位置。低分是对**语料**属性（这条会话没带日期）的惩罚，
而不是对证据属性的惩罚；在任何部分会话无日期的语料上，它会系统性压低所有这些 turn ——
那是一种读起来像发现的抽样偏差。

#### 5.6.11.4 唯一导出，以及为什么这是被普查逼出来的

首版导出了衰减函数、半衰期常量、输入类型三个名字。`export-census.mjs` 把三个全部判为孤儿
（872 / 479 / 393 的计数未变，因为孤儿与新增相抵）。仓库的规则是**一个没有调用者的名字，
是没有任何测试能在它声称的层级上守住的**，而普查把测试引用算作"无调用者"。

因此收敛为单一导出 `temporalBoosts`，衰减通过 `affinityFor` 检验——那是排序真正消费的值——
半衰期则在测试里**重述**而不是 import：一个从实现读取常量的测试，会对它读到的任何值通过。
写出来之后，改实现会让测试变红，这正是契约的作用。

#### 5.6.11.5 census 与"配置了"的区分

`temporal: { scored, total }` 只在权重非零时出现。`scored: 0` 而 population 非空，是
"配置了、一条也没能定位时间"；字段缺席是"这个构建不带这个信号"。这两句话的区分与
5.6.10 的 `bareRetry` 完全同构，规则复用而不重造。

计数在**文本域**（`affinityFor` 的键空间），不在位置域：两条位置一条文本是一个答案，
按位置计数会在 turn 重复的语料上恰好高估它最不该高估的那个量。

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

这条策略在代码里只有一个入口：`TriageWriter.promote(id)`。它被调用一次，就把一行从私有库搬到共享库
（顺序与失败模式见 §5.4.2），并留下 `confirmedAt`。**没有第二条路**：`admit()` 只会往两个方向写，
而 `defer` 与 `private` 都落私有。

推论：拓扑 C/D 的价值不在"自动分流"，而在**把共享变成一次显式授权**；自动分流那部分只适用
于语料里本来就充满组织语言的负载（工作协作），而本仓库还没有那样一份语料 —— 这是 04 §7 的 G2
要的第二样东西。

### 6.4 输出侧：把"顺口说出"变成一次可拒绝的检查

写侧边界成立不等于不泄漏。读者可以在共享任务里引用一条私有事实 —— 它不在窗口里，但模型记得
（权重里、或上一轮上下文里）。这是本设计此前**唯一没有覆盖**的泄漏面。

设计（三层，从便宜到贵，全部复用同一张规则表）：

| 层 | 做什么 | 拒绝方式 | 成本 |
|---|---|---|---|
| O1 草稿扫描 | 把即将发出的回答过一遍 `RULE_TABLE`（与写侧同一张表，所以"该不该存"和"该不该说"用同一套判据）；命中任一 private 规则 → 不给用户看，先要一次确认 | 拒绝发布，附"这一段包含 X" | 纯函数，<1 ms/段 |
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

#### 6.4.1 O1 + O2 已落地（实现第 7 步）

`OutputGuard` 进 `cortex-core`。两条检查，两个各自能说清的承诺：

| 检查 | 判据 | 结论 |
|---|---|---|
| **O1 范围扫描** | 用**写侧同一张表**扫草稿；private 规则命中 → 拦截（`task: 'shared'`） | 60 条上：12 条 gold-private **全部拦下**，已发布事实**零误拦** |
| **O2 归因** | 每条 `[[id]]` 必须落在本次窗口内；共享任务**必须**至少有一条引用 | 未知引用与无引用各自成一条 finding |
| 私有任务 | 自己的事实可以复述（这是产品在工作），但**凭证仍拦** | 草稿会被存、被贴、被日志，都不是"本人" |

**一个让它可用而不烦人的决定：命中可以被"豁免"**。共享任务里合法地引用一条**共享**事实
（包括提到钱的），不应被拦。所以当窗口里有一行 shared 记录，其文本包含被命中的那个**句子**时，
这条 finding 标为 `excusedBy: <id>` 并**保留在报告里** —— 读者有权看到"这句看起来像违规、为什么不是"。

判据用的是**包含关系而非相似度**：会猜的守卫要么放过太多（不再是守卫），要么放过太少（被关掉）。
这一点在 60 条上被量过：已发布的 4 条事实逐条写成草稿，**零误拦**。

**报告的单位是句子，不是命中的词**。`money` 在 "I spent 350 dollars" 上匹配到的是 `spent`，
而"这句话包含：spent"对读者毫无用处。所以 span 会扩展到句子边界（`.` `!` `?` `:`；**换行不算**
—— 草稿按 80 列折行，换行是排版不是语义），再折叠空白、超长截断并标 `…`。

#### 6.4.2 O3 回显（实现第 8 步）：O1 看不见的那 44 条

O1 跑的是规则表，所以它只看得见**规则命中过的**句子——60 条里 12 条。剩下 **44 条是 `defer`**：
没有任何规则有意见，它们靠"默认私有"待在家里；一段草稿复述其中一条，O1 报"干净"。

O3 不需要意见，只需要**行**。机制刻意笨：**字符 n-gram 重叠**（默认 32 字符 ≈ 5 个词），
比对全库私有的每一行。

| 检查 | 看得见的私有行 | 60 条上的读数 |
|---|---|---|
| O1（规则） | 12（规则命中的） | 12/12 拦下 |
| **O3（回显）** | **56（全部私有行）** | **56/56 拦下** |
| 误拦（引用已发布事实） | — | **0/4** |

**为什么用重叠而不是相似度**：embedding 相似度会把"我的卡被拒了"和"我的卡没通过"判成同一句，
而一个对近似句开火的守卫会被关掉。代价写在付出它的地方：**改写抓不到**，并且测试里有一条
**断言它抓不到**（"卡号 4111…" vs "尾号 4444"），这样将来真能抓到时，是这个测试先红。

**三个必要的工程决定**：

1. **白名单先减，再比**：出现在窗口内 shared 行里的 n-gram 会先从私有语料里扣除。这是 O1 豁免
   逻辑在 n-gram 粒度上的同一句话——**先问写侧**。
2. **归一化带位置映射**：草稿按 80 列折行，所以空白先折叠成一个空格再比；`map[i]` 记住每个
   归一化字符来自原文哪里，因此 finding 给出的 span 指向**调用方手里那份草稿**。
3. **大小写不敏感，但位置不敏感于大小写**：`toLowerCase()` 只用于比较用的 gram，不改变文本长度，
   所以位置映射不会被破坏。

**成本是线性的，而且这张表现在有两版读数**（实测，单次扫描，Node 22 x64，同一份合成语料，
每行约 200 字符；`packages/cortex-core/test/echo/run.mjs`，5 次取 p50）：

| 私有行数 | 第 8 步实现（`Set<string>`） | 第 11 步实现（Bloom + 滚动哈希） | 倍数 | 过滤器 |
|---|---|---|---|---|
| 100 | 2.1 ms | **1.6 ms** | 1.3× | 0.1 MB |
| 1,000 | 32 ms | **20 ms** | 1.6× | 1 MB |
| 5,000 | 332 ms | **71 ms** | 4.7× | 4 MB |
| 10,000 | 834 ms | **133 ms** | 6.3× | 8 MB |

**第 8 步那张表（0.94 / 11.1 / 67.5 ms）无法复现，原因很具体**：测它的脚本没有入库，语料也没有
保存，所以那三个数只能当作"某份语料上的读数"，不能与任何其它读数并列。这一版把脚本、语料生成器
和 p50 都放进了仓库，**因此从这一版起，O3 的成本是一个可复现的量**。

**形状仍然是线性的，判据未达成**：10,000 行时一次扫描 133 ms。要真正去掉线性，需要一个**被持有
并被增量维护**的索引；按本步的测量，这样的索引在 5-10k 行上占 **9-18 MB**，而且它的失效方向是
**静默的**（漏一行就漏一条泄漏）。这笔交易被明确记录、明确不采纳（04 §9.14），采纳的是"同一形状
上快 4.7-6.3×"。

三个实现要点，每一个都对应一个可测量的失效：

| 点 | 没有它会怎样 |
|---|---|
| **滚动哈希按 `imul` 循环算幂**，不用 `Math.pow` | `Math.pow(P, 31) >>> 0` 是双精度数低 32 位（尾数早已截断），于是同一个窗口在不同位置得到不同哈希；一切仍是确定性的，`contains` 却对大多数拷贝回答"没有"。原型里这个 bug 活了十分钟，现在是第一条断言 |
| **过滤器只在"可能"上做前置**，命中必须用 `String.includes` 复核 | 布隆过滤器有假阳性；不复核就会**误拦**（0/4 会变成别的数）。复核次数被计数：过滤器质量下降会体现为这个计数器，而不是一次没人解释的变慢 |
| **语料与草稿用同一个归一化** | 一边折叠空白、另一边不折叠，过滤器会把整份语料判成"干净" |

**这一层买不到什么，必须与写侧分开陈述**：改写与概括。"我的卡号是 4111…" 被说成"我的卡尾号 4111"
时 O1 看不见。所以它的承诺是**"减少了部分泄漏"**，不是"不泄漏"。§6.3 的 0/12 是**存储**的读数，
把它当成输出侧的读数，正是本报告反复在防的那类替换。

#### 6.4.3 实现（第 12 步）：把三层接成一次检查，然后发现它们对"私有任务"意见不一致

`DisclosureSession.check(draft, task)` 是这一步唯一新增的公开方法，它做三件事：从读侧取**窗口**、
从私有库取**语料**、把草稿交给 `OutputGuard` 跑 O1+O2+O3。窗口与语料都来自写出这些行的同一个会话，
所以检查问的从来不是另一个问题。

接起来的第一天，两个缺陷同时出现，而它们都不是任何一层的测试能看见的：

| # | 缺陷 | 怎么出现 | 修法 |
|---|---|---|---|
| 1 | **O3 不看任务作用域** | O1 一直对私有任务跳过 scope findings（"回答用户自己的记忆正是产品在工作"），O3 没有跳过。两层接起来之后，**每一条引用了用户自己记忆的私有回答都被拦** —— 私有路径整体不可用，而测试全绿 | `echoes()` 对 `task === 'private'` 直接返回空；`never-retained` 不受影响（凭证从不落库，也从不回显给任何人） |
| 2 | **同一句话被报两次** | 演示里一条 80 字符的私有句在共享草稿里产生**两条一模一样的 `echo`**。注释写的是"一句话一个 finding"，代码做的是"一个窗口一个" —— 上一个窗口之后跳到下一个空格，而那个空格仍在同一句里 | 跳过的位置改成"这句话的结尾"（用已有的 `map` 反查），一句话一个 finding |

第 2 条的发现方式值得记：它是**看输出**发现的，不是看断言。当时所有测试都通过，包括一条测
"56/56 私有行被拦下"的 —— 那条数的是**被拦下的行**，不是 finding 的条数，所以重复项从来不在
它的视野里。

#### 一次真实运行（第 13 次调用起是输出侧）

```
$ check shared 'Here is what I remember: I moved to Berlin in March and now I work at Acme …'
blocked  (2 finding(s)) for a shared task
  echo: I moved to Berlin in March and now I work at Acme on the payments team
  unattributed:

$ check private 'You told me: I moved to Berlin in March and now I work at Acme …'
clear  (0 finding(s)) for a private task

$ check shared 'The project plan moves to Thursday [[c3]].'
clear  (0 finding(s)) for a shared task

$ check shared 'The project plan moves to Thursday.'
blocked  (1 finding(s)) for a shared task
  unattributed:
```

四行的含义：**同一句话，对共享任务是泄漏，对私有任务是产品在工作**；有引用就放行，无引用就拦。
第一行与第二行只差一个参数，而那个参数是这一层最关键的一个决定。

#### 这一次没做的

| 项 | 归属 |
|---|---|
| 改写式泄漏 | 与"不误拦"冲突，第 8 步已断言 |
| 草稿生成（谁来写这段文字） | 编排层；这一层只检查，不生成 |
| 真实题库上的拦截率 | 需要一次真实运行把 `check` 接在答题之后 |

### 6.5 拒绝而非降级

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

**直接含义（第 4 步之前）**：`cortex-ai` 曾依赖 `@xenova/transformers@2.17.2`，落后 v4 两个大
版本，于是**拿不到 WebGPU、拿不到 q4、拿不到 v4 的 ModelRegistry 缓存**。这条 P0 债务已在实现
第 4 步关闭（4.3.1），**代价与收益都量过了**（§4.4）：升级本身逐位等价，需要提防的是 `dtype`
默认值从量化变成 fp32，以及 `text-classification` 单标签 softmax 把重排压成全员并列（§4.4.1）。

**仍未关闭的是"能不能用上"**：`device: 'webgpu'` 这条路径**已实现但未在本仓库测过** —— 需要
一个带 WebGPU 的浏览器与真机；q4 权重同理（`dtype: 'q4'` 可传，但没有一次实测读数）。这两条记在
§13 的债务表里，而不是写成"已支持"。

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
| ~~`cortex-ai` 停在 `@xenova/transformers@2.17.2`~~ | ~~P0~~ **已关闭** | 第 4 步升到 4.3.1；`dtype` 钉死 fp32（§4.4） |
| `device: 'webgpu'` 与 `dtype: 'q8'/'q4'` **可传但未实测** | P1 | 无真机读数；不影响默认路径（fp32/CPU） |
| 认知层不在评测路径（价值写入、巩固、双时态、冲突、图） | **P0** | 净贡献未知，任何"护城河"陈述都不成立 |
| `sinkhorn` 未接线 + 收敛检测器曾恒真 | P1 | 接线那一刻才激活 |
| 默认配置下 `consolidate` 的遗忘时钟量纲错误 | **P0** | 会**删除全部记忆**（已定位） |
| `cortex-memory` 不消费 `Storage` | — | 不是缺陷，是设计事实；影响工作量估计 |
| 浏览器/联邦/分诊三块**只有设计与 POC** | — | 见 03 §2 的启动顺序 |
| Safari 已测但**无跨重启**读数 | P1（影响 iOS 承诺的强度） | WebDriver 会话不是持久 profile；实现阶段用真机补 |
| 端侧**逐条写 5.6 ms**（`journal_mode=delete` 决定的） | P1（影响 API 文档而非架构） | 已在 §3.4.3 量化；写路径必须批量或走事务 |
| `./idb` **无事务** | P2（降级层的能力边界） | 已设计为显式拒绝（§3.4.4），不做假原子 |
| `./analytics`（DuckDB 侧车）未实现 | P2 | 按需 `import()`，与记忆主路径无关 |
| 规则层 leak 的比率仍只有 n=60 | P1 | 需要**同类语料**（职场发言），不是任意语料（§5.4.1） |

实现阶段的启动顺序（每步都有 POC 或单测可依据，不含"边做边定"的决定）：

1. `cortex-storage` 改名 + 五个 subpath + optional peer + **体积守卫**（≤300 KB、不含 native）；
2. `FederatedStorage` 进 core（`[POC-3]` 的 9 条断言直接变单测）；
3. `./opfs` 实现（`[POC-1]` 的 Worker + AHP 形状直接复用）；
4. `cortex-ai` 改名 + transformers.js v4 升级；
5. ~~分诊规则层进 core~~（**已完成**：规则表、写侧与 60 条标注夹具，§5.3.1 / §5.4.2）
   （`[POC-5]` 的 11 条断言变单测）；
6. 卡片与 HITL —— 三项前置（Safari 探针、规则层 n≥600、真实题库端到端）**均已关闭**，
   可与第 5 步并行；输出侧 O1/O2 随卡片一起实现（§6.4）。

---

## 14. 验收契约：判据是数据，不是散文

### 14.1 为什么要有这一层

第 33 步之前，验收标准散在八个 `PREREG-*.md` 与四份测量报告里。这套安排有两个**静默**失败：

1. **数字会漂。** 代码改了，文档里的数还在；没有任何构建步骤读文档，所以没人发现。
2. **没有当前值的判据不可能失败。** "MR 应该到 85%" 在有人把 69.6% 与 85% 放在一起比较之前，
   只是一句愿望。

所以判据被写成**记录**，放在 `cortex-eval/src/acceptance.ts`：

| 字段 | 它防的是什么 |
|---|---|
| `metric` + `dataset` | 一个不说清怎么量的数字，是没人能复现的数字 |
| `comparator` + `threshold` + `unit` | 把 28 个点写成 0.28 |
| `source` | 把一个数值抄进表里（那会是同一测量的第二份副本） |
| `kind`（`gate`/`aim`） | 一个永远不可能绿的构建，或一个拦不住回归的项目 |
| `onMiss` | 装饰性的阈值：没人预先决定miss了怎么办 |
| `competitors` + `grade` | 与一个用别的配方量出来的数比较 |

`source` 是七个变体的联合：`arm` / `gap` / `leak` / `ablation` / `probe` / `artifact` / `unrun`。
它声明的是**值从哪来**，而 `tools/acceptance-check.mjs` 现算。算不出来就是 `unrun`，
不是 0，也不是某人记得的数。

### 14.2 三个状态，两条轴

```
pass    算出来了，达标
fail    算出来了，没达标
unrun   算不出来——报告，但永不当作通过
```

`fail` 再按 `kind` 分：`gate`（已达成，掉下来 exit 1）、`aim`（未达成，打印但不拦）、
`accepted`（决定不修的已知 miss，打印为 `accept`，永不删除）。当前 18 条：13 gate / 5 aim，
其中 1 条 accepted。

**为什么必须分开。** 一个在项目诚实汇报位置时永远不可能绿的构建，会教人删行；而一个不拦任何
东西的构建，会让回归悄悄发生。这两件事必须用两套规则处理，否则其中一件必然做错。

### 14.3 文档里的数字被 CI 绑定

`tools/docs-crosscheck.mjs` 读文档里的 `reading:<id>` 标记，按 id 现算再比。标记是 HTML 注释，
渲染不可见，所以文档读起来正常；漂移时它指名**文件、行号、两个值**。

这一层的意义不是"防止打错字"，而是**改变文档的地位**：白皮书里的分数不再是从别处抄来的，
而是每次 `pnpm check` 重新算出来的。当前 51 个标记跨 53 份文档全部匹配。

### 14.4 这套机制的边界

1. **它只校验数字，不校验论证。** "大约六成"这种句子无法与 58.8% 比较，所以不在范围内。
2. **`unrun` 不是免责。** 一条长期 `unrun` 的判据是技术债，不是"暂无数据"；`--strict-unrun`
   是发布时把它变成 exit 2 的开关。
3. **受控集不是基准。** K/T 系列的数字来自 17 例合成集合，只回答"机制在不在它该在的地方"，
   不回答"能涨几分"。这句话写在 `docs/ACCEPTANCE-MATRIX.md` §4.1 的最后一列。
