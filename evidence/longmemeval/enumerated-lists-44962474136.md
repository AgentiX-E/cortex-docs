# `ask=enumerated` 的 `Step 1` 列表读数（run `44962474136`）

> 命令：`python3 tools/readout-arm-run.py /tmp/enum/benchmark-cortex-memory-ablation-report.json --lists`
> 产物：`benchmark-cortex-memory-ablation-report.json`（206 MB，四重复，500 题）
> 读数日期：2026-11-22。工具是 `--lists` 那个分支，不是新写的脚本。

## 1. 原始输出

```
what Step 1 held (MR: items listed, the number stated, the gold)
  correct  n= 94  median list 2.0  median truncated turns 9.0%
  wrong    n= 27  median list 2.0  median truncated turns 10.7%
  correct with a parsable Step 1 list: 72 of 94

   items  trunc    stated      gold  flags
       2    13%         2         3  counts its list
       0    11%         1         2
       2    10%         2         3  counts its list
       1    11%         1  I attended four movi  counts its list
       0    11%         2         3
       6    14%         6  I attended three wed  counts its list
       0     9%         3         4
       5     9%         5         4  counts its list
       5     8%         5  I viewed four proper  counts its list
       3    12%   Walmart  Thrive Market
       2    10%         2         4  counts its list
       0    12%  Cannot be determin  5 days. 6 days (incl
       4     9%  Step 1 - 2023/03/2  $3,750
       0    11%         4  I replaced or fixed
       2    12%       700      $720
       3    18%       375      $495
       2     7%         2         3  counts its list
       2    16%         8  10 years
       2    11%        22        23
       0     9%  Cannot be determin        20%
       0    10%  Cannot be determin        11
       1    11%       300       100
       2     9%      1456     1,998
       2    17%        10         7
       0     9%         3   4 days.
       0     7%  Cannot be determin       856
       1     9%         1         2  counts its list

  counts its list: 9 of 27 — the rest aggregate a short list into a sum or a duration, which is why
  "arithmetic" was the wrong name for this.
```

## 2. 三个能读出来的事实

1. **27 道错题里 9 道「数了自己的列表」**：`items 2 → stated 2 → gold 3`、`items 1 → stated 1 →
   gold 2`、`items 5 → stated 5 → gold 4`。它没算错，它**列漏了然后把自己的漏列当成答案**。
2. **另外 18 道把一个短列表聚合成和或时长**：`items 2 → 700 → gold $720`（差的 20 不在列表里）、
   `items 3 → 375 → gold $495`（120 不在列表里）、`items 2 → 1456 → gold 1,998`（542 不在列表里）。
   所以「算术失败」这个命名是错的：**聚合是对的，被聚合的列表不全**。
3. **列表长度不区分对错**：correct 组中位列表 2.0 项、wrong 组也是 2.0。所以不能拿「列表短」当
   判据；能区分的是**列表里有没有金标所需的那一项**，而那正是 `carried` 与 `goldRanks` 已经在记的东西。

## 3. 它对本轮结论的影响

**加强**：§156.6 用手读的两道题（`0a995998` 三项列两项、`2ce6a0f2` 四项列两项）不是特例，是 27 道里
9 道的同一形态。`MR` 的差距是注意力/枚举完整性问题，不是算术能力问题。

**限定**：`truncated turns` 在 wrong 组 10.7%、correct 组 9.0%，两者只差 1.7 个百分点——这是
`maxTurnChars=400` 与准确率**无关**的第二个独立读数，与 §156.5 的「0 题金标数字在 400 字符之后」
同向。

**不支持的**：这份读数**不能**证明「让读者看第二次」一定能救回这 9 题。它只说明这 9 题的
`Step 1` 短于金标所需的项数，而短的原因可能是没找到（检索）、没读完（注意力）或没数（聚合）。
`PREREGISTRATION-MULTI-STEP.md` §6 的 falsifier 正是为分开这三种而写的。
