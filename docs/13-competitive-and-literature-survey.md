# 竞品与文献综述：浏览器存储、端侧推理、记忆作用域、人机协同

> 面向 AgentiX-E/cortex。内部设计文档。
> **方法**：每个技术域按"现状（有出处）→ 我们借什么 → 我们不借什么及原因"三段写。
> **证据分级**：`厂商文档`（自述能力）、`论文`（同行评审或预印本）、`实测`（本项目 POC 复跑）。
> 厂商自述一律标注，不与论文结论混排。

---

## 0. 一个总判断

这个领域 2025–2026 的进展**不在"记忆模型变大"，而在"边界被承认"**：存储引擎开始在浏览器里真持久化、
端侧推理把模型搬进标签页、而隐私研究第一次量化了"模型分不清该不该说"的严重程度。
三件事共同指向一个设计后果：**能力下沉到端侧、判断上收到确定性与人**。

---

## 1. 浏览器存储引擎

### 1.1 现状

| 项目 | 状态（2026-10） | 出处 |
| --- | --- | --- |
| **DuckDB-Wasm + OPFS** | 2026-09-18 官方支持 `opfs://`：带 WAL 与 checkpoint 的 `.duckdb` 文件跨刷新/重启存活。**但 npm `latest`（1.33.1-dev57.0）"创建文件却从不写入"**，须锁 1.32.0 或 ≥1.33.1-dev64.0 | `duckdb.org/2026/09/18/opfs-wasm`、`docs/api/wasm/instantiation` |
| **DuckDB `vss`** | "experimental"；HNSW **默认只能建在内存库**，落盘需 `hnsw_enable_experimental_persistence`，理由原文："WAL recovery is not yet properly implemented … **data loss or corruption of the index**"；只支持 `FLOAT`；索引不入 buffer manager、不受 `memory_limit` 约束 | `docs/core_extensions/vss` |
| **SQLite-WASM（官方）** | 提供 OPFS 的 `opfs` 与 access-handle-pool 两种 VFS；同步句柄只在 Worker 内可用 | 官方 `@sqlite.org/sqlite-wasm`；本项目 `[POC-1]` |
| **PGlite + pgvector** | pgvector 为**外置**扩展包（42.9 KB）；浏览器推荐 IndexedDB VFS，**OPFS-AHP 明确"不支持 Safari"**（252 打开句柄上限，而标准 Postgres 安装 >300 文件） | `pglite.dev/docs/filesystems`、`/extensions` |
| **sqlite-vec** | **pre-v1 alpha**（`v0.1.10-alpha.4`，2026-05），README 称"任何 SQLite 能跑的地方，包括浏览器 WASM"；但**官方 JS 文档只覆盖 Node/Deno/Bun**，无浏览器集成示例 | `github.com/asg017/sqlite-vec`、`alexgarcia.xyz/sqlite-vec/js.html` |
| **wa-sqlite** | OPFS/IDB 多后端、强调可扩展；PGlite 的 OPFS-AHP 设计明确取自它 | `github.com/rhashimoto/wa-sqlite`；PGlite 文档自述 |

### 1.2 借什么

- **PGlite 的"access handle pool"思想**：同步句柄无法遍历目录，于是预开一堆随机名句柄当池子、
  用一个 state 文件维护目录映射。我们不需要它的 Postgres，但需要它的**教训**：池子是绕过 API 限制的
  标准手法，代价是 Safari 的句柄上限。
- **DuckDB 的 checkpoint 纪律**：浏览器里"关干净"是例外，`CHECKPOINT` 是唯一确定写进主文件的方式；
  必要时 `SET checkpoint_threshold = '0KB'` 逐语句落盘。

### 1.3 不借什么

- **DuckDB 当记录层**：OLAP 引擎 + "崩溃可能损坏索引"的 HNSW，与"标签页随时被杀"的宿主相反。
- **sqlite-vec 当默认向量层**：pre-v1 且在浏览器里要自己拼 `sqlite-wasm` + 扩展加载 + VFS。
  它仍是**可选后端**（有向量类型与元数据列），但不是默认。
- **PGlite 当默认**：语义最正统，但整库入内存 + 每次查询后整文件刷盘，对"边聊边写"的负载太重。

---

## 2. 向量检索

### 2.1 现状

| 结论 | 出处 |
| --- | --- |
| DuckDB `vss` 的 HNSW 只支持 FLOAT、只支持 L2/cosine/IP、索引必须整体进内存 | 官方 vss 文档 |
| 浏览器侧 ANN 库（HNSW-WASM、Voy 等）需自建索引与持久化，且索引失效后需重建 | 各项目 README |
| 检索质量的公开基准是 LOCOMO / LongMemEval；本项目的 SOTA 攻关全部在 LongMemEval-S 上做 | 本项目 `docs/05-longmemeval-sota-analysis/` |

### 2.2 实测把"直觉"推翻了两次

`[POC-2]`（Node，60k×384，插入式 top-k）：

| 版本 | f64 | f32 | int8 |
| --- | --- | --- | --- |
| 第一版（每命中即 `sort()`） | 16.2 ms | **37.9 ms** | — |
| 修正版（固定缓冲插入） | 22.9 ms | 37.5 ms | 44.7 ms |

第一版里 f32 比 f64 慢 2.3 倍，看起来像"dtype 决定性能"；实际是 **top-k 的簿记**在主导。
修正后三者落在 23–45 ms，**内存却差 8 倍**（176 / 88 / 22 MiB）。结论：

- **dtype 是内存决策**；时间差是同数量级的噪声。
- **int8 在纯 JS 里最慢**（无 i8x16 点积）；它的正当理由是"装得下"，不是"算得快"。
- 任何"int8 更快"的声明必须限定在 **wasm SIMD**，而本项目**未测**。

`[POC-1]`（Chromium，60k×384）= **22.3 ms p50 / 33.4 ms p95**，比 Node 的 37.5 ms 快 1.7 倍。
**Node 不是浏览器的代理**，这条写进方法规则。

### 2.3 借什么 / 不借什么

- 借：**精确扫描 + 固定缓冲 top-k**（`BruteForceVectorIndex` 已在 core，零新依赖）。
- 不借：**浏览器里的 HNSW**。构建成本在 60k 上是秒级到分钟级，而收益是 20 ms → 5 ms；
  在交互预算里这 15 ms 换不来一个"崩溃可能损坏"的结构。
- 备选（未采纳，留作 P3）：`sqlite-vec` 的 `vec0` 虚表（float/int8/binary + 元数据列），
  但需先解决浏览器加载路径。

---

## 3. 端侧推理

### 3.1 现状

| 运行时 | 形态 | 关键限制 | 出处 |
| --- | --- | --- | --- |
| **Transformers.js v4**（`@huggingface/transformers` 4.3.1） | ONNX Runtime Web；默认 WASM(q8)，可选 `device:'webgpu'` | WebGPU 官方 README 仍标"experimental in many browsers" | GitHub README（2026-10-06） |
| **ONNX Runtime Web** | wasm / webgpu / webnn / webgl | **WASM 多线程需 COOP+COEP**（未开则单线程，慢 3–4×）；WebGPU 对 >50M 参数才有明显优势；<10M 时两者接近 | `onnxruntime.ai/docs/tutorials/web/performance-diagnosis` |
| **WebLLM** 0.2.85 | 仅 WebGPU，OpenAI 风格 `chat.completions`，163 个预编译模型 | 无 WebGPU 即不可用；60–100 tok/s（GPU） | 项目 README / 第三方横评 |
| **wllama** | llama.cpp → WASM，GGUF | CPU 5–15 tok/s；多线程需 COOP/COEP | 同上 |
| **Chrome Prompt API（Gemini Nano）** | 浏览器内置，`LanguageModel` | **Chrome 148+ 桌面**；>4 GB VRAM、约 22 GB 磁盘；磁盘不足会被驱逐；Android/iOS/Firefox/Safari 无 | Chrome 文档 / 第三方综述 |
| ~~MediaPipe LLM Inference~~ | —— | **维护模式**，后继为 LiteRT-LM | Google 公告 |

**对本项目的直接含义**：`cortex-llm` 现在依赖 `@xenova/transformers@2.17.2`，落后到 v4 两个大版本，
于是**拿不到 WebGPU、拿不到 q4、拿不到 v4 的 ModelRegistry 缓存**。这是 P0 级债务，不是优化项。

### 3.2 端侧 PII / NER（分诊第 2 层）

| 项目 | 形态 | 关键数字 |
| --- | --- | --- |
| **Rampart**（National Design Studio） | 确定性识别器 + 14.7 MB token-classification ONNX（MiniLM-L6 微调，17 类实体，7 种拉丁字母语言，4-bit MatMul + INT8 embedding） | 明确声明：**非拉丁文字姓名召回约 14%**；"不检测推断性标识（罕见病 + 5 位邮编）" |
| maskera（瑞典语） | 规则层 + 约 43 MB NER（KB-BERT） | 自建 121 条合成测试集上 211/211 全脱敏；作者自评"语料与其耦合，非独立排名" |
| bert-base-NER（通用） | 约 110 MB 首次下载 | 常见 demo 用它，但体积对首屏不友好 |

### 3.3 借什么 / 不借什么

- **借两层结构**：确定性识别器（强格式、校验位）+ 小模型（人名/地名）。这是 Rampart 与 maskera 的共同形态，
  也是我们 `[POC-4]` 规则层 + 本地 NER 的同一分层。
- **借"能力声明"的写法**：Rampart 在模型卡里直说非拉丁召回 14%，这是可复制的诚实标准；
  我们的卡片 UI 必须显示"未脱敏预览"而不是假装覆盖。
- **不借 WebLLM 作为默认生成**：仅 WebGPU，且质量/时延在 0.5B–1B 上未知；它属于"离线演示"档，不属于默认路径。
- **不借 Chrome Prompt API 作为唯一本地 LLM**：桌面 Chrome 独占 + 硬件门槛 + 模型可被驱逐 = 不可作为 SLA。

---

## 4. 记忆作用域与上下文完整性

### 4.1 现状（产品）

| 产品 | 作用域模型 | 值得注意的细节 |
| --- | --- | --- |
| **Letta（原 MemGPT）** | 一个 memory block 可挂到多个 agent → **共享块**；per-user 需显式 `user_id`，否则默认全局 | 文档承认"忘记传 user_id 会静默泄漏"是最常见事故 |
| **Mem0** | 四维：`user_id` / `agent_id` / `run_id` / `app_id` | 作用域在存储层强制，与框架解耦；选择性抽取报 80% token 削减、6pp 精度损失 |
| **Zep / Graphiti** | 双时态知识图谱；事实"失效不删除" | 解决"什么时候为真"，不是"谁能看" |
| **Sentra** | 全组织单图 + 写入时按本体理解 + **permission-scoped facts** | 把权限写进事实，而非查询 |
| **Redis Agent Memory** | namespace + user 标识；working/long-term 两层 | 用命名空间做隔离，与我们的表前缀同构 |
| **Claude Projects** | 记忆按 project 作用域；`pause` vs `reset` | 关闭的两种语义要分开 |

### 4.2 现状（研究）：这是本项目最重要的一条外部证据

**CIMemories**（FAIR @ Meta；arXiv 2511.14937；ICLR 2026）基于 Nissenbaum 的 contextual integrity：

| 发现 | 数字 |
| --- | --- |
| 属性级违规率（只用三人格一致的"简单题"） | **最高 69%** |
| 随任务累积 | 1→40 任务，GPT-5 从 0.1% → 9.6% |
| 随重复累积 | 同一 prompt 跑 5 次到 **25.1%**（"相同提示下泄漏不同属性"） |
| 隐私提示词 | **无效**，退化为全说/全不说；GPT-4o 违规 14.8% 但完整性仅 43.9% |
| 失败形态 | **粒度失败**：模型认得出"领域相关"，分不清领域内哪个细节该说 |

配套的行业观察一致：违规是**输出侧**问题（"没人越权，模型只是知道"），
所以传统访问控制看不见它；且"记忆 = 前缀文本"的注入方式让更大的上下文窗口**加剧**问题。

### 4.3 借什么 / 不借什么

- **借 contextual integrity 作为政策语言**：隐私不是"敏感/不敏感"，是"流动是否符合语境"。
  这直接给出我们的三值（private / shared / defer）与"第三方人名默认私有"的根据。
- **借 CIMemories 的度量**：它把"该不该说"变成可测的 violation / completeness 两个指标。
  我们无法直接跑它（需要多任务画像数据），但可以借其**构造法**：多属性画像 × 多任务语境 × 每属性标注。
- **不借"让模型自己判断"**：69% + 25% 波动 + 提示词无效，三条合起来否掉了这条路。
- **不借 Sentra 的"单图共享"**：它是企业场景（一个组织一份真相）；我们的场景是**一个人的私有 + 一个团队的共享**，
  两者必须物理分离，而不是同一图上的权限位。

---

## 5. 人机协同与记忆卡片

### 5.1 现状

| 产品 | 机制 | 细节 |
| --- | --- | --- |
| **Hyperagent** | 学习提案队列 | **接受前什么都不生效**；接受时选"你的记忆 / 这个 agent 的 / 工作区共享"；`Dismiss` 是终态；支持合并重复、归档优于删除 |
| **AideAI** | 敏感度分级确认 | 中性习惯自动存（10 分钟可撤销）；**敏感事实必须确认卡**；secret 直接不存；"Is this still accurate?" 过期复核；`Used from memory` 标注；Memory Center 五 tab（Active / Needs review / Needs update / History / Access） |
| **ChatGPT / Claude / Gemini** | 账号级记忆列表 | 共同缺陷：藏在设置二级、hover 才出控件、写入无确认（HCI 研究称为"评估鸿沟"） |
| **memory card 五原则**（行业综述） | 可见 / 可编辑 / 有作用域 / 可过期 / 可导出 | 明确"不可导出 = 锁定 = 招致迁移" |
| **AI UX Playground** | 作用域开关 | 保存时的 scope toggle（这条/项目/全部）与账号级列表是**两个界面**，都要有 |

### 5.2 借什么 / 不借什么

- **借三档归属**（你的/agent 的/工作区共享）→ 映射为 private / shared / both。
- **借"敏感度分级触发"**：不是每条都问，而是"中性自动 + 敏感必确认 + 凭据不存"。这是覆盖率 26.7% 之后
  唯一可扩展的交互结构。
- **借"dismissed 终态"与"过期复核"**：前者防打扰疲劳，后者防过期事实污染。
- **不借"账号级列表即全部"**：列表是审计面，**写入点的确认**才是控制面。CIMemories 的累积效应说明
  事后审计无法补偿事前不拦。
- **不借"hover 才出控件"**：所有主操作常驻可见。

---

## 6. 评测集

| 数据集 | 测什么 | 本项目怎么用 |
| --- | --- | --- |
| **LongMemEval-S**（500 题，5 能力：IE/ABS/KU/MR/TR） | 长程记忆问答 | 主战场：所有 SOTA 攻关读数（`docs/07`） |
| **LOCOMO** | 长对话记忆（多轮、跨会话） | 交叉验证检索与巩固；Mem0 报告在此上做了 selective extraction 消融 |
| **CIMemories**（10 画像 × 平均 147 属性 × 45 语境） | 上下文完整性（violation / completeness） | **分诊层的目标指标**：作为外部基准引用，不重跑（需画像数据） |
| **ai4privacy/openpii-1.5m** | PII 标注 | 本地 NER 的召回/精度评测（Rampart 的训练与评测来源） |
| **BEAM / MemoryAgentBench / AMB** | 多会话、超大上下文 | 二期扩展（见 `docs/03`） |

**本项目自建的两个"仪器"指标**（因为外部集测不到）：

1. **噪声底**：同一配置跑两次的净差（MR −2 / TR −4，`[实测]`），任何效应必须越过它才叫效应。
2. **false-share 上界**：规则层在小样本上的 Wilson 上界（`[POC-4]`），而不是"零次"。

---

## 7. 逐域结论表

| 域 | 我们采用 | 我们拒绝 | 拒绝的理由（可核） |
| --- | --- | --- | --- |
| 浏览器存储 | SQLite-WASM + OPFS-AHP 作记录层 | DuckDB 作记录层、PGlite 作默认 | 写形态不匹配；HNSW 落盘官方承认可能损坏；PGlite 整库入内存 |
| 向量 | 精确扫描 + 插入式 top-k；f32/int8 按内存选 | 浏览器 HNSW | 60k 只需要 22 ms；索引构建与失效风险不划算 |
| 端侧推理 | transformers.js v4（WASM 默认 / WebGPU 可选） | WebLLM 作默认、Chrome Prompt API 作 SLA | 仅 WebGPU / 桌面独占 + 可被驱逐 |
| PII | 规则层 + 本地小 NER（两层） | 单一模型端到端 | Rampart/maskera 同为两层；模型对非拉丁召回仅 14% |
| 作用域 | 物理分离的两库 + 表前缀命名空间 | 单库权限位 | 企业单图假设与"个人私有 + 团队共享"不符 |
| 披露决策 | 规则 → 用户；模型只提议 | 模型直接决定 | CIMemories 69%、累积、提示词无效 |
| 交互 | 提案队列 + 三档归属 + 终态忽略 + 过期复核 | 账号级列表作为唯一控制面 | 事后审计无法补偿事前不拦 |
| 评测 | LongMemEval 主战场 + 自建噪声底/false-share 上界 | 单次运行的点估计 | 净差可达 4 题（`[实测]`） |
