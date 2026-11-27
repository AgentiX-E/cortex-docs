"""The queue after row 0 was executed: price against what each row can decide.

No accuracy number appears in this figure, and that is the point of the round it records: the only quantity
that moved is a *state*, so plotting it on an accuracy axis would manufacture a reading. What is plotted is
what a dispatch of each row costs and whether the row can be dispatched at all.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROWS = [
    ("1. MR 121-question pair (readerSearch=1)", 5.87, "dispatchable"),
    ("2. resolution: raw, same pair", 3.57, "dispatchable"),
    ("3. LoCoMo 300-question subset", 7.28, "dispatchable"),
    ("4. 431-question census, one pass", 10.45, "dispatchable"),
    ("— per-route room on verbatim-acts", 5.81, "demoted"),
    ("— release credentials (outside repo)", 0.00, "outside"),
]
COLORS = {
    "dispatchable": "#2f6f4e",
    "demoted": "#8a8a8a",
    "outside": "#b0821f",
}

labels = [f"{name}" for name, _, _ in ROWS]
prices = [price for _, price, _ in ROWS]
colors = [COLORS[state] for _, _, state in ROWS]

fig, ax = plt.subplots(figsize=(10.4, 4.6))
bars = ax.barh(range(len(ROWS)), prices, color=colors, height=0.62)
ax.set_yticks(range(len(ROWS)))
ax.set_yticklabels(labels, fontsize=9)
ax.invert_yaxis()
ax.set_xlabel("cost of one dispatch (CNY)", fontsize=10)
ax.set_title(
    "The queue after row 0: ¥27.17 remaining, and the first row can now be dispatched",
    fontsize=11,
    pad=12,
)
ax.set_xlim(0, max(prices) * 1.22)

for bar, price in zip(bars, prices):
    ax.text(
        bar.get_width() + 0.16,
        bar.get_y() + bar.get_height() / 2,
        f"¥{price:.2f}", va="center", fontsize=9,
    )


handles = [
    plt.Rectangle((0, 0), 1, 1, color=COLORS["dispatchable"]),
    plt.Rectangle((0, 0), 1, 1, color=COLORS["demoted"]),
    plt.Rectangle((0, 0), 1, 1, color=COLORS["outside"]),
]
ax.legend(handles, ["dispatchable now", "demoted (§210.4)", "blocked outside the repo"],
          loc="lower right", fontsize=8, frameon=False)

ax.grid(axis="x", color="#e2e2e2", linewidth=0.7)
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)

fig.tight_layout(rect=(0, 0.08, 1, 1))

# Row 0 is the one this round executed: ¥0, and its output was a state rather than a score.
fig.text(
    0.012, 0.025,
    "row 0 (executed this round): implement readerSearch — ¥0, and it converted row 1 from missing to buildable",
    fontsize=8.5, color="#2f6f4e",
)

fig.savefig("cortex-queue-after-row0-2026-11-27.png", dpi=170)
print("wrote cortex-queue-after-row0-2026-11-27.png")
