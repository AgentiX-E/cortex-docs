#!/usr/bin/env python3
"""Round 204: every mechanism in the queue, against the bar its own population sets.

Each bar is the *most* a mechanism could buy, in points on the 500-question suite. The tick at the end of the
bar's group is the smallest true difference that population resolves at 80% power. A bar shorter than its
tick cannot be certified here whatever it does — which is why nineteen rounds of dispatches produced null
results that were arithmetically correct and evidentially empty.

Sources: docs/MEASURE-RESOLUTION-WALL.md §2 (ceilings, and the `MR`/`KU` floors), docs/MEASURE-REACHABLE-HEADROOM.md
§2 (self-consistency 1.40, numeric institution 1.20), docs/MEASURE-COST-LEVER.md §2 (the per-route room, 1.05),
SOTA-BASELINE.md (the 2.2-point gap to 95.6).
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT = "/workspace/charts/cortex-detectability-2026-11-26.png"

INK = "#1b1b1f"
MUTED = "#6b6b74"
CORTEX = "#c1121f"
GREY = "#8d99ae"
GREEN = "#2a9d8f"
GRID = "#e4e6ea"
PAPER = "#fbfbfc"

# (label, ceiling in points, floor in points, family)
ROWS = [
    ("stale-value selection (H2), KU", 8.33, 10.52, "queue"),
    ("the same including the decline, KU", 9.72, 10.52, "queue"),
    ("under-count repair, MR", 4.96, 9.37, "queue"),
    ("entity grouping (H3), MR", 3.31, 9.37, "queue"),
    ("decline repair (E3.2), MR", 3.10, 9.37, "queue"),
    ("deterministic summation, MR", 1.86, 9.37, "queue"),
    ("self-consistency, 3 votes, MR", 1.40, 9.37, "measured"),
    ("numeric institution, MR", 1.20, 9.37, "measured"),
    ("per-route room, suite", 1.05, 9.37, "measured"),
]

fig, ax = plt.subplots(figsize=(11.4, 6.6), dpi=200)
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)

y = list(range(len(ROWS)))[::-1]
for yi, (label, ceiling, floor, family) in zip(y, ROWS):
    color = CORTEX if family == "measured" else GREY
    ax.barh(yi, ceiling, height=0.52, color=color, alpha=0.92, zorder=3)
    # The bar's own value, at the end of the bar.
    ax.text(
        ceiling + 0.12,
        yi,
        f"{ceiling:.2f}",
        va="center",
        ha="left",
        fontsize=9.4,
        color=INK,
        zorder=5,
    )
    # The population's resolution, drawn as a tick on the row rather than a full line: two populations are in
    # play and a single vertical rule would misattribute one of them.
    ax.plot(
        [floor, floor],
        [yi - 0.31, yi + 0.31],
        color=INK,
        lw=2.0,
        solid_capstyle="butt",
        zorder=4,
    )
    ax.text(
        floor + 0.12,
        yi + 0.30,
        f"bar to clear: {floor:.2f}",
        va="bottom",
        ha="left",
        fontsize=8.6,
        color=MUTED,
        zorder=5,
    )

ax.set_yticks(y)
ax.set_yticklabels([row[0] for row in ROWS], fontsize=10.2, color=INK)
ax.set_xlim(0, 13.0)
ax.set_ylim(-0.9, len(ROWS) - 0.15)
ax.set_xlabel("most a mechanism could buy, in points on the 500-question suite", fontsize=11, color=INK)

ax.axvline(2.2, color=CORTEX, lw=1.3, ls=(0, (5, 4)), zorder=2)
ax.text(
    2.32,
    len(ROWS) - 0.55,
    "the whole gap to 95.6  ·  2.2 points  ·  11 questions",
    fontsize=10,
    color=CORTEX,
    va="top",
    zorder=6,
)

ax.set_title(
    "Every queued mechanism is shorter than the bar its own population sets",
    fontsize=14.5,
    color=INK,
    pad=44,
    loc="left",
)
ax.text(
    0,
    1.022,
    "Longest bar in the queue is 92% of the lowest bar to clear. A null result here is the denominator, not the mechanism.",
    transform=ax.transAxes,
    fontsize=9.9,
    color=MUTED,
)

ax.grid(True, axis="x", color=GRID, lw=0.9, zorder=0)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(axis="y", length=0)

ax.legend(
    handles=[
        Line2D([], [], color=GREY, lw=7, label="proposed, never dispatched"),
        Line2D([], [], color=CORTEX, lw=7, label="dispatched and closed with a null"),
        Line2D([], [], color=INK, lw=2, label="resolution of that population (80% power)"),
    ],
    loc="upper center",
    bbox_to_anchor=(0.5, -0.115),
    ncol=3,
    frameon=False,
    fontsize=9.6,
)

fig.tight_layout()
fig.savefig(OUT, facecolor=PAPER)
print(OUT)
