#!/usr/bin/env python3
"""Draw the room axis of the registered arm, which is now closed at its top.

## Why two points and not a curve

The campaign has five dispatched room values, and only two of them are comparable to each other: the
48,000 / 24,000 / per-route trio in `docs/MEASURE-COST-LEVER.md` was run at `ask=verbatim`, and the
registered arm has been `ask=verbatim-acts` since `§13.294` measured that ask as worth 5.75 `MR`
questions on its own. Plotting all five would draw a curve through two variables, which is exactly the
reading `§13.294` had to retract. So the figure carries the pair that differs in the room alone, and
says in a footnote why the rest is absent.

## What each panel is, in its own unit

Left: `MR` accuracy, the mean over four repetitions, because one repetition carries a 0.75-question zero
point (`§143.1`) and a single-pass difference of half a question is inside it. Right: prompt tokens
delivered to the reader per question **on the same side of the same run**, because the billed token
count is what a room costs; the 500-question `C1` reading is a different population (most of its
questions sit on 24,000-character routes) and putting the two in one column is the unit mismatch
`token-basis.py` exists to catch.

## What the picture is for

`§144` found that thirty of 1,832 gold turns sat beyond the delivery and none was ever unplaced, which
made "widen the room" the one increment with a mechanism that could be computed in advance. This figure
is the answer: the mechanism fires -- sixteen short questions become one -- and the accuracy does not
move. A reader who has the mechanism's success without the outcome will keep buying the room; the
figure is drawn so both numbers are in one view.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures" / "fig-longmemeval-room-axis.png"

INK = "#1c1c1e"
MUTED = "#8a8a8e"
ROOM = "#2c6fbb"
COST = "#c0392b"

# Both points are the registered arm with one field moved: `cortex_memory_max_prompt_chars` on
# `multi-session`. `accuracy` is the four-repetition mean of the feature side, `paired` is the delta
# against that run's own control (the number the register uses), `tokens` is the feature side's prompt
# tokens per question, and `short` is the count of questions whose `goldOverlap.carried < total`.
POINTS = [
    {
        "room": 48_460,
        "run": "44768451597 (one repetition for the gold account) / §143 four-repetition arm",
        "accuracy": 83.47,
        "paired": -2.48,
        "control": 86.16,
        "tokens": 13_019,
        "short": 16,
    },
    {
        "room": 62_000,
        "run": "44829684980",
        "accuracy": 83.88,
        "paired": -2.27,
        "tokens": 15_744,
        "short": 1,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    arguments = parser.parse_args()

    rooms = [point["room"] for point in POINTS]
    fig, (left, right) = plt.subplots(1, 2, figsize=(11.0, 4.6))

    # The y-axis is deliberately wider than the effect. A panel that spans 83.45 to 83.92 would draw a
    # 0.4-point difference as a climb, and the reading this figure exists to publish is that it is flat.
    left.plot(rooms, [point["accuracy"] for point in POINTS], "-o", color=ROOM, linewidth=1.6, markersize=8)
    for point in POINTS:
        left.annotate(
            f"{point['accuracy']:.2f}%\n({point['short']} short)",
            (point["room"], point["accuracy"]),
            textcoords="offset points",
            xytext=(0, -30),
            ha="center",
            fontsize=8.8,
            color=ROOM,
        )
    left.axhline(
        POINTS[0]["control"],
        color=MUTED,
        linestyle=(0, (4, 3)),
        linewidth=1.1,
    )
    left.annotate(
        f"its own reference pipeline, {POINTS[0]['control']:.2f}%\n(same reader, smaller window)",
        (rooms[0] - 900, POINTS[0]["control"] + 0.15),
        fontsize=8.2,
        color=MUTED,
        ha="left",
        va="bottom",
    )
    left.set_title("What the room buys", fontsize=10.5, color=INK, loc="left")
    left.set_ylabel("MR accuracy (%), four-repetition mean", fontsize=9.5, color=INK)
    left.set_ylim(80.0, 88.0)

    right.plot(rooms, [point["tokens"] for point in POINTS], "-o", color=COST, linewidth=1.6, markersize=8)
    for point in POINTS:
        right.annotate(
            f"{point['tokens']:,}",
            (point["room"], point["tokens"]),
            textcoords="offset points",
            xytext=(0, 11),
            ha="center",
            fontsize=8.8,
            color=COST,
        )
    right.set_title("What the room costs", fontsize=10.5, color=INK, loc="left")
    right.set_ylabel("prompt tokens per question, feature side", fontsize=9.5, color=INK)
    right.set_ylim(12_000, 17_000)

    for axis in (left, right):
        axis.set_xlabel("multi-session room (characters)", fontsize=9.5, color=INK)
        axis.set_xlim(45_500, 65_000)
        axis.set_xticks(rooms)
        axis.set_xticklabels([f"{room:,}" for room in rooms])
        axis.grid(color="#ececec", linewidth=0.8)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)

    # The two halves of the reading, on one line each, where neither can be mistaken for the other.
    fig.text(
        0.012,
        0.135,
        f"mechanism: {POINTS[0]['short']} -> {POINTS[1]['short']} questions with a gold turn outside the window",
        fontsize=9,
        color=INK,
    )
    fig.text(
        0.012,
        0.095,
        f"outcome: paired delta {POINTS[0]['paired']:+.2f}pp -> {POINTS[1]['paired']:+.2f}pp, "
        f"i.e. {(POINTS[1]['paired'] - POINTS[0]['paired']) / 100 * 121:+.2f} questions, McNemar p = 0.804",
        fontsize=9,
        color=INK,
    )
    fig.text(
        0.012,
        0.055,
        f"price: {(POINTS[1]['tokens'] / POINTS[0]['tokens'] - 1) * 100:+.1f}% prompt tokens per question "
        f"on the same side of the same arm",
        fontsize=9,
        color=COST,
    )

    fig.suptitle(
        "The room axis of the registered arm: the mechanism fires and the accuracy does not move",
        fontsize=11.5,
        color=INK,
        x=0.012,
        ha="left",
    )
    fig.text(
        0.012,
        0.005,
        "Only these two dispatches differ in the room alone; the 48,000 / 24,000 / per-route trio in "
        "MEASURE-COST-LEVER.md ran at\nask=verbatim, and that ask is worth 5.75 MR questions by itself. "
        "Accuracy is each run's feature-side four-repetition mean; the paired\ndelta is against that "
        "run's own control, which is the number the register reads.",
        fontsize=7.4,
        color=MUTED,
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.17, 1, 0.93))
    fig.savefig(arguments.out, dpi=200)
    print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
