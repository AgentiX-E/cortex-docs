#!/usr/bin/env python3
"""Round 205: the bar is a conversion rate, not a score gap.

Every table this campaign ordered its queue by compared a mechanism's **ceiling in points** against a
**floor in points**. Round 204's detectability chart did that too, and the floors in it (9.37 on `MR`,
10.52 on `KU`) are `2.8016 * sqrt(p(1-p)/n)` -- the *unpaired* minimum detectable effect at 80% power --
while every dispatch in the campaign is read by a **paired** exact McNemar, whose rejection region starts
at six discordant questions all one way (`2 * 0.5**6 = 0.03125`). `tools/queue-floor.mjs` was written to
name exactly that substitution and its self-test pins both numbers.

Restated in the registered test's own units, the question is not "is the ceiling above the floor" but
**"how completely must a mechanism work"**: with `R` members in its class and no leaks, the reading is
significant at 80% power when `P(Bin(R, q) >= 6) >= 0.8`.

    R = 4     no q reaches it: `Bin(4, 1) >= 6` is false at every q, so no outcome of this dispatch can
              produce p <= 0.05 whatever the mechanism does
    R = 6     q >= 96.3%
    R = 7     q >= 88.0%

`R` is the conversions the mechanism has available, which is the reachable population and not always the
class size: the under-count repair's class holds six questions and four of them carry a gold turn outside
the window, so it has three.

Five of the seven rows cannot be certified at any conversion rate. Of the two that can, one was dispatched
twice (`5` up, `5` down against a bar of 88%) and the other became visible only this round. Sources: docs/MEASURE-RESOLUTION-WALL.md §2 (ceilings),
docs/MEASURE-REACHABLE-HEADROOM.md §2, and tools/queue-floor.mjs (the floor the criterion uses).
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

OUT = "/workspace/charts/cortex-conversion-floor-2026-11-27.png"

INK = "#1b1b1f"
MUTED = "#6b6b74"
CORTEX = "#c1121f"
GREY = "#8d99ae"
GRID = "#e4e6ea"
PAPER = "#fbfbfc"

# (label, class size, required conversion or None when no rate reaches the rejection region, outcome)
ROWS = [
    ("stale-value + the decline, KU", 7.0, 0.880, "dispatched twice: 5 up, 5 down"),
    ("stale-value selection (H2), KU", 6.0, 0.963, "the same dispatch"),
    ("delivery institution, suite", 6.0, 0.963, "invisible before §205"),
    ("under-count repair, MR", 3.0, None, "3 of its 6 reachable"),
    ("entity grouping (H3), MR", 4.0, None, ""),
    ("decline repair (E3.2), MR", 3.75, None, ""),
    ("deterministic summation, MR", 2.25, None, ""),
]

fig, ax = plt.subplots(figsize=(12.2, 6.9), dpi=200)
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)

y = list(range(len(ROWS)))[::-1]
for yi, (label, size, need, outcome) in zip(y, ROWS):
    reached = need is not None
    if reached:
        ax.barh(yi, need, height=0.5, color=CORTEX, alpha=0.92, zorder=3)
        # Inside the bar rather than after it: at 96% a label hung off the end lands on the outcome column,
        # and the two numbers a reader compares are then printed on top of each other.
        ax.text(
            0.014,
            yi,
            f"{need:.1%}",
            va="center",
            ha="left",
            fontsize=10.2,
            color="white",
            fontweight="bold",
            zorder=4,
        )
    else:
        # The region no rate reaches, drawn as a hatch rather than a bar: a bar would read as a rate the
        # mechanism could be pushed to, and the point is that the rejection region is outside this class.
        ax.barh(yi, 1.0, height=0.5, color=GREY, alpha=0.26, hatch="///", edgecolor=GREY, zorder=3)
        ax.text(
            0.5,
            yi,
            f"no rate reaches it — {size:g} members, the test needs 6",
            va="center",
            ha="center",
            fontsize=9.4,
            color=MUTED,
            style="italic",
            zorder=4,
        )
    ax.text(
        -0.012,
        yi,
        label,
        va="center",
        ha="right",
        fontsize=10.2,
        color=INK if reached else MUTED,
    )
    if outcome:
        ax.text(
            1.016,
            yi,
            outcome,
            va="center",
            ha="left",
            fontsize=9.2,
            color=MUTED,
            style="italic",
        )

ax.set_yticks([])
ax.set_xlim(0, 1.0)
ax.set_ylim(-0.75, len(ROWS) - 0.25)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0%}"))
ax.tick_params(axis="x", colors=MUTED, labelsize=9.6, length=0)
ax.grid(axis="x", color=GRID, linewidth=0.9, zorder=0)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.set_xlabel(
    "share of its class a mechanism must convert for a p ≤ 0.05 reading at 80% power (no leaks)",
    color=MUTED,
    fontsize=10.2,
    labelpad=10,
)

fig.text(
    0.006,
    0.965,
    "Five of the queue's seven mechanisms cannot be certified at any conversion rate",
    fontsize=15.4,
    color=INK,
    fontweight="bold",
    ha="left",
    va="top",
)
fig.text(
    0.006,
    0.918,
    "Rejection needs six discordant questions all one way -- a p of 0.03125. A class smaller than six has "
    "no outcome that reaches it, whatever the mechanism does.",
    fontsize=10.2,
    color=MUTED,
    ha="left",
    va="top",
)

legend = [
    Patch(facecolor=CORTEX, alpha=0.92, label="certifiable: six or more conversions available"),
    Patch(facecolor=GREY, alpha=0.26, hatch="///", edgecolor=GREY, label="not certifiable at any rate"),
]
ax.legend(
    handles=legend,
    loc="upper center",
    bbox_to_anchor=(0.5, -0.085),
    ncol=2,
    frameon=False,
    fontsize=9.8,
    handlelength=1.6,
)
fig.subplots_adjust(left=0.245, right=0.795, top=0.845, bottom=0.185)
fig.savefig(OUT, facecolor=PAPER)
print(OUT)
