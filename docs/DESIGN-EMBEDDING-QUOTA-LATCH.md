# 设计：嵌入账户的进程级闩锁（`latchQuota`）

> 本文件写于实现之前、读数之前。它记录的是**为什么长成这样**，不是它跑出了什么。
> 判据与验收条件登记在 `PREREGISTRATION-TURN-WINDOW-MATCH.md` §6.4 / §6.5。

## 1. 问题，用一次失败的数字说

派发 `44354315890` 在 28 分钟时死于 `EmbeddingQuotaExhaustedError`（`429`，供应商码 `1113`，
「余额不足或无可用资源包,请充值。」）。产物里的传输台账是：

```
attempts 3129 / calls 3129 / cleanCalls 2698 / refusedCalls 431 / retriedCalls 0
```

`retriedCalls = 0` 说明重试层没有重试——它认出了这个错误不该重试，这一点是对的。431 次被拒是
431 次**独立的**调用。第一次被拒就把「这个账户不能付钱」确立为事实，后面 430 次问的是同一个供应商
同一个问题，收到的也是同一个答案。

**这 430 次往返是这次失败里唯一可以纯代码消除的部分**，也是本轮唯一的目标。分数不会因此改变：
一个不能付钱的账户无论闩不闩都测不出东西。

## 2. 四个决定

### 2.1 闩锁，而不是策略

产品侧已经有策略：`SearchIndex` 的 `onEmbedFailure` 可以在向量通道失败后退化成词法评分，并把
`embedDegraded` 报出来。参考侧**刻意不用它**。一次 pass 中途降级会让两条配方混进同一个准确率，
而那个数字在产物里看起来像一个结果——这比一次当场死掉的运行危险得多，因为死亡至少是可见的。

所以闩锁不做选择。它只是**拒绝花钱**，并且用同一个类型化错误持续拒绝，于是它上面每一层的行为
一个字节都没变：`runWorker` 照旧 `throw`，`main().catch` 照旧写失败记录，进程照旧非零退出。
唯一改变的是账单。

### 2.2 属于 harness，不属于产品

一次 benchmark 跑几个小时，账户不可能在运行中途被充值，所以「这不会变好」对它的余生成立。
产品进程是另一种：运维可以在它运行时充值，闩锁会把十分钟的故障变成一个进程生命周期内的永久故障。
产品的按次决策（`onEmbedFailure`）是对的形状，闩锁是测量的对形状。

这一条同时回答了需求⑯：这里没有「评测侧证明了却没出货」的能力，因为被证明的是一个**测量完整性**
属性，不是一个用户能力。

### 2.3 读数是被发布出去的，不是被返回的

失败记录写在 `main().catch(...)` 里，位于 `main` 作用域之外。同一个问题 `resolveEmbeddingProvenance`
已经解决过一次：来源信息是环境的纯函数，所以可以在失败路径上重新求值。闩锁的计数是**状态**，
不能重新求值。所以工厂在建客户端时把读数的闭包发布到一个模块级槽位，失败路径读取它。

这是本仓里模块级状态的既有模式（`embeddingSourceCounters`、`retryStats()`、`providerRefusals()`、
`scorerChannelStats()`），前提也相同：一个进程跑一个 run。

### 2.4 一个对象，不是一个布尔加三个可空字段

第一版把 `latchedAtCall`、`latchedStatus`、`detail` 分开存，然后在抛错处写
`latchedAtCall ?? 429` 和 `detail ?? ''`；读数类型则是一个 `latched: boolean` 加三个
`| null` 字段。覆盖率显示这些兜底的右臂**一次都没执行**——因为三者是在同一个块里一起写入的，
`??` 在这里是恒等式。

不可达的兜底不是免费的：它会静默吸收将来的越界，而它上面的算术永远不被测试。改成单一对象
`closure: { atCall, status, detail } | null` 之后，「已闩锁」「有状态码」「有原文」三件事变成
一件事，类型里不再存在「闩上了但没有状态码」这个状态，所有消费方的兜底一并消失。
这与上一轮在 `resolution.ts` 删掉 `truncateCodePointSafe` 是同一类修复，间隔一天出现两次。

## 3. 三个状态，三条不同的记录行

| 状态 | 记录行 | 它说的是什么 |
| --- | --- | --- |
| 没有闩锁读数（`undefined`） | 不打印 | 调用方没有报告任何嵌入客户端 |
| `null` | `embedding: no client was built before the failure` | 运行在建客户端之前就死了（数据集没解析出来） |
| 未关闭 | `embedding: no quota refusal in 3129 call(s)` | 账户是好的，而且这个数字让「好」可读 |
| 已关闭 | `embedding: LATCHED at call 1 (status 429) — 1 provider refusal(s), 430 refused without a request` | 事故 |

未关闭那一行在**每一次**失败上都打印，理由与 `benchmark.ts` 的拒绝行相同：只在事故时出现的行，
让读者无法区分「账户没问题」和「这条记录早于这个计数器」。

## 4. 两个实现期发现

### 4.1 装饰器必须转发 `identity()`

`EmbeddingSpace` 拒绝查询一个**非空**且空间未声明的索引。所以一个丢掉可选 `identity` 的装饰器会把
进程里每一个向量索引变成不可检索的——不是慢，是**拒绝服务**。转发因此是承重的而不是整洁的；并且
只在内部模型有时才挂 `identity`，让包装器的「没有」与模型的「没有」一致，而不是发明一个返回
`undefined` 的方法去对抗一个禁止 `undefined` 的类型。

### 4.2 第三个不可达兜底：`detail === ''`

`closure` 里的 `detail` 第一版写成 `error.detail === '' ? error.message : error.detail`。
覆盖率显示 `''` 那一臂从未执行，理由是构造上不可能：`isQuotaExhausted` 要求响应体**非空**才认这个
错误，所以 `OpenAIEmbedding` 造不出 `detail` 为空的配额错误。这已经是本轮第三个同类修复
（两个 `??` + 这一个），于是它被删掉而不是被测试——用一个人造的错误对象去覆盖它，测的是谎话。

### 4.3 `instanceof` 断言被 `identity()` 断言替代

工厂现在对两个分支都套闩锁，所以 `createEmbeddingWithProvenanceFromEnv` 返回的对象是装饰器，
`toBeInstanceOf(OpenAIEmbedding)` 必然失败——但它失败的**原因**不是行为变了。九个断言（
`embedding-provenance.test.ts` 五处、`report-runner.test.ts` 四处）改成了 `identity()` 相等，
这是同一个事实更强的表述：`identity()` 是 `EmbeddingSpace` 真正读取、缓存被拒绝时真正比较的字段，
一个把后端名字写错的客户端在 `instanceof` 下是看不出来的。

## 5. 它不做什么

| 不做 | 理由 |
| --- | --- |
| 重试第一次拒绝 | 重试层已经决定不重试这个类型，那是正确的 |
| 降级到词法 | 会把两种配方混进同一个准确率（§2.1） |
| 覆盖 LLM 侧的配额 | DeepSeek 的余额与嵌入余额是两个账户；同一个论证，另一个类型，另一轮 |
| 把读数写进 `benchmark-cortex-memory-partial.json` | 那份 JSON 由 `attachPartial` 从 `error.partial` 构造，计数产生在传输层，把它塞进去要第二条通路；`benchmark-error.log` 是所有失败摘要的唯一归处，重复一份就有两处会漂移 |
| 给产品加闩锁 | §2.2 |

## 6. 验收

| # | 断言 | 位置 |
| --- | --- | --- |
| V1 | 第一次拒绝之后，第二次调用**不触达**内部模型（假客户端的调用计数不变） | `embedding-latch.test.ts` |
| V2 | 本地拒绝是同一类型、同一 `status`，消息里保留第一次拒绝的供应商原文 | 同上 |
| V3 | 非配额错误不关闭闩锁，下一次调用仍然到达供应商 | 同上 |
| V4 | 闩锁关闭时已在途的第二个请求计为**供应商拒绝**，且不移动边界 | 同上 |
| V5 | `dimension()` 与 `identity()` 被转发；内部模型没有 `identity` 时包装器也没有 | 同上 |
| V6 | 三个状态各打印一行，未关闭那一行带调用数 | `bench-failure.test.ts` |
| V7 | 工厂的两个分支都装了闩锁（含离线 hash 回退） | `embedding-provenance.test.ts` |
| V8 | `embedding-latch.ts` / `bench-failure.ts` / `embedding-factory.ts` 四维覆盖率 100% | 本轮追踪报告 |
| V9 | 失败的四个状态（无客户端 / 未关闭 / 已关闭 / 未提供）各有一行，且互不混淆 | `bench-failure.test.ts` |
MD
