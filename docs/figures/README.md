# Figures

Three figures, one data file, one renderer. Every number in the pictures comes from `landscape.json`, which
carries a `source` and a measurement unit per row — the point of drawing them at all is that a reader can go
back and check.

```bash
python3 tools/render-landscape.py          # rewrites all three into this directory
```

## Why three and not one

The review asks for accuracy against cost, split by leaderboard, plus a combined view. A single scatter would
have to place three incommensurable units on one axis:

| artifact | unit | what it measures |
| --- | --- | --- |
| QA accuracy on LongMemEval-S | percent over 500 questions | end to end, reader and judge included |
| recall@k on a sub-capability | percent, recall only | the retriever, with no reader |
| tokens per query | tokens | what one answer costs |

That is the comparison this project has retracted twice (`RETRACTIONS.md` §2, §3): a per-capability percentage
from a local grouping cannot be subtracted from one built on the published split, and a recall figure cannot be
read as an answer accuracy. So the figures stay inside one unit per axis, and the `MS`/`KU`/`TR` comparison
against Supermemory's `recall@20 with aggregation` is **not** drawn — it is a different measurement and the
document that discusses it says so in words.

## The files

| file | axes | what it answers |
| --- | --- | --- |
| `fig-longmemeval-accuracy-vs-cost.png` | left: tokens per query (log) × accuracy; right: systems that publish no cost, on the same accuracy axis | where cortex sits when both numbers exist — the only combined view |
| `fig-longmemeval-accuracy-ranking.png` | accuracy, grouped by answering reader | the same memory system spans 90.2 to 98.4 as the reader changes |
| `fig-longmemeval-cost-per-query.png` | tokens per query | "most accurate" and "cheapest" are different winners, and cortex is neither |

## Three rules the renderer follows, and the defects behind them

1. **An unpublished cost is not a position.** Systems without a cost figure are drawn on a second panel that
   shares the accuracy axis. The first version put them in a grey band across the top, which placed them at an
   accuracy they do not have (the band sat above every point) and pushed its label past the axes.
2. **A bar chart's y axis is a category index, not a quantity.** The second version shared one y axis between a
   scatter and a `barh`, which squashed the scatter's data into the top decile. The right panel now plots a
   marker at each system's accuracy and carries the name in the label.
3. **A crowded label moves; a marker does not.** Three systems lie within 1.9 points of each other (96.8, 96.2,
   94.9). Their labels are pushed down by a minimum spacing with a leader line back to the marker, because
   moving the marker would be a lie about the score.

## What the figures do not show

- **Recall versus accuracy.** No figure mixes them.
- **Cost as money.** Tokens are what a provider publishes; a currency figure would need a rate card this
  repository does not own (`cortex-ai/src/usage.ts` states the same rule for the artifact).
- **A trend.** These are readings from different days on different stacks. The ranking figure groups by reader
  precisely so that no one reads the ordering as a progression.
