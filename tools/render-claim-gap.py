#!/usr/bin/env python3
"""Draw the gap between what a system claims on LongMemEval and what an independent run measured.

## Why this figure exists

Every other figure in this directory plots published numbers as if they were commensurable. They are
not, and the reason is measurable: on the same suite, three systems that publish 90 to 94.4 are
re-measured by independent harnesses at 63.8 to 71.2. A leaderboard drawn only from claims ranks
vendors by optimism; a leaderboard drawn only from re-runs has three rows. The dumbbell shows both
coordinates of the same system, which is the only shape in which the gap is visible rather than
argued about.

## Why the oracle ceiling is a line and not a row

`82.4` is the published ceiling for this suite -- the reader is given the evidence sessions and
nothing else -- measured with `gpt-4o`. It is not a system and cannot be ranked, but it is the number
that decides whether a claim is even possible, and a figure that omits it lets a reader believe 98.4
and 95.4 are on the same scale as 71.0.

## Why `cortex` has no measured marker

Because no independent re-run of this repository exists. Drawing the claim twice, or at a
"corrected" position of our own choosing, would be the defect this figure was built to expose. The
row is drawn with a single marker and a note saying so, which is the honest state of the evidence.

Usage:
  python3 tools/render-claim-gap.py [--out docs/figures]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "figures" / "landscape.json"
OUT = ROOT / "docs" / "figures" / "fig-longmemeval-claim-vs-measurement.png"

INK = "#1c1c1e"
MUTED = "#8a8a8e"
CLAIM = "#c0392b"
MEASURED = "#2c6fbb"
CEILING = "#9b59b6"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    data = json.loads(DATA.read_text())["independent"]
    rows = data["rows"]
    ceiling = data["oracleCeiling"]

    fig, ax = plt.subplots(figsize=(10.4, 4.6))
    for position, row in enumerate(reversed(rows)):
        y = position
        claim = row["claim"]
        ax.plot(claim, y, "o", color=CLAIM, markersize=9, zorder=3)
        ax.annotate(
            f"{claim:.1f}",
            (claim, y),
            textcoords="offset points",
            xytext=(0, 11),
            ha="center",
            fontsize=8.5,
            color=CLAIM,
        )
        for measured in row["measured"]:
            value = measured["value"]
            ax.plot([claim, value], [y, y], "-", color=MUTED, linewidth=1.2, zorder=1)
            ax.plot(value, y, "s", color=MEASURED, markersize=8, zorder=3)
            ax.annotate(
                f"{value:.1f}",
                (value, y),
                textcoords="offset points",
                xytext=(0, -14),
                ha="center",
                fontsize=8.5,
                color=MEASURED,
            )
        if not row["measured"]:
            ax.annotate(
                "no independent re-run",
                (claim, y),
                textcoords="offset points",
                xytext=(16, -3),
                fontsize=8,
                color=MUTED,
                style="italic",
            )

    ax.axvline(ceiling, color=CEILING, linestyle=(0, (4, 3)), linewidth=1.3, zorder=0)
    ax.annotate(
        f"published oracle ceiling {ceiling:.1f}",
        (ceiling, len(rows) - 0.42),
        textcoords="offset points",
        xytext=(-4, 0),
        ha="right",
        fontsize=8.5,
        color=CEILING,
        rotation=90,
        va="top",
    )

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([row["system"] for row in reversed(rows)], fontsize=9.5)
    ax.set_xlabel("LongMemEval-S accuracy (%)", fontsize=9.5, color=INK)
    ax.set_xlim(45, 102)
    ax.set_ylim(-0.7, len(rows) - 0.35)
    ax.grid(axis="x", color="#e6e6e6", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=9)

    ax.plot([], [], "o", color=CLAIM, label="the system's own published figure")
    ax.plot([], [], "s", color=MEASURED, label="an independent harness's re-run")
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)

    fig.text(
        0.01,
        0.015,
        "Sources: HEAMS (arXiv, 2026-11); Lobu agent-memory-benchmark (glm-5.1 answerer, 2026-11); "
        "jakecuth.com/work/agent-memory-lab; vendor pages. Configurations differ between rows -- "
        "that is the finding, not a defect of the drawing.",
        fontsize=7.2,
        color=MUTED,
        wrap=True,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(args.out, dpi=200)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
