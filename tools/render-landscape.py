#!/usr/bin/env python3
"""Render the three positioning figures the review asks for, from one data file.

## Why the data is a file rather than literals in this script

Every number below is published somewhere, and the point of these figures is that a reader can check
them against the source. A literal inside a plotting call is a number nobody can audit; a row in
`docs/figures/landscape.json` carries its own citation, its own measurement unit and -- crucially --
whether it is even comparable.

## Why three figures and not one

The review asks for accuracy against cost, split by leaderboard, plus a combined view. A single scatter
would have to put three incommensurable units on one axis and would then invite exactly the comparison
this project has retracted twice:

| artifact | unit | what it measures |
| --- | --- | --- |
| QA accuracy on LongMemEval-S | percent, 500 questions | end to end, reader and judge included |
| recall@k on a sub-capability | percent, recall only | the retriever, with no reader |
| tokens per query | tokens | what one answer costs |

So the figures are: **accuracy against cost** (only the rows that publish both), **accuracy ranking
grouped by reader** (because the same system moves 8 points when its reader changes), and **cost
ranking** (because "most accurate" and "cheapest" are different winners, and this project is neither).
The combined view is the first figure by construction: it is the only one with both axes.

## Why unreported cost is drawn as a band and not as a point

A missing cost is not zero and not the mean of the others. Placing those systems at an imputed x would
invent a position and, worse, would put a system with no cost data next to one with a measured bill where
a reader would compare them. The band along the top says "accuracy measured, cost not published", which is
a fact about the literature rather than about the system.

Usage:
  python3 tools/render-landscape.py [--out docs/figures]
"""

from __future__ import annotations

import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DATA = REPO / "docs" / "figures" / "landscape.json"

# Colour encodes product type, and the encoding is stated on every figure because it is the axis the
# review asks about: a self-hostable system a reader can run is a different proposition from a hosted one
# at the same score.
def _cost_ticks(low: float, high: float) -> list[float]:
    """Tick positions for a log cost axis, rounded to numbers a reader can repeat.

    Derived from the data rather than written down: a fixed tick list is a fixed axis, and the axis has to
    follow whatever rows the file holds -- including the next system that publishes a cost outside today's
    range.
    """
    candidates = [500, 1_000, 2_000, 2_500, 3_000, 4_000, 5_000, 6_000, 7_500, 10_000, 15_000, 20_000, 30_000,
                  40_000, 50_000, 75_000, 100_000]
    inside = [value for value in candidates if low * 0.82 <= value <= high * 1.22]
    # A single tick is not an axis: fall back to the two ends of the observed range, rounded.
    return inside if len(inside) >= 2 else [round(low, -2), round(high, -2)]


COLOURS = {
    "open-source": "#1f77b4",
    "closed-cloud": "#d62728",
    "unstated": "#7f7f7f",
}
MARKERS = {"open-source": "o", "closed-cloud": "s", "unstated": "D"}
LABELS = {
    "open-source": "open source / self-hostable",
    "closed-cloud": "closed cloud service",
    "unstated": "type not stated",
}


def load() -> dict:
    return json.loads(DATA.read_text())


def figure_accuracy_cost(data: dict, out: pathlib.Path) -> pathlib.Path:
    """Two panels over one shared accuracy axis: priced systems by cost, unpriced ones beside them.

    The first attempt drew the unpriced systems in a band across the top, and the band lied in two ways: it
    put them at an accuracy they do not have (the band sat above every point) and it crowded its label past
    the axes. A second panel is the honest shape -- the shared y axis keeps the comparison available, and the
    x axis of the right panel is free to mean something else, which is "no cost was published".
    """
    rows = data["overall"]
    priced = sorted(
        [row for row in rows if row.get("tokensPerQuery") is not None],
        key=lambda row: row["tokensPerQuery"],
    )
    unpriced = sorted(
        [row for row in rows if row.get("tokensPerQuery") is None],
        key=lambda row: row["accuracy"],
    )

    fig, (left, right) = plt.subplots(
        1,
        2,
        figsize=(14, 7.5),
        sharey=True,
        gridspec_kw={"width_ratios": [1.45, 1]},
    )

    # Labels are placed top-down and pushed ABOVE their marker when the row below is close enough that the
    # two would collide. `Maximem Synap` (95.6 at 7,400) and `Mem0` (94.4 at 6,787) are 1.2 points and 9% of
    # an axis apart: at a fixed offset the first one's text lands on the second one's marker, and a marker
    # under a label reads as "this system is here" -- the label IS the data, so it cannot cover another.
    for row in sorted(priced, key=lambda r: -r["accuracy"]):
        left.scatter(
            row["tokensPerQuery"],
            row["accuracy"],
            s=170,
            c=COLOURS[row["type"]],
            marker=MARKERS[row["type"]],
            edgecolors="black",
            linewidths=1.2,
            zorder=3,
        )
        crowded_left = sum(
            1
            for other in priced
            if other is not row
            and other["accuracy"] > row["accuracy"]
            and abs(other["accuracy"] - row["accuracy"]) < 1.8
            and 0.8 < other["tokensPerQuery"] / row["tokensPerQuery"] < 1.3
        ) % 2 == 1
        # Crowded rows alternate sides instead of all moving up. Pushing both labels above their markers
        # moved the collision from the markers to the text -- the second attempt had `Maximem Synap` printed
        # across `Mem0`, which is worse than the original overlap because now one system's name is hidden
        # behind another's rather than merely close to it.
        left.annotate(
            row["system"],
            (row["tokensPerQuery"], row["accuracy"]),
            textcoords="offset points",
            xytext=(-13, -4) if crowded_left else (11, -4),
            ha="right" if crowded_left else "left",
            fontsize=9,
        )
    left.set_xscale("log")
    # Derived from the rows, not written down. The first version hard-coded `(2_200, 9_000)`, which was correct
    # for the six rows that existed then and silently CLIPPED the next two that arrived above 9,000 -- a point
    # outside the axis is not a point with a surprising position, it is an absent system, and the figure's whole
    # job is to show which systems exist at which cost.
    costs = [row["tokensPerQuery"] for row in priced]
    left.set_xlim(min(costs) * 0.82, max(costs) * 1.22)
    # Plain numbers rather than 3x10^3: a reader comparing 2,807 with 7,448 should not have to decode an
    # exponent to do it. The ticks follow the data for the same reason the limits do.
    left.set_xticks(_cost_ticks(min(costs), max(costs)))
    left.get_xaxis().set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    left.set_xlabel("tokens per query (log scale)")
    left.set_ylabel("LongMemEval-S QA accuracy (%)")
    left.set_title("cost published", fontsize=11)
    left.grid(True, which="both", alpha=0.25, zorder=0)

    # Points on a shared accuracy axis rather than bars. A bar chart's y axis is a category index, and sharing
    # it with a scatter of accuracies squashed the left panel's data into the top decile -- the first attempt
    # did exactly that. With the marker placed at the accuracy, the two panels share one axis honestly and the
    # label carries the name.
    right.set_xlim(0, 1)
    right.set_xticks([])
    # The marker sits at the true accuracy and the label is pushed down only as far as it must be to clear its
    # neighbour, with a leader line back to the marker. Three systems inside 1.9 points (96.8, 96.2, 94.9) put
    # their labels on top of each other otherwise, and moving the MARKER would be a lie about the score.
    placed: list[float] = []
    for row in sorted(unpriced, key=lambda item: item["accuracy"], reverse=True):
        y = row["accuracy"]
        if placed and placed[-1] - y < 2.4:
            y = placed[-1] - 2.4
        placed.append(y)
        right.scatter(
            0.02,
            row["accuracy"],
            s=150,
            c=COLOURS[row["type"]],
            marker=MARKERS[row["type"]],
            edgecolors="black",
            linewidths=1.2,
            zorder=3,
        )
        right.plot(
            [0.05, 0.09],
            [row["accuracy"], y],
            color="#999999",
            linewidth=0.8,
            zorder=2,
        )
        right.text(
            0.1,
            y,
            f"{row['system']} ({row['reader']}) -- {row['accuracy']:.1f}",
            va="center",
            fontsize=9,
            # A white pad behind the text so the cortex reference line does not run through it. The line has to
            # cross this panel -- it is what makes the comparison available -- and a label a reader has to
            # squint past is worse than one with a box behind it.
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6},
        )
    right.set_xlabel("no cost axis: these sources publish accuracy only")
    right.set_title("cost not published", fontsize=11)
    right.grid(True, axis="y", alpha=0.25)

    for ax in (left, right):
        ax.axhline(
            next(row["accuracy"] for row in rows if row["system"] == "cortex"),
            color="#1f77b4",
            linestyle=":",
            linewidth=1.4,
            zorder=1,
        )

    handles = [
        Line2D(
            [0],
            [0],
            marker=MARKERS[k],
            color="w",
            markerfacecolor=COLOURS[k],
            markeredgecolor="black",
            markersize=10,
            label=LABELS[k],
        )
        for k in COLOURS
        if any(row["type"] == k for row in rows)
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False)
    fig.suptitle(
        "LongMemEval-S (500 questions): accuracy against cost, and the systems that publish only accuracy\n"
        "The dotted line is cortex; the same memory system spans 90.2 to 98.4 across readers",
        fontsize=12,
    )
    path = out / "fig-longmemeval-accuracy-vs-cost.png"
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def figure_accuracy_ranking(data: dict, out: pathlib.Path) -> pathlib.Path:
    """The leaderboard as it must be read: grouped by reader, because the reader moves the score 8 points."""
    rows = sorted(data["overall"], key=lambda row: row["accuracy"])
    fig, ax = plt.subplots(figsize=(11, 8))
    bars = ax.barh(
        [f"{row['system']} ({row['reader']})" for row in rows],
        [row["accuracy"] for row in rows],
        color=[COLOURS[row["type"]] for row in rows],
        edgecolor="black",
        linewidth=0.8,
    )
    for bar, row in zip(bars, rows):
        ax.text(
            bar.get_width() + 0.25,
            bar.get_y() + bar.get_height() / 2,
            f"{row['accuracy']:.2f}",
            va="center",
            fontsize=9,
        )
    top = max(row["accuracy"] for row in rows)
    ax.axvline(top, color="#d62728", linestyle="--", linewidth=1.2, zorder=1)
    cortex = next(row for row in rows if row["system"] == "cortex")
    ax.axvline(cortex["accuracy"], color="#1f77b4", linestyle=":", linewidth=1.6, zorder=1)
    # Both reference lines are labelled at the top of the axes rather than at the bottom, where the legend used
    # to sit on top of them.
    # The high label sits BELOW the axes and the cortex label ABOVE them: at the top both were five units long
    # and met in the middle of the 91-98 range, which is the busiest part of the figure. The bottom of the
    # 97-100 strip is empty on every row, so nothing collides there.
    ax.text(
        top + 0.6,
        -0.85,
        f"published high {top:.1f}",
        color="#d62728",
        fontsize=9,
        ha="right",
        clip_on=False,
    )
    ax.text(
        cortex["accuracy"] + 0.4,
        len(rows) - 0.35,
        f"cortex {cortex['accuracy']:.2f}",
        color="#1f77b4",
        fontsize=9,
    )
    ax.set_xlim(60, 101)
    ax.set_xlabel("LongMemEval-S QA accuracy (%)")
    ax.set_title(
        "Published LongMemEval-S accuracy, by answering reader\n"
        "The same memory system spans 90.2 to 98.4 with the reader held out of the comparison",
        fontsize=12,
    )
    handles = [
        Line2D([0], [0], color=COLOURS[k], lw=8, label=LABELS[k])
        for k in COLOURS
        if any(row["type"] == k for row in rows)
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False)
    ax.grid(True, axis="x", alpha=0.25)
    path = out / "fig-longmemeval-accuracy-ranking.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def figure_cost(data: dict, out: pathlib.Path) -> pathlib.Path:
    """The column this project loses on, and the one it is cheapest to be honest about."""
    rows = sorted(
        [row for row in data["overall"] if row.get("tokensPerQuery") is not None],
        key=lambda row: row["tokensPerQuery"],
    )
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.bar(
        [row["system"] for row in rows],
        [row["tokensPerQuery"] for row in rows],
        color=[COLOURS[row["type"]] for row in rows],
        edgecolor="black",
        linewidth=0.8,
    )
    for bar, row in zip(bars, rows):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 120,
            f"{row['tokensPerQuery']:,}",
            ha="center",
            fontsize=9,
        )
        if row.get("costNote"):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() / 2,
                row["costNote"],
                ha="center",
                va="center",
                fontsize=7,
                rotation=90,
                color="white",
            )
    ax.set_ylabel("tokens per query")
    ax.set_title(
        "Reported cost per query, LongMemEval-S\n"
        "Bars are the published figures; the note inside a bar is how that figure was defined",
        fontsize=12,
    )
    ax.grid(True, axis="y", alpha=0.25)
    path = out / "fig-longmemeval-cost-per-query.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO / "docs" / "figures"))
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = load()
    for path in (
        figure_accuracy_cost(data, out),
        figure_accuracy_ranking(data, out),
        figure_cost(data, out),
    ):
        print(path.relative_to(REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
