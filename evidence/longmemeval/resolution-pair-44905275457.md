# The rendering form's pair: `resolution` at `raw` against `layered`, one window, `MR`

Run [`44905275457`](https://github.com/AgentiX-E/cortex/actions/runs/44905275457) · workflow
`semantic-carry.yml` · commit `18807fc0` · artifact `semantic-carry-merged` (2,477,493 bytes) and four
shard artifacts.

- Dataset: `longmemeval`, `capability=MR`, `windows=1`, 121 questions, **2 repetitions**, 4 shards
- Pairing: `resolution` — the same cognitive system on both sides, `resolution` at the registered
  `raw` (control) against `layered` (treatment). `review_pass=bare`, `turn_rendering=head`
  (`maxTurnChars=400`), `semanticCarry=off` on both sides
- Artifact agrees: `featureConfig.resolutionPair = true`, `memoryArmConfig.resolution = 'layered'`

## The reading (`tools/read-merged-population.py --windows 1 --pairing resolution`)

Replayed from the four shard artifacts with the repaired `merge-ablation.mjs`, because the merged
artifact uploaded by the run predates `baselineRoleCensuses` / `baselinePromptChars` being carried
through the merge — the run's own merge dropped them, which is defect 3 in §152.11.

```
population: 121 corpora x 1 windows = 121 questions over 4 shards, 2 repetition(s)
whole population: n=121  delta=+7.5000 question(s)  discordant b=6 c=14  McNemar p=0.1153
turns median 199 -> 208  (+4.5%)
chars median 48334 -> 45813  (-5.2%)
F3 fail: turns +4.5% is below the +20% floor, so the room did not buy more events and this family closes
```

| quantity | control (`raw`) | treatment (`layered`) | Δ |
| --- | ---: | ---: | ---: |
| correct answers / 242 | 192 (79.34%) | 207 (**85.54%**) | **+6.20 points** |
| question-level mean (121 × 2) | 96.00 | **103.50** | **+7.50 questions** |
| paired flips | — | 14 gained / 6 lost | **+8** |
| exact McNemar, two-sided | — | — | **p = 0.1153** |
| per-run flips | — | run 0: +5, run 1: +10 | **both positive** |
| turns median | 199 | 208 | +4.5% |
| chars median | 48,334 | 45,813 | **−5.2%** |
| turns total | 24,169 | 25,242 | +4.4% |
| chars total | 5,845,652 | 5,576,752 | **−4.6%** |
| questions with more turns | — | **114** more, 2 fewer, 5 same | — |

## Cost

| side | prompt tokens | completion | cache-hit share | CNY (0.2 / 2 / 3 per M) |
| --- | ---: | ---: | ---: | ---: |
| control | 3,092,034 | 48,726 | **98.5%** | 0.85 |
| treatment | 3,102,492 | 47,733 | **53.4%** | 3.36 |
| total | 6,194,526 | 96,459 | — | **4.21** (projection 1.73) |

Prompt tokens grew 0.3% and the bill grew 3.0×, the same cache effect the boundary clock's pair measured
at 4.28×: a mechanism that changes every capped turn invalidates the provider's prefix cache.

## What the criteria say, and what they do not

`F3` **fails** on both clauses (turns +4.5% against a +20% floor; chars −5.2% against a ±2% band), so
`C7`'s density family closes — `RETRACTIONS.md` entry 6. `F4`'s primary clause passes (103.50 ≥ 101.25,
`up − down = +8 ≥ −3`); its secondary clause misses on the mean (103.50 < 104.25) and passes on flips.

The two facts are consistent only if the mechanism did something other than what it claims: characters
**fell** while turns rose slightly, so the room was **reallocated by relevance** rather than densified.
`C8` registers that hypothesis with criteria written after this reading but before its own
(`03-execution-plan.md` §14.146).

## What this artifact does not carry

`F2` (non-capped routes byte-identical) is unreadable here: the population is `MR`, which is a capped
route (`maxTurnCharsRoutes=multi-session,temporal`). `F1`'s "90/500 digests changed" needs both sides'
digests and the roster holds one per question. Both are carried by `resolution.test.ts`'s byte
assertions instead, as the pre-registration says.
