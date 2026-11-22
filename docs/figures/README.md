# Figures

Five figures, two data files, one renderer. Every number in the pictures comes from `landscape.json` or
`matched-model.json`, which carry a `source` and a measurement unit per row — the point of drawing them at all is
that a reader can go back and check.

```bash
python3 docs/figures/plot-landscape.py     # rewrites all five into this directory
```

`landscape.json` holds published rows: a vendor's or a paper's own figure under its own answer model. `matched-model.json`
holds the rows this repository measured itself, one dispatch per system, and is kept separate on purpose — mixing the
two in one file would make a figure caption have to explain which half of a plotted point came from whom.

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
| `fig-longmemeval-room-axis.png` | room (characters) × `MR` accuracy, and room × prompt tokens per question | the room axis of the registered arm: 16 short questions become 1, accuracy moves 0.4 points, tokens move 21% |
| `fig-longmemeval-matched-model.png` | prompt tokens the system caused to be read (log) × accuracy | the three competitors as **this repository** measured them: one model for the system and the reader, one judge, one sample. Drawn from `matched-model.json`, whose rows carry `n` — two of them are n=2 |

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
4. **The axis follows the data, and a fixed axis deletes systems.** The limits used to be written down
   (`2,200`-`9,000`), which was right for the six rows that existed then and silently **clipped** the next two
   that arrived above 9,000. A point outside the axis is not a point in a surprising place -- it is an absent
   system, and the figure's whole job is to show which systems exist at which cost. Limits and ticks are now
   derived from the rows.
5. **When two labels collide, one changes side rather than both moving up.** `Maximem Synap` (95.6 at 7,400) and
   `Mem0` (94.4 at 6,787) are 1.2 points and 9% of an axis apart. The first repair pushed both labels above
   their markers, which moved the collision from the markers to the text: one system's name was then printed
   across another's. The second repair alternates sides within a crowded cluster, so each label leaves its own
   marker visible.

6. **One row is one run.** The cortex row carried `91.15` from run `44317789307` and `7,448` tokens from run
   `44017278305`: two runs, one row, and no reader could tell from the picture. That is the same defect class as
   `S17`'s pair -- a number beside a label that names a different provenance -- and it is why the row now carries
   `91.25` and `7,448`, both read out of `costEfficiency` in the same artifact (`S16`, run `44017278305`), with
   the two field names written into the row's `source`. A figure whose two coordinates come from two experiments
   is a position that no system ever occupied.

7. **A label is placed by measurement, not by a rule.** The first two attempts at keeping names off each
   other were rules over data coordinates -- alternate sides when two rows are within 1.8 points, then the
   same test with a cost ratio added. Both failed the moment the row set grew: `Perpetuity` (94.0 at 3,600)
   and `Mem0` (94.4 at 6,787) pass every such test and still printed as `PerpetuMem0`, and `KITE` at 1,600
   tokens sits in the axis's leftmost eighth, where the left-hand escape put its name off the canvas. Where
   text lands is a display-coordinate question, so the renderer now draws a candidate, asks for its bounding
   box, and keeps it only if it hits nothing already placed and stays inside the axes. The same rewrite moved
   the cost notes out of the bars and into a footnote: with `Hindsight` at 43,600 and `KITE` at 1,600 the
   short bars are nine pixels tall, and a rotated note inside one is a white smear over the bar it describes.

## What the figures do not show

- **Recall versus accuracy.** No figure mixes them.
- **Cost as money.** Tokens are what a provider publishes; a currency figure would need a rate card this
  repository does not own (`cortex-ai/src/usage.ts` states the same rule for the artifact).
- **A trend.** These are readings from different days on different stacks. The ranking figure groups by reader
  precisely so that no one reads the ordering as a progression.

## The rows added on 2026-11-20

Four rows arrived from an external re-check: Perpetuity (94.0 at 3,600), Graphon Labs (92.8 at 15,100), Honcho
(90.4 at 11,600) and Maximem Synap (95.6 at 7,400). Perpetuity is the one worth looking at twice: the cheapest
published path to 94 on this suite, at half this arm's bill. `05-competitor-analysis.md` §30 draws the
consequence, and it is not "we are behind" -- it is that the lever is which text the frame holds rather than how
much of it there is.

`Graphon` publishes two figures for one system (96.2 best case, 92.8 with a cost). Only the row that names a
cost is entered: a single row cannot hold a best case and a bill without implying they happened together.

## `fig-longmemeval-claim-vs-measurement.png`

The only figure here that draws a number twice for the same system: the claim and an independent
re-run, joined. Every other figure ranks claims; this one shows that the ranking is a ranking of
claims, because the same Mem0 reads 94.4 (vendor), 71.0 (HEAMS) and 65.7 (Lobu), and the same Zep
reads 90.2 and 71.2. The vertical dashed line is the published oracle ceiling for the suite, which
is the number that decides whether a claim is possible at all. `cortex` carries a single marker
because no third party has re-run it — the absence is drawn rather than described.
Generated by `tools/render-claim-gap.py` from `landscape.json`'s `independent` block.
