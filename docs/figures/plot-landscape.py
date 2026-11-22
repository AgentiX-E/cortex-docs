#!/usr/bin/env python3
"""Draw the LongMemEval-S landscape from `landscape.json`, with cortex's own coordinates.

## Why a committed script and not a notebook cell

The three figures this replaces were produced once, on 2026-11-20, by code that is not in the
repository. `03-execution-plan.md` §13.38 records what that costs: a number whose derivation
lives in a session cannot be re-derived by its reader, so every later argument about the number
has to trust the session. The coordinates here are checked into `landscape.json` with a source
per row; this file is the only thing that turns them into pixels, and running it again
reproduces the pixels.

## What the cost axis does and does not mean

`tokensPerQuery` is whatever the vendor published: some count memory tokens, some count reader
input, one counts neither. The axis is therefore comparable in **order of magnitude** and no
finer, which is why the figures label each point with its number rather than inviting a reading
off the axis. Accuracy has the same caveat for a different reason -- the answer model moves
Mastra by 10.6 points on its own -- so the two axes are read together and neither alone.

Usage:
    python3 docs/figures/plot-landscape.py            # writes the three PNGs beside this file
    python3 docs/figures/plot-landscape.py --check    # exit 1 if a PNG would change
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt  # noqa: E402  (backend must be chosen before pyplot)

HERE = Path(__file__).resolve().parent
LANDSCAPE = HERE / 'landscape.json'
#: The matched-model runs: same harness, same reader id, same judge, one dispatch per system.
MATCHED = HERE / 'matched-model.json'

#: The two classes the reader needs separated, and the colour each one gets.
#:
#: Three classes, not two: `unstated` is a real category -- KITE and full-context publish a
#: score without saying whether their stack is installable -- and folding it into either of the
#: others would claim something the source does not say.
TYPE_COLOUR = {
    'open-source': '#1f6fb4',
    'closed-cloud': '#c0392b',
    'unstated': '#7f8c8d',
    'cortex': '#d4ac0d',
}
TYPE_MARKER = {
    'open-source': 'o',
    'closed-cloud': 's',
    'unstated': '^',
}

#: cortex's own row, drawn from the artifact rather than from `landscape.json`, so that a
#: correction to the measured number is one constant and not a hand-edited coordinate.
CORTEX_LABEL = 'cortex'

#: The one axis this figure no longer draws, and why it is named rather than deleted.
#:
#: Earlier revisions carried a hollow star at 93.85% -- what `ask=enumerated` would read if its
#: projected +2.60 held. Run `44962474136` measured it at **89.70%**, 1.53 points *below* the
#: registered arm, and the axis is retired (`RETRACTIONS` #24). Leaving the star would make this
#: figure the last document still claiming it; deleting the fact would hide that the claim existed.
WITHDRAWN = {
    'label': 'enumerated ask',
    'projection': 93.85,
    'measured': 89.70,
}



def load() -> dict:
    return json.loads(LANDSCAPE.read_text(encoding='utf-8'))


def _cortex_row(data: dict) -> dict:
    for row in data['overall']:
        if row['system'] == CORTEX_LABEL:
            return row
    raise SystemExit('landscape.json has no cortex row: the figures would silently omit us')


def plot_accuracy_vs_cost(data: dict, out: Path) -> None:
    rows = [row for row in data['overall'] if row.get('tokensPerQuery')]
    fig, ax = plt.subplots(figsize=(11, 7))

    for row in rows:
        ours = row['system'] == CORTEX_LABEL
        ax.scatter(
            row['tokensPerQuery'],
            row['accuracy'],
            s=260 if ours else 110,
            marker='*' if ours else TYPE_MARKER[row['type']],
            color='#f1c40f' if ours else TYPE_COLOUR[row['type']],
            edgecolors='black',
            linewidths=1.6 if ours else 0.6,
            zorder=5 if ours else 3,
        )
        # Mem0 and Synap are 600 tokens apart and 1.2 points apart, so they collide whatever the
        # global offset does. Mem0's label goes to its left because the space there is empty;
        # everything else keeps the default above-right placement.
        left_side = row['system'].startswith('Mem0')
        ax.annotate(
            f"{row['system']}\n{row['accuracy']:.2f}%",
            (row['tokensPerQuery'], row['accuracy']),
            textcoords='offset points',
            xytext=(-11, -22) if left_side else (9, 8),
            ha='right' if left_side else 'left',
            fontsize=8.5,
            fontweight='bold' if ours else 'normal',
            zorder=6,
        )

    ours = _cortex_row(data)
    # No projection is drawn. The one this figure used to carry is named in `WITHDRAWN` and priced
    # where a reader who remembers it will look: at the bottom, beside the axis that retired it.
    fig.text(
        0.012,
        0.012,
        f"withdrawn: the {WITHDRAWN['label']} was projected at {WITHDRAWN['projection']:.2f}% and "
        f"measured {WITHDRAWN['measured']:.2f}% (RETRACTIONS #24)",
        fontsize=7.4,
        color='#7d6608',
        ha='left',
    )

    # The comparison that decides the next iteration: the same money, four and a third points.
    synap = next(row for row in data['overall'] if row['system'] == 'Maximem Synap')
    ax.annotate(
        f"same cost, {synap['accuracy'] - ours['accuracy']:+.2f}pp",
        xy=(synap['tokensPerQuery'], (synap['accuracy'] + ours['accuracy']) / 2),
        fontsize=8.5,
        color='#7b241c',
        ha='left',
        xytext=(synap['tokensPerQuery'] * 1.15, (synap['accuracy'] + ours['accuracy']) / 2),
        arrowprops={'arrowstyle': '-', 'linestyle': '--', 'color': '#7b241c', 'lw': 0.9},
        zorder=4,
    )

    ax.set_xscale('log')
    ax.set_xlim(700, 60_000)
    ax.set_ylim(84.5, 97.6)
    ax.set_xlabel('tokens per question (vendor-published; order of magnitude only)', fontsize=10)
    ax.set_ylabel('LongMemEval-S accuracy (%)', fontsize=10)
    ax.set_title(
        'LongMemEval-S: accuracy against published cost per question\n'
        f"{data['questions']} questions, as of {data['asOf']}. "
        'Only rows that published a token count appear.',
        fontsize=11.5,
    )
    ax.grid(True, which='both', linestyle=':', alpha=0.35)

    handles = [
        plt.Line2D([], [], marker=TYPE_MARKER[name], color=TYPE_COLOUR[name], linestyle='',
                   markersize=8, label=label)
        for name, label in (
            ('open-source', 'open source / self-hostable'),
            ('closed-cloud', 'closed cloud service'),
            ('unstated', 'type not stated'),
        )
    ]
    handles.append(
        plt.Line2D([], [], marker='*', color='#f1c40f', linestyle='', markersize=14,
                   markeredgecolor='black', label='cortex (measured by this repository)')
    )
    ax.legend(handles=handles, loc='lower right', fontsize=8.5, framealpha=0.95)

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot_ranking(data: dict, out: Path) -> None:
    rows = sorted(data['overall'], key=lambda row: row['accuracy'])
    fig, ax = plt.subplots(figsize=(11, 8))

    for index, row in enumerate(rows):
        ours = row['system'] == CORTEX_LABEL
        ax.barh(
            index,
            row['accuracy'],
            height=0.72,
            color='#f1c40f' if ours else TYPE_COLOUR[row['type']],
            edgecolor='black' if ours else 'none',
            linewidth=1.2 if ours else 0,
        )
        ax.text(
            row['accuracy'] + 0.45,
            index,
            f"{row['accuracy']:.2f}",
            va='center',
            fontsize=8.5,
            fontweight='bold' if ours else 'normal',
        )

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(
        [
            f"{row['system']} ({row['reader']})" + ('  <-- this repository' if row['system'] == CORTEX_LABEL else '')
            for row in rows
        ],
        fontsize=8.5,
    )
    # The withdrawn projection is *not* drawn as a reference line here either: on a ranking of
    # published scores, a vertical line at a number nobody reported would read as a row.
    ax.set_xlabel('LongMemEval-S accuracy (%)', fontsize=10)
    ax.set_title(
        'LongMemEval-S: every published overall score, with its answer model\n'
        'Self-reported unless the row is cortex. The reader column is the reason two rows\n'
        'of the same system can differ by ten points.',
        fontsize=10.5,
    )
    # The floor is the x axis start; the ceiling leaves room for the 98.40 label, which is
    # otherwise clipped by the axes edge on the highest row.
    ax.set_xlim(50, 103)
    ax.grid(True, axis='x', linestyle=':', alpha=0.35)

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot_claim_vs_measurement(data: dict, out: Path) -> None:
    independent = data['independent']
    fig, ax = plt.subplots(figsize=(11, 7))

    # Grouped by claim, because two systems were re-run twice each and both of their pairs land on
    # the same x. Drawn flat, the four labels overlap into two unreadable sentences -- which is how
    # a figure that is *about* reproducibility became the one nobody could read.
    grouped: dict[tuple[str, float], list[tuple[float, str]]] = {}
    for row in independent['rows']:
        for measured in row['measured']:
            grouped.setdefault((row['system'], row['claim']), []).append(
                (measured['value'], measured['by'])
            )

    # Placed in descending y and pushed down on collision, in data units. Two of the four re-runs
    # land at 71.0 and 71.2 on claims 4.2 apart, so a fixed per-group offset cannot separate them:
    # the collision is between groups, not inside one.
    placed: list[float] = []
    for (system, claim), measured_rows in grouped.items():
        measured_rows.sort(reverse=True)
        ax.scatter([claim] * len(measured_rows), [m[0] for m in measured_rows],
                   s=110, color=TYPE_COLOUR['open-source'], zorder=3)

    labels = [
        (claim, value, f'{system} · {by} · {value:.1f}')
        for (system, claim), measured_rows in grouped.items()
        for value, by in measured_rows
    ]
    for claim, value, text in sorted(labels, key=lambda item: -item[1]):
        y = value
        while any(abs(y - other) < 2.2 for other in placed):
            y -= 2.2
        placed.append(y)
        # To the left: the claim axis runs to 102 and a 40-character label placed to the right of
        # x=94 would be clipped by the axes. The left half of this panel is empty above the
        # diagonal, so that is where the room is.
        ax.annotate(
            text,
            xy=(claim, value),
            xytext=(claim - 1.2, y),
            ha='right',
            va='center',
            fontsize=7.5,
            arrowprops={'arrowstyle': '-', 'color': '#aab7b8', 'lw': 0.6,
                        'shrinkA': 0, 'shrinkB': 4},
            zorder=4,
        )

    ours = _cortex_row(data)
    ax.scatter(
        ours['accuracy'], ours['accuracy'], s=300, marker='*', color='#f1c40f',
        edgecolors='black', linewidths=1.4, zorder=5,
    )
    ax.annotate(
        f"cortex {ours['accuracy']:.2f}%\nno independent re-run exists",
        (ours['accuracy'], ours['accuracy']),
        textcoords='offset points',
        xytext=(12, -26),
        fontsize=8.5,
        fontweight='bold',
    )

    low, high = 45, 102
    ax.plot([low, high], [low, high], linestyle='--', color='#7f8c8d', linewidth=1)
    ax.text(high - 3, high - 6, 'claim = measurement', fontsize=8, color='#7f8c8d', ha='right')
    ax.axhline(independent['oracleCeiling'], color='#c0392b', linestyle=':', linewidth=1.2)
    ax.text(
        low + 1,
        independent['oracleCeiling'] + 1.2,
        f"oracle ceiling {independent['oracleCeiling']}% -- gold evidence sessions only, gpt-4o "
        '(jakecuth lab, 2026-11)',
        fontsize=7.8,
        color='#c0392b',
    )

    # The x floor is below the y floor on purpose: the labels sit to the left of their claims and
    # the longest one belongs to the claim at 60.4, so the panel needs that much room while the
    # data itself never goes below 45.
    ax.set_xlim(36, high)
    ax.set_ylim(low, high)
    ax.set_xlabel('vendor-claimed accuracy (%)', fontsize=10)
    ax.set_ylabel('accuracy under an independent re-run (%)', fontsize=10)
    ax.set_title(
        'LongMemEval-S: what is claimed against what a third party measured\n'
        'Every pair below the diagonal is a claim a re-run could not reproduce. A system with no\n'
        're-run appears only at its claim, and that absence is itself the finding.',
        fontsize=10.5,
    )
    ax.grid(True, linestyle=':', alpha=0.35)

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot_matched_model(_data: dict, out: Path) -> None:
    """The competitors as *this repository* measured them, on one model, one judge and one sample.

    Every other figure here compares published numbers, and a published number is a claim about a system plus a
    reader plus a judge. This panel removes two of the three: the system is the same binary, the model is
    `deepseek-chat` for both the system's own calls and the reader, and the judge and sample are one run's. What is
    left is the mechanism's price, which is the only axis a copy/don't-copy decision can use.

    The two coordinates are (prompt tokens the system caused to be read, accuracy). The token axis is the *system*
    total: what the reader read plus what the system spent producing it. For Mem0 those two halves differ by three
    orders of magnitude -- 407 tokens handed over, 544k spent extracting -- and a panel that plotted only the first
    would place the most expensive arm here at the cheap end of the axis, which is also exactly how a vendor's
    "context per question" figure reads.

    Rows sharing a `series` are one system at two settings, drawn joined: the segment between them is a *within-system*
    comparison and is the only movement on this panel that no cross-system confound can explain. Mastra's two rows are
    the equal-envelope experiment -- a tenfold lower `messageTokens` -- and the segment is 4% of the cost for 3.3 points
    of accuracy, which is what "the trigger does not control the number that is large" looks like when drawn.
    """
    data = json.loads(MATCHED.read_text(encoding='utf-8'))
    fig, ax = plt.subplots(figsize=(11, 7))

    # A series is drawn before the points so its line cannot cover a marker.
    by_series: dict[str, list[dict]] = {}
    for row in data['rows']:
        if 'series' in row:
            by_series.setdefault(row['series'], []).append(row)
    for rows in by_series.values():
        if len(rows) < 2:
            continue
        # The order the file lists them, which is baseline first and treatment second -- the same direction every
        # paired table in this repository reads. Sorting by coordinate would label the segment with the negative of
        # the movement it describes: `messageTokens` 30k -> 3k is -4.05% tokens, not +4.2%.
        ordered = rows
        ax.plot(
            [row['promptTokensPerQuestion'] for row in ordered],
            [row['accuracy'] for row in ordered],
            color='#aab7b8',
            linestyle='-',
            linewidth=1.4,
            zorder=2,
        )
        first, last = ordered[0], ordered[-1]
        delta_tokens = (last['promptTokensPerQuestion'] / first['promptTokensPerQuestion'] - 1) * 100
        delta_points = last['accuracy'] - first['accuracy']
        # Placed to the right of the segment rather than on it: both endpoints already carry a label, and a third
        # annotation between them printed over the lower point's own line.
        ax.text(
            max(row['promptTokensPerQuestion'] for row in ordered) * 1.12,
            (first['accuracy'] + last['accuracy']) / 2 - 0.9,
            f"{delta_tokens:+.1f}% tokens\n{delta_points:+.1f} points",
            ha='left',
            va='center',
            fontsize=7.8,
            color='#5d6d7e',
            bbox={'boxstyle': 'round,pad=0.25', 'facecolor': 'white', 'edgecolor': '#e5e8e8', 'alpha': 0.85},
            zorder=6,
        )

    cortex_arm = next(row for row in data['rows'] if row['system'] == 'cortex-session')
    # The reference arm's two coordinates as a crosshair, because every claim on this panel is relative to it: below
    # the horizontal line is less accurate than Cortex's own window, to the right of the vertical one costs more.
    ax.axhline(cortex_arm['accuracy'], color='#7f8c8d', linestyle='--', linewidth=1)
    ax.axvline(cortex_arm['promptTokensPerQuestion'], color='#7f8c8d', linestyle='--', linewidth=1)
    # The crosshair is explained in the footer rather than labelled on the line: rotated it ran through the reference
    # point's own annotation, and horizontal along the bottom it ran under the footer box. A caption is worth having
    # only where nothing else already occupies the space.

    for index, row in enumerate(data['rows']):
        filled = row['answerer'] == 'self'
        ax.scatter(
            row['promptTokensPerQuestion'],
            row['accuracy'],
            s=260 if row['type'] == 'cortex' else 200,
            marker='*' if filled else 'o',
            color=TYPE_COLOUR.get(row['type'], '#7f8c8d'),
            edgecolors='black',
            linewidths=1.2,
            zorder=4,
        )
        # Two rows share one accuracy (the n=2 pair sits at 50%), and a fixed offset over one of them printed both
        # labels on the same line. Alternating the vertical offset by position within the tie is what keeps the
        # labels attached to their own point.
        #
        # A later member of a series is pushed below its own point for the same reason one level over: its baseline
        # sits directly above it, so an upward label lands on the segment and on the baseline's label.
        tied = [other for other in data['rows'] if other['accuracy'] == row['accuracy']]
        lowered = any(row in rows[1:] for rows in by_series.values())
        offset = -34 if lowered else (18 if len(tied) == 1 or tied.index(row) % 2 == 0 else -30)
        ax.annotate(
            f"{row['system']}\n{row['accuracy']:.1f}% @ {row['promptTokensPerQuestion'] / 1000:,.0f}k tok/q (n={row['n']})",
            (row['promptTokensPerQuestion'], row['accuracy']),
            textcoords='offset points',
            xytext=(0, offset),
            ha='center',
            fontsize=8.2,
            zorder=5,
        )

    ax.set_xscale('log')
    ax.set_xlim(1_500, 4_000_000)
    ax.set_ylim(44, 78)
    # Plain numbers on a log axis: `10^5` makes a reader convert, and the whole point of this panel is that the
    # ratios between the coordinates are the finding.
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda value, _pos: f'{value:,.0f}'))
    ax.set_xlabel('prompt tokens the system caused to be read, per question (log)', fontsize=10)
    ax.set_ylabel('accuracy under one shared judge (%)', fontsize=10)
    ax.grid(alpha=0.25, linestyle=':', which='both')
    ax.set_title(
        'The same systems, measured by this repository on one model\n'
        'star = answers on its own generator, circle = retrieved context read by the shared reader',
        fontsize=11,
    )
    # Counted from the rows rather than written down: this caption said `n=2 for mem0 and memcog` after Mem0 had
    # been re-run at n=30, and a footer that misstates the sample is the one label on a figure a reader takes as
    # metadata rather than as a result.
    arm_counts: dict[int, int] = {}
    for row in data['rows']:
        arm_counts[row['n']] = arm_counts.get(row['n'], 0) + 1
    sample_line = '; '.join(
        f"n={count} for {arms} arm{'s' if arms > 1 else ''}"
        for count, arms in sorted(arm_counts.items(), reverse=True)
    )
    ax.text(
        0.99,
        0.02,
        f'{sample_line}.\n'
        "Dashed crosshair: cortex-session's own coordinates — right of it costs more, below it scores less.\n"
        'Not the 500-question leaderboard: these rows price a mechanism, they do not rank a system.',
        transform=ax.transAxes,
        ha='right',
        va='bottom',
        fontsize=7.6,
        color='#5d6d7e',
        bbox={'boxstyle': 'round,pad=0.4', 'facecolor': 'white', 'edgecolor': '#d5dbdb', 'alpha': 0.9},
    )
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='exit 1 if a figure would change')
    parser.add_argument('--out-dir', type=Path, default=HERE)
    args = parser.parse_args(argv)

    data = load()
    targets = {
        args.out_dir / 'fig-longmemeval-accuracy-vs-cost.png': plot_accuracy_vs_cost,
        args.out_dir / 'fig-longmemeval-accuracy-ranking.png': plot_ranking,
        args.out_dir / 'fig-longmemeval-claim-vs-measurement.png': plot_claim_vs_measurement,
        args.out_dir / 'fig-longmemeval-matched-model.png': plot_matched_model,
    }
    return _render(data, targets, check=args.check)


def _render(data: dict, targets: dict, check: bool) -> int:
    """Draw every figure, and report whether any of them landed on different bytes."""
    changed = []
    for path, draw in targets.items():
        before = path.read_bytes() if path.exists() else None
        draw(data, path)
        after = path.read_bytes()
        if before != after:
            changed.append(path.name)
    if check and changed:
        print('figures would change: ' + ', '.join(changed))
        return 1
    print(f'{len(targets)} figures written to {next(iter(targets)).parent}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
