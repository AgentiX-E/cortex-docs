#!/usr/bin/env python3
"""Draw the same-ruler reading: what is left of the gap after the judge is held fixed.

## Why this figure exists beside `fig-longmemeval-accuracy-vs-cost.png`

That figure plots every row on its own published coordinates, which is the right way to show the
landscape and the wrong way to read one gap: two points on it can differ by their answer model, their
judge, their corpus subset, or their cost basis, and the plot cannot say which.

This one adds the row that was measured (§172): the competitor's own answers re-graded by this
repository's judge. `ruler` holds the answers fixed and moves the judge (+0.20 points, p = 1.0000), so
the instrument is ruled out; `system` holds the judge fixed and moves the answers (-4.60 points,
p = 0.0018), and that is the reading the figure is about.

Every coordinate comes from `landscape.json` -- the competitor rows are their own published figures,
with a source per row -- and the two re-graded numbers come from `landscape.json`'s Synap `source`
string, which carries the dispatch that produced them.

Usage:
    python3 docs/figures/plot-same-ruler.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = Path(__file__).resolve().parent
LANDSCAPE = HERE / 'landscape.json'
OUT = HERE / 'fig-longmemeval-same-ruler.png'

#: The three readings from the pre-registered re-grade (section 10.2 of the pre-registration).
READINGS = [
    ('ruler\n(their answers,\ntwo judges)', 0.20, 1.0000, 'same answers'),
    ('system\n(our judge,\ntwo answer sets)', -4.60, 0.0018, 'same judge'),
    ('reference\n(the old headline)', -4.40, 0.0026, 'neither'),
]

TYPE_COLOUR = {'open-source': '#1f77b4', 'closed-cloud': '#d62728', 'closed': '#d62728'}


def main() -> int:
    landscape = json.loads(LANDSCAPE.read_text())
    rows = [row for row in landscape['overall'] if row.get('tokensPerQuery')]

    fig, (left, right) = plt.subplots(
        1, 2, figsize=(15.5, 7.2), gridspec_kw={'width_ratios': [2.05, 1]}
    )

    # ---- left: accuracy against published cost, with the re-graded point beside the published one
    for row in rows:
        colour = TYPE_COLOUR.get(row.get('type', ''), '#555555')
        marker = 'o' if row.get('type') == 'open-source' else 's'
        left.scatter(
            row['tokensPerQuery'], row['accuracy'], s=95, marker=marker,
            facecolor=colour, edgecolor='white', linewidth=0.9, zorder=3,
        )
        # The competitor whose point is re-graded has two labels to fit in one place, so its published
        # label goes left and the measured one goes below; every other label keeps the default corner.
        left_side = row['system'] in ('Maximem Synap', 'Mem0 (managed)', 'Mem0')
        anchor = (-14, 6) if left_side else (6, 6)
        left.annotate(
            f"{row['system']}\n{row['accuracy']:.1f}% @ {row['tokensPerQuery'] / 1000:.1f}K",
            xy=(row['tokensPerQuery'], row['accuracy']), xytext=anchor,
            textcoords='offset points', fontsize=7.2, color='#333333',
            ha='right' if left_side else 'left',
        )

    cortex = next(row for row in rows if row['system'] == 'cortex')
    synap = next(row for row in rows if row['system'] == 'Maximem Synap')
    regraded = 95.80

    # The measured point: same answers, this repository's judge. Open circle, dashed link.
    left.scatter(
        synap['tokensPerQuery'], regraded, s=150, marker='o', facecolor='none',
        edgecolor='#d62728', linewidth=2.0, zorder=4,
    )
    left.annotate(
        f"Synap re-graded\n{regraded:.2f}% (same ruler)", xy=(synap['tokensPerQuery'], regraded),
        xytext=(10, -34), textcoords='offset points', fontsize=7.6, color='#d62728', weight='bold',
    )
    left.plot(
        [synap['tokensPerQuery'], synap['tokensPerQuery']], [synap['accuracy'], regraded],
        linestyle=':', color='#d62728', linewidth=1.2, zorder=2,
    )

    # The gap that survives one ruler, drawn between the two measured points.
    left.annotate(
        '', xy=(synap['tokensPerQuery'], regraded),
        xytext=(cortex['tokensPerQuery'], cortex['accuracy']),
        arrowprops=dict(arrowstyle='<->', color='#444444', linewidth=1.4, shrinkA=6, shrinkB=6),
    )
    left.annotate(
        '−4.60 pts\np = 0.0018\n(one judge, 500 paired)',
        xy=(cortex['tokensPerQuery'] * 0.42, cortex['accuracy'] - 1.9),
        fontsize=8.2, color='#444444', ha='left', va='center', weight='bold',
    )

    left.set_xscale('log')
    left.set_xlabel('published tokens per question (log scale; vendors count different things)')
    left.set_ylabel('LongMemEval-S accuracy (%)')
    left.set_title(
        'Accuracy against cost, with the one point this repository re-graded', fontsize=11, weight='bold'
    )
    left.grid(alpha=0.25, linewidth=0.6)
    left.legend(
        handles=[
            Line2D([], [], marker='o', linestyle='', markerfacecolor='#1f77b4', markeredgecolor='white', label='open source / self-hosted'),
            Line2D([], [], marker='s', linestyle='', markerfacecolor='#d62728', markeredgecolor='white', label='closed / hosted'),
            Line2D([], [], marker='o', linestyle='', markerfacecolor='none', markeredgecolor='#d62728', markeredgewidth=2, label='competitor answers, our judge'),
        ],
        loc='lower right', fontsize=7.6, framealpha=0.92,
    )

    # ---- right: what the gap decomposes into
    labels = [name for name, _, _, _ in READINGS]
    deltas = [delta for _, delta, _, _ in READINGS]
    colours = ['#2ca02c' if abs(d) < 1 else '#d62728' for d in deltas]
    bars = right.barh(labels, deltas, color=colours, alpha=0.85, height=0.55, zorder=3)
    right.axvline(0, color='#333333', linewidth=1.1, zorder=4)
    for bar, (_, delta, p, _fixed) in zip(bars, READINGS):
        # Inside the bar when it is long enough to hold the text, outside it when it is not. Putting
        # every label on the same side made the short bar's text overlap the axis label.
        inside = abs(delta) > 2.4
        right.text(
            (delta / 2) if inside else delta - 0.22,
            bar.get_y() + bar.get_height() / 2,
            f"{delta:+.2f} pts\np = {p:.4f}",
            va='center', ha='center' if inside else 'right',
            fontsize=9.0, weight='bold',
            color='white' if inside else '#333333',
        )
    right.set_xlim(-7.6, 4.2)
    right.set_xlabel('cortex minus competitor (accuracy points)')
    right.set_title('Three ways of holding something fixed', fontsize=11, weight='bold')
    right.grid(axis='x', alpha=0.25, linewidth=0.6, zorder=0)
    right.invert_yaxis()

    fig.suptitle(
        'Maximem Synap leads by 4.60 points under one ruler — the judge was not the difference',
        fontsize=13, weight='bold', y=0.98,
    )
    fig.text(
        0.5, 0.012,
        'Competitor coordinates are their own published figures (landscape.json, one source per row); only the '
        'cortex row and the open circle are measured here.\n'
        'The re-grade put the competitor\'s 500 answers through this repository\'s judge: 479/500 = 95.80% '
        'against their published 478/500 = 95.60%.',
        ha='center', fontsize=7.4, color='#555555',
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.955))
    fig.savefig(OUT, dpi=160)
    print(f'wrote {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
