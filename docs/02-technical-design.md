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
| **智谱 embedding-3**（嵌入） | 协议兼容（`OpenAIEmbedding`），但**类型不对** | 提议要**生成**：把一句话拆成原子、给出遮罩跨度。嵌入做不到这件事。cortex 里嵌入的位置是检索/重排，由本地 cross-encoder 重排器覆盖；且 429 配额已耗尽，把用户原句发去嵌入 API 还与"本地零网络"直接冲突 |

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
| **G1 逐字接地** | 每个原子必须是原句（折叠大小写、空白、破折号/引号形态、句末标点后）的**连续片段** | 卡片会提供一个用户从没说过、却可以一键发布的句子 |
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
