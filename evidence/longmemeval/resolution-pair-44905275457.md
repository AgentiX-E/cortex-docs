# 渲染形态的配对：`resolution` 的 `raw` 对 `layered`，一个窗口，`MR`

运行 [`44905275457`](https://github.com/AgentiX-E/cortex/actions/runs/44905275457) · 工作流
`semantic-carry.yml` · commit `18807fc0` · 产物 `semantic-carry-merged`（2,477,493 字节）加四份分片产物。

- 数据集：`longmemeval`，`capability=MR`，`windows=1`，121 道题，**2 遍重复**，4 个分片
- 配对方式：`resolution` —— 两侧是同一个认知系统，`resolution` 取注册值 `raw`（对照）对
  `layered`（处理）。`review_pass=bare`、`turn_rendering=head`（`maxTurnChars=400`）、
  两侧 `semanticCarry=off`
- 产物自述一致：`featureConfig.resolutionPair = true`，`memoryArmConfig.resolution = 'layered'`

## 读数（`tools/read-merged-population.py --windows 1 --pairing resolution`）

用修好的 `merge-ablation.mjs` 从四份分片产物重放，因为该运行上传的合并产物早于
`baselineRoleCensuses` / `baselinePromptChars` 被带过合并这一步——那次运行自己的合并把它们丢了，
即 §152.11 的缺陷 3。

```
population: 121 corpora x 1 windows = 121 questions over 4 shards, 2 repetition(s)
whole population: n=121  delta=+7.5000 question(s)  discordant b=6 c=14  McNemar p=0.1153
turns median 199 -> 208  (+4.5%)
chars median 48334 -> 45813  (-5.2%)
F3 fail: turns +4.5% is below the +20% floor, so the room did not buy more events and this family closes
```

| 量 | 对照（`raw`） | 处理（`layered`） | Δ |
| --- | ---: | ---: | ---: |
| 正确数 / 242 | 192（79.34%） | 207（**85.54%**） | **+6.20 点** |
| 题级均值（121 × 2） | 96.00 | **103.50** | **+7.50 题** |
| 配对翻转 | — | 得 14 / 失 6 | **+8** |
| 精确 McNemar，双侧 | — | — | **p = 0.1153** |
| 逐遍翻转 | — | 第 0 遍 +5，第 1 遍 +10 | **两遍都为正** |
| turns 中位 | 199 | 208 | +4.5% |
| chars 中位 | 48,334 | 45,813 | **−5.2%** |
| turns 合计 | 24,169 | 25,242 | +4.4% |
| chars 合计 | 5,845,652 | 5,576,752 | **−4.6%** |
| turn 变多的题 | — | **114** 道变多、2 道变少、5 道不变 | — |

## 成本

| 侧 | prompt token | completion | 缓存命中占比 | CNY（0.2 / 2 / 3 每百万） |
| --- | ---: | ---: | ---: | ---: |
| 对照 | 3,092,034 | 48,726 | **98.5%** | 0.85 |
| 处理 | 3,102,492 | 47,733 | **53.4%** | 3.36 |
| 合计 | 6,194,526 | 96,459 | — | **4.21**（投影 1.73） |

prompt token 只涨 **0.3%**，账单涨 **3.0 倍**——与边界时钟那对测到的 4.28 倍是同一个缓存效应：
**一个改动每一条被截断轮次的机制，会让供应商的前缀缓存整段失效。**

## 判据说了什么，没说什么

`F3` **两个子句都不成立**（turns +4.5% 对 +20% 地板；chars −5.2% 对 ±2% 带），所以 `C7` 的密度族
关闭——`RETRACTIONS.md` 第 6 条。`F4` 的主子句通过（103.50 ≥ 101.25，`up − down = +8 ≥ −3`）；
次子句在均值上未达（103.50 < 104.25），在翻转上通过。

这两件事只有在「机制做的不是它声称的事」时才自洽：**字符降了而轮次微升**，所以房间是被
**按相关性重新分配**了，不是被加密了。`C8` 把这个假设登记成判据——判据写在这份读数之后、
在它自己的读数之前（`03-execution-plan.md` §14.146）。

## 这份产物不带的东西

`F2`（未被截断的路由逐字节相同）在这里读不出来：族群是 `MR`，而 `MR` 是一条被截断的路由
（`maxTurnCharsRoutes=multi-session,temporal`）。`F1` 的「500 个摘要里有 90 个变了」需要两侧的摘要，
而名册每题只存一个。两者都由 `resolution.test.ts` 的字节断言承载，正如预登记所写。
