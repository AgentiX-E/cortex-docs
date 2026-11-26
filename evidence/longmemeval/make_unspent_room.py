#!/usr/bin/env python3
"""The room the arm pays for and does not spend, drawn as two panels that answer two questions.

## What this chart is for

The campaign has read the evidence room as a **budget** for many rounds -- cut it and lose points,
raise it and buy points. Both readings assume the room is spent. On the published artifact it is not:
`selectByRelevance` returns the largest fitting prefix, so the first turn too large for what is left
ends the pass and the rest of the paid-for room is returned to nobody.

The left panel is that hole, per route. It is bimodal for one reason and the reason is the finding:
`maxTurnChars` is 400 on exactly `multi-session` and `temporal`, so a prefix over small turns lands
within one turn of the room by construction. The four routes with no cap run to five figures on a
single question. **The campaign's own room reading is `multi-session`-shaped, which is the one route
where the rule is nearly exact** -- that is why four rounds of room experiments never surfaced this.

The right panel is the same arithmetic per question, which is the only form that decides anything.
`gap` is the best missing gold's rank minus the turns the window actually held: it is how far buying
room would have to reach. Questions on the right of it cannot be fixed by filling at any price, and
`multi-session` -- where 13 of the arm's 14 decision faults live -- has slack so small that it cannot
be fixed there either.

## What the colours mean, and what they refuse to mean

Filled markers are wrong answers, hollow are correct ones. That split is drawn because it is the trap:
**215 questions could gain gold and only 10 of them are wrong**, and on this artifact a question with
an absent gold reads *higher* than one whose gold arrived whole (93.64% against 91.76%). A chart that
showed only "gold recovered" would read as an accuracy forecast it is not entitled to make.
"""

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ARTIFACT = pathlib.Path("/tmp/art457/benchmark-cortex-memory-ablation-report.json")

ROUTE_ORDER = [
    "multi-session",
    "temporal",
    "abstention",
    "knowledge-update",
    "assistant",
    "flat",
]
CAPPED = {"multi-session", "temporal"}

CAPTION = (
    "read off `45760081761`. The fill's reach is an upper bound: it spends the slack on gold as if no "
    "other turn competed for it.\n"
    "215 questions could gain gold and only 10 of them are wrong -- on this artifact a question with an "
    "absent gold reads 93.64% against 91.76% for one whose gold arrived whole."
)


def load():
    report = json.loads(ARTIFACT.read_text())
    rooms = report["memoryArmConfig"]["maxPromptCharsByRoute"]
    rows = []
    for question in report["questions"]:
        overlap = question.get("goldOverlap") or {}
        gold = overlap.get("goldTurns") or []
        if not gold:
            continue
        delivered = overlap.get("goldDelivered") or []
        ranks = overlap.get("goldRanks") or []
        missing = [i for i in range(len(gold)) if not delivered[i]]
        if not missing:
            continue
        room = rooms[question["route"]]
        slack = room - question["deliveredPromptChars"]
        ordered = sorted(missing, key=lambda i: ranks[i] if ranks[i] >= 0 else 10**9)
        left, recoverable = max(0, slack), 0
        for index in ordered:
            if len(gold[index]) <= left:
                left -= len(gold[index])
                recoverable += 1
        held = len(question.get("turns") or [])
        surf = [ranks[i] for i in ordered if ranks[i] >= 0]
        rows.append(
            {
                "route": question["route"],
                "slack": slack,
                "gap": (min(surf) - held) if surf else None,
                "correct": bool(question.get("correct")),
                "missing": len(missing),
                "recoverable": recoverable,
            }
        )
    return rows


def main():
    rows = load()
    fig, (left, right) = plt.subplots(1, 2, figsize=(13.6, 6.2), gridspec_kw={"width_ratios": [1, 1.25]})

    # ---- left: the hole, per route ------------------------------------------------------------
    means, maximums, names = [], [], []
    for route in ROUTE_ORDER:
        of_route = [row["slack"] for row in rows if row["route"] == route]
        if not of_route:
            continue
        means.append(sum(of_route) / len(of_route))
        maximums.append(max(of_route))
        names.append(route)

    y = range(len(names))
    colors = ["#c0392b" if name in CAPPED else "#2f6fb5" for name in names]
    left.barh(list(y), maximums, color=colors, alpha=0.22, height=0.62, label="worst question on the route")
    left.barh(list(y), means, color=colors, height=0.62, label="mean per question")
    left.set_yticks(list(y))
    left.set_yticklabels(names, fontsize=9.5)
    left.invert_yaxis()
    left.set_xlabel("characters of paid-for room returned unspent (log scale)", fontsize=9.5)
    left.set_title("the prefix rule's hole is a function of the turn cap", fontsize=11, loc="left")
    left.axvline(0, color="#3a3a3a", lw=0.8)
    for index, (mean, peak) in enumerate(zip(means, maximums)):
        left.text(peak * 1.10, index, f"{peak:,}", va="center", fontsize=8, color="#3a3a3a")
        left.text(mean * 1.10, index - 0.24, f"mean {mean:,.0f}", va="center", fontsize=7.5, color="#5c6672")
    left.legend(
        handles=[
            Patch(facecolor="#c0392b", alpha=0.75, label="`maxTurnChars: 400` binds"),
            Patch(facecolor="#2f6fb5", alpha=0.75, label="no per-turn cap"),
            Patch(facecolor="#8a93a0", alpha=0.6, label="mean"),
            Patch(facecolor="#8a93a0", alpha=0.22, label="worst question"),
        ],
        loc="upper right",
        bbox_to_anchor=(1.0, 1.0),
        fontsize=8,
        frameon=False,
        ncol=2,
    )
    left.set_xscale("log")
    left.set_xlim(60, max(maximums) * 3.5)

    # ---- right: per question, in the two dimensions that decide ---------------------------------
    for correct, face, label, zorder in (
        (True, "none", "correct", 2),
        (False, "#c0392b", "wrong", 4),
    ):
        picked = [
            row
            for row in rows
            if row["correct"] is correct and row["gap"] is not None
        ]
        right.scatter(
            [row["gap"] for row in picked],
            [row["slack"] for row in picked],
            s=[18 + 7 * row["missing"] for row in picked],
            facecolors=face,
            edgecolors="#c0392b" if not correct else "#2f6fb5",
            linewidths=1.1,
            alpha=0.85 if not correct else 0.55,
            label=label,
            zorder=zorder,
        )

    # The ten wrong questions the fill can reach get a ring, and the eleven it cannot are left plain.
    # Two extra legend entries were tried and removed: they showed hollow markers standing for filled
    # ones, which is a legend that describes a symbol the chart does not draw.
    reachable = [
        row for row in rows if not row["correct"] and row["recoverable"] > 0 and row["gap"] is not None
    ]
    unreachable = [
        row for row in rows if not row["correct"] and row["recoverable"] == 0 and row["gap"] is not None
    ]
    right.scatter(
        [row["gap"] for row in reachable],
        [row["slack"] for row in reachable],
        s=[60 + 10 * row["missing"] for row in reachable],
        facecolors="none",
        edgecolors="#8e2b21",
        linewidths=1.8,
        zorder=6,
    )

    right.set_xlabel("gap: the best missing gold's rank minus the turns the window held", fontsize=9.5)
    right.set_ylabel("characters of room left unspent", fontsize=9.5)
    right.set_title("filling reaches 10 of the 21 wrong questions, and none in `multi-session`", fontsize=11, loc="left")
    right.set_yscale("symlog", linthresh=100)
    right.axhline(0, color="#3a3a3a", lw=0.8)
    right.grid(axis="y", color="#dfe3e8", lw=0.6, zorder=0)
    right.set_axisbelow(True)

    # The 21 wrong questions that are missing gold, called out as a group: this is where the whole
    # delivery axis lives, and `gap` splits it into "buy room" and "no amount of room".
    right.annotate(
        f"ringed: the {len(reachable)} wrong questions the fill can reach\n"
        f"plain: the {len(unreachable)} it cannot, at any price",
        xy=(0.985, 0.985),
        xycoords="axes fraction",
        fontsize=8.2,
        color="#8e2b21",
        va="top",
        ha="right",
    )
    right.annotate(
        "13 of the 14 decision faults are `multi-session`: its slack is 16-108, so filling buys nothing",
        xy=(0.985, 0.905),
        xycoords="axes fraction",
        fontsize=8.2,
        color="#8e2b21",
        va="top",
        ha="right",
    )

    # Away from the top-right, where the two notes live: a legend on top of an annotation is the one
    # overlap that makes both unreadable.
    right.legend(loc="center right", fontsize=8.5, frameon=False)
    fig.text(0.008, 0.015, CAPTION, fontsize=7.8, color="#6b7684")

    fig.tight_layout(rect=(0, 0.035, 1, 1))
    out = pathlib.Path("/workspace/charts/cortex-unspent-room-2026-11-27.png")
    fig.savefig(out, dpi=170)
    print(out)


if __name__ == "__main__":
    main()
