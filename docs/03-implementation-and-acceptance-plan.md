# Cortex 实现推进与验收计划

> 面向 AgentiX-E/cortex。内部文档。
> 目标：以"发现并解决 BUG"为核心导向的 TDD 路径，全维度测试覆盖率 ≥95%，用真实、公平、科学的权威测试集对标竞品，确保在精度、准度、深度、广度、工程成熟度、测评指标上全面超越竞品。

---

## 0. 结论先行

1. **迭代模型**：M1–M7 七个里程碑，每阶段先写测试（TDD）、实现、跑权威基准 + 显著性检验 + 消融，通过门禁才进入下一阶段。
2. **验收铁律**：全维度覆盖率 ≥95%（语句/分支/函数/行）、无 mock（用 pg-mem、真实 sqlite、真实 WASM）、min/max/avg + Welch's t-test（p<0.05）、**三次命中原则**（连续三次独立运行均达标，且 min 优于基线 median）、绝不 skip/continue-on-error/`|| true`。
3. **权威测试集**：LoCoMo、LongMemEval(S/M)、BEAM(1M/10M)、MemSecBench、MemoryAgentBench、Agent Memory Benchmark(AMB)，外加自建消融套件（写入取舍、抽取保真、检索即巩固、弃权、巩固通道）。
4. **公平对标**：不采信 vendor 单侧分数，**自己复现 Mem0/Zep/Letta 基线**，在相同环境、相同数据、相同指标、相同随机种子下对比；每个结论附日志/数据证据。

---

## 1. 迭代计划（M1–M7）

| 里程碑 | 目标 | 关键测试 | 验收门禁 |
|---|---|---|---|
| **M1** | 最小评测包 + 基线复现 | 跑通 LongMemEval(S)/BEAM-1M/MemoryAgentBench/MemSecBench | 本地复现 Mem0 基线分（±1 容差），评测 harness 可复现 |
| **M2** | 主动弃权 + 价值驱动写入 | LongMemEval ABS、BEAM abstention、自建弃权消融 | BEAM-10M abstention +10、t-test p<0.05、三次命中 |
| **M3** | 双时态 + 冲突消解 | LongMemEval KU/TR、BEAM knowledge_update/contradiction | BEAM-10M KU +8、contradiction +10、图谱成本 −50% |
| **M4** | 巩固通道 + 检索即巩固 | 自建巩固消融、长期一致性 | 消融显著、记忆规模亚线性、min > baseline median |
| **M5** | 投毒防御 + 溯源 | MemSecBench（persistence/consequence/repair） | persistence 显著下降、repair 成功率达标 |
| **M6** | 多智能体一致性 | 自建一致性测试（CRDT 冲突合并） | 冲突合并正确、无数据丢失 |
| **M7** | 跨层统一动力学 | 数值验证 + 理论 | 收敛性数值证明 + 论文级结论 |

---

## 2. 测试方法与覆盖率策略

### 2.1 TDD 铁律

1. 每个功能：先写失败测试 → 最小实现使测试通过 → 重构；
2. 测试覆盖每个维度：**语句 / 分支 / 函数 / 行** 全部 ≥95%；
3. **禁止 mock**：用真实嵌入式 SQLite（better-sqlite3）、内存 PG（pg-mem）、真实 SQLite WASM、真实 transformers.js（小型模型）做集成测试；
4. 属性测试（fast-check）覆盖纯算法：随机矩阵的 SVD 重构误差、Sinkhorn 收敛到双随机、FSRS 稳定性单调性、t-test 统计性质。

### 2.2 覆盖率维度

| 维度 | 目标 | 手段 |
|---|---|---|
| 语句（Statements） | ≥95% | vitest + coverage-v8 |
| 分支（Branches） | ≥95% | 显式测试每个分支 |
| 函数（Functions） | ≥95% | 每个导出函数有测试 |
| 行（Lines） | ≥95% | 行级覆盖 |

### 2.3 公平公正科学的评测协议

- **同环境**：相同 Node 版本、相同 embedding 模型、相同 LLM（若用）、相同硬件；
- **同数据**：下载官方 benchmark 数据（LoCoMo/LongMemEval/BEAM/MemSecBench），不做裁剪；
- **同指标**：Top-1 与 Top-5 严格区分（历史教训：Top-5 不得误标为 Top-1）；
- **同随机种子**：随机算法固定种子，报告三次独立运行的 min/median/avg；
- **显著性**：Welch's t-test（p<0.05），报告效应量；
- **消融**：每个 feature（弃权、双时态、巩固、赫布、FSRS、OT、TD(λ)）逐一开关，量化 Δaccuracy。

---

## 3. 权威测试集与测评挖掘

### 3.1 权威基准清单

| 基准 | 出处 | 结构 | 测评能力 | Cortex 用途 |
|---|---|---|---|---|
| **LoCoMo** | ACL 2024 | 10 段超长对话，588 turns/27 sessions/16.6K tokens | 单跳/多跳/时序/开放域/总结 | 已近饱和（Mem0 92.5 / Zep 94.7），作回归测试 |
| **LongMemEval** | ICLR 2025 | 500 题，~115K tokens/40 sessions；M 版 ~500 sessions | IE/MR/KU/TR/ABS | **主基准**（弃权、知识更新是软肋） |
| **BEAM** | ICLR 2026 | 100 对话，至 1000 万 tokens，2000 探针 | 10 能力（含 contradiction、abstention、knowledge_update） | **规模化压力 + 进攻靶心** |
| **MemoryAgentBench** | — | 记忆 vs 长上下文对照 | contradiction、selective forgetting、长期一致性 | 冲突消解 + 遗忘 |
| **MemSecBench** | 2026 | 310 案例 | 投毒 persistence/consequence/repair | 安全防御 |
| **Agent Memory Benchmark (AMB)** | agentmemorybenchmark.ai | 开放可复现 leaderboard | 真实长上下文任务 | 公开对标 |
| **LifeBench** | 2026 | 长程多源记忆 | 多源融合 | 多源记忆（P2） |
| **3DMem-Bench** | 2026 | 26K 轨迹/2892 具身任务 | 时空/多模态 | 多模态（P2） |

### 3.2 竞品表现整合（需自行复现校准）

> 以下为 vendor/论文报告值，**Cortex 对标前必须自己复现**，不能直接采信。

| 指标 | Mem0 | Zep | Letta | Cortex 目标 |
|---|---|---|---|---|
| LoCoMo | 92.5 | 94.7 | — | ≥95（饱和区，回归） |
| LongMemEval | 94.4 | 63.8 | 83.2 | ≥95（主战场） |
| LongMemEval ABS | 弱 | 弱 | 弱 | **显著领先** |
| BEAM-1M | 64.1 | — | — | ≥68 |
| BEAM-10M | 48.6 | — | — | ≥60（进攻靶心） |
| BEAM-10M abstention | 35.7 | — | — | **+10** |
| BEAM-10M knowledge_update | ~26 | — | — | **+8** |
| BEAM-10M contradiction | 40 | — | — | **+10** |
| MemSecBench persistence | 84%（恶意持久化） | — | — | **显著下降** |

---

## 4. 每个迭代的验收标准（严格完备）

### M1 验收
- [ ] 评测 harness 可一键复现（`pnpm bench`），日志含完整数据；
- [ ] 复现 Mem0 基线（相同环境/数据/指标），偏差 ≤1；
- [ ] 覆盖率 ≥95% 四维度；
- [ ] CI（lint/typecheck/test/format）真实全绿。

### M2 验收（主动弃权）
- [ ] BEAM-10M abstention 提升 ≥+10，Welch's t-test p<0.05；
- [ ] 消融：关弃权 → 幻觉率显著上升（证明弃权贡献）；
- [ ] 三次独立运行，min 值也达标；
- [ ] 弃权阈值校准曲线（reliability diagram）达标。

### M3 验收（双时态 + 冲突消解）
- [ ] BEAM-10M knowledge_update ≥+8、contradiction ≥+10；
- [ ] 图谱构建 LLM 调用数比 Zep 式全量抽取 −50%；
- [ ] 消融：关双时态 → KU 显著下降。

### M4 验收（巩固通道）
- [ ] 消融：开巩固 vs 关巩固，长期一致性显著提升；
- [ ] 记忆库规模在任务量线性增长下保持亚线性；
- [ ] 巩固不阻塞实时推理（延迟 P99 不劣化）。

### M5 验收（投毒防御）
- [ ] MemSecBench persistence 显著下降；
- [ ] repair 成功率达标；
- [ ] 误删真实记忆率（FPR）低于阈值。

### M6/M7 验收
- [ ] M6：多智能体冲突合并正确、无数据丢失；
- [ ] M7：跨层动力学收敛性数值证明 + 论文级结论。

---

## 5. 优化与回归闭环

1. **每轮迭代后下载 benchmark 日志，深入分析失败根因**，产出可执行优化方案；
2. **每次失败做 deep root cause analysis + full fix**，并反思"为何 husky/CI 未在 push 前捕获"；
3. **本地镜像 CI/Release 全部检查项**后才推送，杜绝 local-pass/CI-fail 漂移；
4. **废弃代码直接删除**（不 @deprecated），架构方向调整时整体重写；
5. **每个 green 里程碑后主动给出"最优路径下一步"**。

> 术语与算法背景见 `04-knowledge-dictionary.md`。
