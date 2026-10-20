# Cortex 技术设计与实现

> 面向 AgentiX-E/cortex（Node.js/TypeScript 智能体记忆系统）。内部文档。
> 目标：以最高工程标准、零妥协地追求极致完美与优雅，覆盖从架构到底层功能实现；明确每个功能"自研 vs 引入 npm 包"的决策与理由；多候选包深入对比后给出最优选项。

---

## 0. 结论先行

1. **架构**：pnpm monorepo，参考 `entity-resolver` 的"core = 纯契约 + 零 I/O 算法，node/browser = 后端适配"分层。核心包 `cortex-core` 同时兼容 Node 与浏览器，所有 I/O 通过接口注入。
2. **抽象层**：Storage（嵌入式/远程）、Vector（暴力/IVF/HNSW/pgvector）、LLM、Embedding、Graph 五类抽象全部以接口定义在 core，具体实现下沉到 node/browser 包。
3. **自研 vs 引入原则**：**算法核心（价值驱动、弃权、巩固、双时态、冲突消解、最优传输、IB、FSRS、TD(λ)）全部自研**（这是 Cortex 的护城河，且需最高精度控制）；**存储引擎、线性代数、图结构、本地 embedding、属性测试等基础设施引入成熟 npm 包**，避免重复造轮子。
4. **科学计算包选型**：线性代数选 **`ml-matrix`**（纯 JS、Float64、Jacobi SVD、浏览器+Node 双端）；图选 **`graphology`**（纯 JS、零依赖、双端）；统计检验**自研**（Kahan 求和 + Welford 方差 + Welch's t-test，保证 Float64 精度）。
5. **存储选型**：Node 嵌入式选 **`better-sqlite3`**（同步、快、成熟）；向量检索扩展选 **`sqlite-vec`**；远程选 **`pg` + pgvector**；浏览器选 **`@sqlite.org/sqlite-wasm`**（官方 OPFS）+ 内存 Map 降级。

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        cortex-core (契约 + 纯算法，零 I/O)          │
│  interfaces/  domain/  memory/  value/  consolidation/           │
│  temporal/  contradiction/  abstention/  retrieval/              │
│  math/(ot, ib, fsrs, stats)  graph/  provenance/  security/       │
├─────────────────────────────────────────────────────────────────┤
│   cortex-node                 │   cortex-browser                  │
│   better-sqlite3 + sqlite-vec │   @sqlite.org/sqlite-wasm + OPFS  │
│   pg + pgvector               │   内存 Map + IndexedDB            │
│   (Node 专属后端)              │   (浏览器专属后端 + Web Worker)     │
├─────────────────────────────────────────────────────────────────┤
│   cortex-llm  (LLM/Embedding 适配器)   cortex-server (REST, 可选)  │
│   cortex-cli  (CLI, 可选)               cortex-studio (UI, 可选)   │
└─────────────────────────────────────────────────────────────────┘
```

**核心原则**：
- **依赖倒置**：core 只依赖接口，不依赖任何 I/O 实现；
- **浏览器与 Node 共享 100% 核心算法**，只有"存储/网络/嵌入推理"层不同；
- **所有外部依赖要么嵌入式、要么可替换**，绝不依赖独立外部服务/进程。

---

## 2. 子包结构（参考 entity-resolver）

```
packages/
├── cortex-core          # 契约 + 纯算法，零 I/O，双端
├── cortex-node          # better-sqlite3 + pg 后端（Node）
├── cortex-browser       # sqlite-wasm + IndexedDB 后端（浏览器）
├── cortex-llm           # LLM + Embedding 适配器（本地 transformers.js + 远程 API）
├── cortex-server        # REST API（可选，Hono）
├── cortex-cli           # 命令行（可选）
└── cortex-studio        # Web UI（可选，Vitepress/React）
```

### 2.1 包职责

| 包 | 职责 | 依赖 |
|---|---|---|
| `cortex-core` | interfaces、domain types、认知算法、数学工具 | `ml-matrix`、`graphology` |
| `cortex-node` | better-sqlite3 / sqlite-vec / pg 后端实现 | `cortex-core`、`better-sqlite3`、`sqlite-vec`、`pg` |
| `cortex-browser` | sqlite-wasm / IndexedDB 后端实现 + Worker 池 | `cortex-core`、`@sqlite.org/sqlite-wasm`、`idb-keyval` |
| `cortex-llm` | LLM/Embedding 适配器 | `@xenova/transformers`（本地）、fetch（远程） |
| `cortex-server` | REST（Hono） | `cortex-core`、`cortex-node` |
| `cortex-cli` | CLI | `cortex-core`、`cortex-node` |
| `cortex-studio` | Web UI | `cortex-core`、`cortex-browser` |

---

## 3. 抽象层设计

### 3.1 Storage 抽象（可插拔存储）

```ts
// cortex-core/src/interfaces/storage.ts
export interface Storage {
  // 键值 / 事实 / 记忆条目 / 图 / 元数据 的统一读写原语
  put(table: string, key: string, value: unknown, opts?: PutOptions): Promise<void>;
  get<T>(table: string, key: string): Promise<T | undefined>;
  del(table: string, key: string): Promise<void>;
  query<T>(table: string, predicate: QueryPredicate): Promise<T[]>;
  transaction<T>(fn: (tx: StorageTx) => Promise<T>): Promise<T>;
  close(): Promise<void>;
}
```

**为什么这么设计**：把"记忆条目 / 事实边 / 图节点 / 溯源日志 / 元数据"统一为表格化 KV 原语，让 embedded（better-sqlite3）与 remote（pg）实现同一接口，浏览器（sqlite-wasm）也一致。**这是 cortex 可插拔存储的基石**。

### 3.2 Vector 抽象（可插拔向量索引）

```ts
export interface VectorIndex {
  add(id: string, vector: Float64Array, meta?: unknown): Promise<void>;
  search(query: Float64Array, k: number, filter?: Filter): Promise<VectorHit[]>;
  remove(id: string): Promise<void>;
  size(): Promise<number>;
}
```

**实现矩阵**：
- Node 嵌入式：`sqlite-vec`（IVF + brute-force + metadata filter）；
- Node 远程：pgvector（IVFFlat / HNSW）；
- 浏览器：内存暴力搜索（`ml-matrix` 矩阵化 + 分块）+ IndexedDB 持久化；
- 兜底：纯暴力精确搜索（所有环境可用，作为基准）。

### 3.3 LLM 抽象

```ts
export interface LLM {
  complete(prompt: string, opts?: CompleteOptions): Promise<string>;
  completeStructured<T>(prompt: string, schema: JsonSchema, opts?): Promise<T>;
}
```

### 3.4 Embedding 抽象

```ts
export interface EmbeddingModel {
  embed(texts: string[]): Promise<Float64Array[]>;   // 返回 Float64 向量
  dimension(): number;
}
```

- 本地：`@xenova/transformers`（transformers.js），浏览器 + Node 双端、离线、隐私；
- 远程：OpenAI 兼容 / 任意 provider 的 fetch 适配器；
- **关键**：统一转成 `Float64Array`，保证与 ml-matrix 的精度衔接（不让 embedding 的 float32 截断污染下游计算）。

### 3.5 Graph 抽象

```ts
export interface MemoryGraph {
  addEdge(a: string, b: string, weight: number, kind?: EdgeKind): void;
  neighbors(id: string): Iterable<{ id: string; weight: number }>;
  // 扩散激活 / 路径搜索 / 连通分量 / 谱聚类
  spreadingActivation(seeds: string[], maxDepth: number): Map<string, number>;
  shortestPath(a: string, b: string): string[] | null;
}
```

基于 `graphology`（图结构）+ 自研认知算法（扩散激活、赫布更新）。

---

## 4. 核心算法设计（自研，护城河）

### 4.1 价值驱动写入 + 主动弃权（MDP + VoI）

- 记忆条目 = `{ content, value, confidence, source, timestamps }`；
- 写入决策：`write = U(future_utility) > threshold`，效用用**习得价值函数**（可插拔：启发式 VoI / 习得 MDP 策略）；
- 检索决策：返回 `null` 当 `max_U(query, memories) < τ`（弃权），τ 用留出集校准；
- 置信度校准：Platt/temperature scaling，输出校准后的 `P(可靠答案)`。

### 4.2 异步巩固通道（Hebbian + FSRS + OT + TD(λ)）

- **Hebbian 边权**：`w_ij ← w_ij + η·σ(共激活显著性)·(1−w_ij)`，全局突触衰减；显著性函数 σ 用统计显著性（观测共激活 / 期望共激活），抑制噪声关联；
- **FSRS 遗忘曲线**：稳定性 `S` 随检索增益更新，遗忘 `exp(−Δt/τ)`；
- **跨层蒸馏**：情景记忆 → 语义记忆，用 **Sinkhorn 最优传输**约束信息分布保持（避免过度抽象丢细节）；
- **信用分配**：沿记忆 DAG 用 **TD(λ) 资格迹**反向传播任务成败信用。

### 4.3 时序双时态 + 冲突消解

- 事实 = `(subject, predicate, object, valid_from, valid_until, system_from, system_until, source, confidence)`；
- "当前有效值"查询走时间区间索引（段树/区间树）；
- 冲突消解 = 时序优先 + **贝叶斯证据融合**（来源可信度加权 + 后验更新）。

### 4.4 抽取保真（Information Bottleneck）

- 显式优化 `max I(M;未来) − β·I(M;原始)`，把"丢多少留多少"变成可求导目标；
- 用 ml-matrix 做互信息估计的数值实现。

### 4.5 数学工具（自研，Float64 精度）

| 工具 | 用途 | 算法 |
|---|---|---|
| Sinkhorn 最优传输 | 记忆多样性、巩固蒸馏 | Sinkhorn-Knopp 迭代（ml-matrix） |
| SVD / 特征分解 | 降维、谱聚类、图 Laplacian | ml-matrix Jacobi SVD |
| Welch's t-test | 显著性检验 | 自研（Welford + t 分布近似） |
| Kahan 求和 | 高精度累加 | 自研 |
| FSRS 遗忘曲线 | 记忆衰减 | 自研 |

---

## 5. npm 包选型：自研 vs 引入（深入对比）

### 5.1 存储引擎

| 候选 | 环境 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **`better-sqlite3`** | Node | 同步、极快、成熟、支持扩展加载 | 仅 Node，需原生编译 | ✅ **Node 嵌入式首选** |
| `node:sqlite` | Node | 内置无依赖 | 仍标记 experimental，API 不稳定 | ❌ 暂不用 |
| `@duckdb/node-api` | Node | 分析强、列式 | 重、非 OLTP 友好、启动慢 | ❌ 不适配高频小写 |
| **`pg`** | Node | PostgreSQL 标准客户端、成熟 | 需外部 PG 服务 | ✅ **远程首选** |
| **`@sqlite.org/sqlite-wasm`** | 浏览器 | 官方、OPFS 持久化 | WASM 体积 | ✅ **浏览器首选** |
| `sql.js` | 浏览器 | 简单 | 非官方、无 OPFS、持久化弱 | ⚠️ 备选 |
| `absurd-sql` | 浏览器 | IndexedDB 持久化 | 依赖 sql.js、维护弱 | ❌ |

### 5.2 向量检索

| 候选 | 环境 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **`sqlite-vec`** | Node(+WASM) | 零依赖、轻量、IVF+暴力、可嵌入 better-sqlite3 | 需加载扩展 | ✅ **Node 嵌入式首选** |
| `hnswlib-node` | Node | HNSW 快 | 原生编译、无元数据过滤、维护一般 | ⚠️ 备选 |
| `vectra` | Node | 本地索引 | 单机文件、无 SQL 整合 | ❌ |
| `pgvector` | PG | 远程标准 | 需 PG 扩展 | ✅ **远程首选** |
| 自研暴力 | 双端 | 精确、可控、无依赖 | 规模受限 | ✅ **兜底 + 基准** |

### 5.3 科学计算（线性代数 / SVD / 特征分解）

| 候选 | 精度 | 双端 | 性能 | 结论 |
|---|---|---|---|---|
| **`ml-matrix`** | Float64 | ✅ 纯 JS | 中（Jacobi SVD 稳定） | ✅ **首选** |
| `mathjs` | Float64 | ✅ | SVD 支持弱（`eigs` 有，SVD 需自写） | ❌ SVD 缺失 |
| `@stdlib/stdlib` | Float64 | ✅ | 全面但庞大 | ⚠️ 太重 |
| `vectorious` | Float64 | ❌ Node（BLAS） | 高 | ❌ 不跨浏览器 |
| `@tensorflow/tfjs` | Float32 | ✅ | 高 | ❌ 默认 float32 精度不足 |

**为什么 ml-matrix**：纯 JS 双端、Float64、内置 Jacobi SVD 与对称特征分解（数值稳定）、API 简洁、体积小。SVD 是 PCA/谱聚类/IB 的基石，mathjs 的 SVD 缺失是硬伤，tfjs 的 float32 不满足"最高精度"要求，vectorious 的 native BLAS 无法跨浏览器。

### 5.4 图结构

| 候选 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **`graphology`** | 纯 JS、零依赖、双端、算法齐全 | — | ✅ **首选** |
| `@dagrejs/graphlib` | 成熟 | 算法少、维护一般 | ❌ |
| 自研邻接表 | 可控 | 重复造轮子、易错 | ❌ |

### 5.5 LLM / Embedding

| 候选 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **`@xenova/transformers`** | 本地、双端、离线、隐私 | 模型需下载、体积大 | ✅ **本地 embedding 首选** |
| OpenAI SDK | 远程标准 | 绑定单一 provider | ⚠️ 用 fetch 自建适配 |
| `ai`（Vercel） | 统一多 provider | 抽象层重、运行时依赖 | ❌ 自建轻量抽象更可控 |

**为什么自建 LLM/Embedding 抽象**：只需"complete / embed"两个原语，用 fetch + 可插拔 provider 配置即可，避免引入重量级框架；本地推理用 transformers.js，远程用 OpenAI 兼容协议。

### 5.6 测试与验证

| 候选 | 用途 | 结论 |
|---|---|---|
| `vitest` + `@vitest/coverage-v8` | 单测 + 覆盖率 | ✅ |
| `fast-check` | 属性测试（发现边界 bug） | ✅ |
| `pg-mem` | 内存 PG（真实 SQL 测试，无 mock） | ✅ |
| `@playwright/test` | 浏览器 e2e | ✅ |

---

## 6. 底层功能实现要点

1. **数值精度**：所有向量/矩阵用 `Float64Array` / ml-matrix（Float64），统计用 Kahan 求和 + Welford 方差，避免 float32 截断与灾难性抵消。
2. **异步巩固**：巩固进程为独立 worker，批量异步更新，只更新被访问节点的局部邻域，保证实时推理不被阻塞。
3. **可溯源**：provenance DAG + 不可变日志（append-only），每条记忆带来源、时间、可信度；删除用逻辑删除 + 墓碑，支持遗忘权。
4. **安全**：来源可信度评分 + 沙箱验证 + 审计回滚（对标 MemSecBench 的 persistence→consequence→repair）。
5. **双端一致性**：core 的纯算法在 Node 与浏览器跑同一套测试（vitest + playwright），杜绝环境漂移。
6. **CI 真实全绿**：`ci = lint && typecheck && test && format`，绝不 `continue-on-error`/`|| true`。

7. **证据角色的边界（`evidenceRoles` / `roleOf`）**：证据房间按**角色**过滤，但产品**不解析任何数据集的格式**。
   `CortexMemory` 接受三个输入 —— `evidenceRoles`（允许的角色集合）、`evidenceRolesRoutes`（触达哪些路由）、
   `roleOf`（把一轮文本读成角色的回调）；格式知识由调用方（benchmark 臂的 `roleOfTurn`）提供。
   三个状态都是被决定的而非默认的：缺席 = 不过滤且提示词逐字节不变；`roleOf` 返回 `undefined` = **保留**该轮
   （分类器失败不能读成"没有证据"）；空集合 = **构造期拒绝**（它会在每条被触达的路由上什么都不放行）。
   过滤发生在**准入之后、选择之前**，多会话路径上**逐会话**执行，捕获（`lastRetrievedContext` /
   `admittedEvidence`）在过滤之后，因此覆盖率数字描述的是读者可能被展示的东西。
   设计理由见 `09-progress-and-delivery-report.md` §133、注册见 `PREREGISTRATION-CORTEX-MEMORY-ARM.md` §13.83。

8. **问法与渲染是两条独立的轴（`EvidenceAsk`）**：一次提示词由**证据**、**渲染**（`numbered` / `sourced`：证据怎么印）
   与**问法**（`route` / `extractive` / `aggregate` / `computed` / `enumerated` / `sweep`：模型被要求做什么）
   三者组成，三者可以各自移动。问法的**触达**（`ASK_ROUTES`）是实验的一部分而不是注释：
   一个 run 的产物必须说清哪些路由的指令真的变了，否则"处理没有到达提示词"会被读成"处理无效"。
   `sweep` 是第一个**只触达一条路由**的问法 —— 它要求逐会话写一行（`Session <n>: <items, or none>`）再数，
   其余五条路由保持 shipped 块逐字节不变，于是 IE/KU/ABS/TR 成为这次实验的内部对照。
   设计理由见 `09-progress-and-delivery-report.md` §140、注册见 `PREREGISTRATION-CORTEX-MEMORY-ARM.md` §13.92。

9. **第二遍咨询（`reviewPass`）**：`audit` 在多会话路由上**再咨询一次**，给模型同一批证据、逐字引用的第一遍回答，
   以及三个"清单会错的地方"（漏条目 / 把两件事并成一条 / 证据不支持的条目），要求以强制写出的 `Step 2 — <数>` 收尾。
   触达是**结构性**的（它长在 `answerSessions` 里），所以其它五条路由不可能被配置进来；
   预算用 `fitToBudget` **重新选证据**而不是在第一份提示词后追加；第一遍弃答时不做第二遍。
   设计理由见 `09-progress-and-delivery-report.md` §142、注册见 `PREREGISTRATION-CORTEX-MEMORY-ARM.md` §13.94。

> 完整实现推进与验收见 `03-implementation-and-acceptance-plan.md`。
