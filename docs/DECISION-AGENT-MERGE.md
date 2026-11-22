# 决策：`cortex-agent` 并入 `cortex-ai` 的 `./agent` 子路径

> 状态：已实施，`pnpm check` 待复跑确认（本文记录实施过程与三个被暴露的门禁缺陷）。
> 触发：用户三连问——"为什么要依赖 `cortex-memory`？" → "B 方向之后不就可以并进 `cortex-ai` 了？" → "合并"。

## 0. 结论

`@agentix-e/cortex-agent` 已删除，十个源文件、八个测试文件、一个 bench 入口分别迁到
`packages/cortex-ai/src/agent/`、`packages/cortex-ai/src/__tests__/agent/`、
`packages/cortex-memory/bench/probe-multi-step.ts`。

合并的前提是一处**必须连同做的重构**：渲染器从 import 改成端口。没有它，合并会把一条
`cortex-ai → cortex-memory` 的边塞进适配层；有了它，`cortex-ai/agent` 的依赖只有 `cortex-core`。

| 项 | 合并前 | 合并后 |
| --- | --- | --- |
| 工作区包数 | 6 | **5** |
| `cortex-ai` 生产依赖 | `{core}` | `{core}`（未变） |
| `cortex-ai` 兄弟 dev 依赖 | 无 | 无 |
| agent 的渲染依赖 | `cortex-memory`（import `buildPrompt`/`admitTurns`） | **无**（`Renderer<Config>` 端口） |
| `cortex-ai` 导出面 | `.` / `./local` / `./web` | `.` / **`./agent`** / `./local` / `./web` |
| 测试 | ai 300 余 + agent 118 | ai **414**（单一套件） |
| 覆盖率（ai） | 99.79 / 100 / 99.01 / 100 | **100 / 100 / 100 / 100**（agent 子目录逐文件 100） |
| memory 测试 | 1,696 | **1,710**（+14：`renderInOrder` 9 + 跨包等价 3 + 计数修正） |

## 1. 为什么合并在"B′ 之后"才成立

合并的原始障碍不是"两个包都碰模型"，而是一条具体的边：agent 曾经 `import { buildPrompt }`。
把它塞进 `cortex-ai` 就等于让**适配层依赖渲染层**，而 `cortex-ai` 的全部意义是"离模型最近、
离策略最远"。

B′ 把这条边换成 `Renderer<Config>` 端口后，`cortex-ai/agent` 的 import 只剩：

```ts
import type { LLM } from '@agentix-e/cortex-core';
```

于是合并的代价从"依赖倒置"降为"零依赖增量的一个 barrel 条目"，这才是可以接受的形态。

**这条顺序不能颠倒**：先合并再端口化，中间那个提交会带一条环状依赖通过 `pnpm install`。

## 2. 判据与它的失效

上一轮反对合并的理由是 `git log` 测出的 **0/11 共同提交**（11 次里没有一次同时碰两棵树）。
用户选择合并，等于主动放弃这条判据。

按项目规则，放弃的判据必须留痕而不是删除。因此：

- 判据本身仍然成立，记录在 `docs/DESIGN-MULTI-STEP-RETRIEVAL.md` §2 末段；
- 放弃的理由是**产品形态优先于包拓扑**：1,159 行、零 IO、一个接口，撑不起一个独立包的发布叙事；
- 若将来 `./agent` 长出第二条依赖或独立版本需求，恢复为独立包的成本是 `git mv` —— 因为端口已经在了。

## 3. 改动清单

### 3.1 新增（memory 侧，渲染归属）

| 文件 | 内容 |
| --- | --- |
| `packages/cortex-memory/src/render-in-order.ts` | `renderInOrder({question, turns, ordered, config})`：admission（`now:0, threshold:0`）→ 按给定顺序重排 → 逐条 rank-difference 打分 → `buildPrompt` |
| `packages/cortex-memory/src/__tests__/render-in-order.test.ts` | 9 例：等价、顺序、裁切、重复 id、越界 id、同文本一次计分、temporal、ask、无日期 |
| `packages/cortex-memory/src/__tests__/agent-renderer.test.ts` | 3 例跨包：byte-for-byte 等价、真索引对照、`maxSteps:0` 端到端 |

`renderInOrder` 的调用者是 `packages/cortex-memory/bench/probe-multi-step.ts` —— 导出普查扫
`bench/`，这条边也是它不成为孤儿的原因。

### 3.2 改造（agent 侧，端口化）

| 文件 | 改动 |
| --- | --- |
| `types.ts` | 新增 `Renderer<Config>`、`RenderedPrompt`（结构化 `carried[].ordinal`），本地声明 `SearchHit` |
| `compose.ts` | 145 → 90 行：只做"去重 + 保序 + 交给渲染器"，不再渲染 |
| `tools.ts` | `SearchIndex` → 内联结构类型；`SearchableIndex`/`IndexRetrievalOptions` 取消导出 |
| `probe.ts` | 收 `retrievalFor` 工厂 + `renderer` + `config`，不再 `new SearchIndex()` |
| `index.ts` | 导出面 8 个名字；不再导出无调用者的类型 |

### 3.3 迁移与删除

```
packages/cortex-agent/src/*.ts        → packages/cortex-ai/src/agent/
packages/cortex-agent/src/__tests__/  → packages/cortex-ai/src/__tests__/agent/
packages/cortex-agent/bench/*.ts      → packages/cortex-memory/bench/probe-multi-step.ts
packages/cortex-agent/                → 删除
```

`probe-multi-step.ts` 落在 memory 而不是 eval，原因写在它的头注释里：它同时需要 loop（`cortex-ai`）、
renderer（`cortex-memory`）、corpus loader（`cortex-eval`），而只有 memory 对三者都已有边。

## 4. 实施中被暴露的三个问题

这三个都不是"搬迁失误"，是合并把一个原本被包边界掩盖的缺陷摆到了台面上。

### 4.1 `pnpm` 报出环，而环是"测试用房边"造成的

第一次 `pnpm install` 输出：

```
WARN  There are cyclic workspace dependencies: cortex-ai, cortex-memory, cortex-eval
```

成因链条：`ai --dev--> memory` → `memory --dev--> eval` → `eval --dep--> ai`。
断在 `ai --dev--> memory`：**测试不是增加产品边界的理由**。

处置：ai 的测试全部改用本地假实现（`recorder` 渲染器、查表检索器）；唯一需要真实现的
"渲染等价"断言移到 memory（它对 `cortex-ai` 已有 dev 边）。第二次 install 无环警告。

### 4.2 导出普查只排除 `src/__tests__/`，不排除嵌套的 `src/agent/__tests__/`

`tools/export-census.mjs` 的过滤条件是：

```js
.filter((path) => !path.includes(`${sep}src${sep}__tests__${sep}`))
```

放在 `src/agent/__tests__/` 的 `fixtures.ts` 因此被当作**生产代码**扫描，四个 export
（`ScriptedLlm`、`FailingLlm`、`ScriptedRetrieval`、`scriptedRetrieval`）立刻成为"新孤儿"。

处置：测试目录改为 `src/__tests__/agent/`（与其余包一致），import 相对路径一并改为 `../../agent/`。
**没有改普查脚本**——脚本的约定是"测试在 `src/__tests__/` 下"，改约定的成本高于改布局。

### 4.3 `SearchHit` 失去唯一的外部调用者

`cortex-memory` 的 `SearchHit` 之所以十年没有成为孤儿，是因为 `cortex-agent` 的 `types.ts`
import 过它。agent 自持类型之后，它掉进普查的未引用类。

处置：`export type SearchHit` → `type SearchHit`，并从 memory 的 barrel 移除。公开方法签名
`SearchIndex.search(): Promise<readonly SearchHit[]>` 不变，`tsc` 会把该声明一并 emit 到
`dist`，消费方拿到的形状完全一样。

## 5. 依赖图，前后

```
前：core ─┬── ai ── eval
         ├── memory ── agent        ← agent 依赖 memory（渲染）
         └── storage

后：core ─┬── ai ── eval
         │   └── ./agent            ← 只依赖 core
         ├── memory ── (bench 用 ./agent，dev)
         └── storage

dev 边（测试与 bench）：
  memory --dev--> {ai, eval, storage}
  （ai 不再有兄弟 dev 边）
```

## 6. 门禁

| 门禁 | 结果 |
| --- | --- |
| `cortex-ai` typecheck | 通过 |
| `cortex-ai` test | **414 / 414**，覆盖率 100/100/100/100 |
| `cortex-memory` typecheck | 通过（含 `tsconfig.bench`） |
| `cortex-memory` test | **1,710 / 1,710** |
| `cortex-eval` typecheck | 通过 |
| `export-census --check` | **0 new orphans** |
| `cortex-ai` lint | 通过 |
| `pnpm check` | 见 §7 |

`entry-surface.test.ts`（断言 ai 恰好三个导出面）在合并后**变红**，这是它被写出来的目的。
处置是把它改为四个并写明第四条依赖故事，而不是放宽断言。

## 7. 仍未做的事

1. `pnpm check` 全仓复跑（本次改动只影响了 ai / memory / eval / 文档 / 覆盖率基线）。
2. `multiStep` 仍未接进评测臂——**这是上一轮就记着的缺口，合并没有修它**。
   合并改变的是"这个机制住在哪个包里"，不改变"它从没被派发过"。
3. `docs/ANALYSIS-AGENT-BOUNDARY-AND-MEMCOG.md` §1.3 的代价表需要按本文更新：
   合并的技术障碍已随 B′ 消失，剩下的是"零共同演进"这一条已被用户主动放弃的判据。
