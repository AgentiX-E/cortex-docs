# 审计：导出普查按「名字」而不是「导入」认定调用者

**审计对象**：`tools/export-census.mjs` + `packages/cortex-core/src/export-census.ts`
**触发**：第 109 轮（I1 判官跨厂牌），一个新建工具里的本地类名让一条账本分类静默翻转
**结论**：这是一条**真实缺陷**，影响面为「一个未导入的同名标识符即可把孤儿提升为有用例」；本轮不改普查实现（改动会重排 464 行账本），改为**记录 + 在命名上规避**，并把复合判据写进 `--check` 的读法。

---

## 1. 事实

`I1` 需要新工具 `tools/judge-cross-vendor.mjs`。第一版在文件内定义：

```js
class Refusal extends Error {}
```

`cortex-storage` 的 `packages/cortex-storage/src/browser/opfs.ts:33` 导出了：

```ts
export type Refusal = { tier: BrowserTier; reason: string };
```

该类型在账本里被记为 **isolated orphan / `referenced-locally`**（导出、无外部调用者、只在自身文件内被引用）。

新工具落盘后，CI 的 `Verify library` 在 `export-census-gate.test.ts` 上红：

```
expected [ …(463) ] to deeply equal [ …(464) ]
-   "cortex-storage: Refusal",
```

即：**新工具从未 import 过 `cortex-storage`**，但 `cortex-storage: Refusal` 从孤儿集合里消失了。

原因是普查的调用者判定基于**标识符文本**：`tools/` 在它的扫描根内（`readAllSources()` 同时走 `packages/` 与 `tools/`），任何出现 `Refusal` 这个 token 的文件都被当作「有调用者」。

## 2. 为什么这是缺陷而不是配置

| 应有的语义 | 实际的语义 |
| --- | --- |
| 「有调用者」= 某处的导入绑定指向该导出 | 「有调用者」= 仓库里某个文件出现过同名字符串 |
| 判定应当**与语言无关地保守**：拿不准就当孤儿 | 判定**与语言无关地宽松**：同名即调用者 |

两个方向都被打破：

1. **假阳性（本轮）**：一个与 `cortex-storage` 无关的工具里的本地类名，把 `cortex-storage` 的孤儿提升为「有用例」。账本因此少记一条待清偿债务，`--check` 从此对这条名字失去保护。
2. **潜伏的假阴性**：反过来，任何**字符串**里出现某个导出名（文档、注释、测试标题、一个语料 fixture）都可能被算作调用者。仓库里已经存在大量此类文本，说明账本里 `withCaller` 的分母并不精确 —— 只是那些条目**本来就被当成有调用者**，所以从未被追问。

## 3. 本轮采取的处理（以及为什么不是修普查）

**处理**：把本地类改名为 `ComparisonRefused`。理由不是「躲开」，而是**同名遮蔽本身就是坏卫生**：一个工具在局部重新定义另一个包导出的领域类型名，任何读者都会先怀疑它在用那个类型。

同时把这条限制写进这里，并在 `judge-cross-vendor.mjs` 的注释里指回本文，避免下一个人把「改名」误读成「缺陷已修」。

**为什么不在本轮修普查**：

1. 修法是「调用者必须是 import/绑定」，这会把判定从词法变成语法，需要为 `.ts/.mjs/.py/.bench` 四类文件各写解析；
2. 任何一处判定变化都会重排 464 行账本（`orphanClass` + `totals` + `locations`），而账本的用途是**挡住新增孤儿**，一次大重排会让「本轮新增了什么」不可读；
3. 更重要：**修它的正确时机是有第二个证据时**。现在只有一个名字碰撞的实例，修法只能靠推测；等到第二次出现（例如某个语料字符串里的导出名让一条债务消失），修法就有两个必须同时满足的用例。

**记入待办**（不是放弃）：`tools/export-census.mjs` 的调用者判定应改为绑定级；触发条件 = 第二次出现同类翻转。

## 4. 可复现的检查

```bash
# 1) 在任意 tools/*.mjs 里写一行 `class Refusal extends Error {}`
# 2) 跑普查，观察 isolate 集合少一条
node tools/export-census.mjs --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); \
print([s for s in d["orphans"] if "cortex-storage: Refusal" in s])'
# 预期：改动前有输出，改动后为空 —— 而两个版本的源码一个字都没有变
```

## 5. 与「按名字认定」相邻的一条更危险的推论

如果同名即调用者，那么**删除一个导出**时，只要仓库里还有任何文本写着这个名字，账本就永远不会报它是孤儿。也就是说，这个账本能证明「有」而不能证明「没有」。本仓库的 `--check` 只用于「不得新增孤儿」，方向恰好是「证明有」，所以这个缺陷**尚未污染任何已发布结论**；但任何引用 `orphanCount` 当作「未使用导出的总数」的文档，都必须知道它是**上界**而不是计数。

本轮已核对 `docs/` 与 `cortex-docs/docs/` 中不存在把 `orphanCount` 当作精确计数的表述。
