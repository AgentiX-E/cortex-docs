"""Accuracy x cost position for cortex against the published board (LongMemEval-S, 500 questions).

    python3 tools/render-position.py

Every point is a figure somebody published or this repository measured; the two rings are cortex readings
whose confirmation is still outstanding, drawn open so they cannot be read as shipped. `COST_ROWS` is the
subset with a published token count, `ALL_ROWS` is the whole board.
"""
import matplotlib
matplotlib.use('Agg')
import pathlib

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# (label, accuracy %, prompt tokens per question, kind)  kind: oss-ts | oss-py | closed
COST_ROWS = [
    ('cortex (registered, 400 cap)', 91.20, 7448, 'oss-ts'),
    ('cortex (600 cap, pending control)', 93.40, 7242, 'pending'),
    ('cortex + resolution: layered (R4 pending)', 93.60, 7461, 'pending'),
    ('Maximem Synap', 95.6, 7400, 'closed'),
    ('Mem0 (managed)', 94.4, 6800, 'closed'),
    ('Mastra OM', 94.87, 30000, 'oss-ts'),
    ('Hindsight', 94.6, 43600, 'closed'),
    ('Zep', 90.2, 4400, 'closed'),
]
ALL_ROWS = [
    ('Recallium', 98.4, 'closed'),
    ('ContextStream', 96.8, 'closed'),
    ('agentmemory V4', 96.2, 'oss-py'),
    ('MemCog', 95.80, 'closed'),
    ('Maximem Synap', 95.6, 'closed'),
    ('Mastra OM', 94.87, 'oss-ts'),
    ('Hindsight', 94.6, 'closed'),
    ('Mem0 (managed)', 94.4, 'closed'),
    ('cortex (600, pending)', 93.40, 'pending'),
    ('cortex + layered (R4 pending)', 93.60, 'pending'),
    ('cortex (registered)', 91.20, 'oss-ts'),
    ('Zep', 90.2, 'closed'),
    ('RAW-RAG', 87.53, 'oss-py'),
]
STYLE = {
    'oss-ts': dict(marker='o', color='#c62828', s=110, zorder=5),
    'oss-py': dict(marker='^', color='#ef6c00', s=100, zorder=5),
    'closed': dict(marker='s', color='#1565c0', s=90, zorder=4, alpha=.85),
    'pending': dict(marker='o', facecolors='none', edgecolors='#c62828', s=170, linewidths=2.2, zorder=6),
}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 6.6), gridspec_kw={'width_ratios': [1.15, 1]})

for label, acc, tok, kind in COST_ROWS:
    ax1.scatter(tok, acc, **STYLE[kind])
    dx, dy = (10, 6)
    arrow = None
    if label.startswith('cortex (registered'):
        dx, dy = (12, -22)
    if label.startswith('cortex (600'):
        dx, dy = (16, 14)
    if label.startswith('cortex + resolution'):
        # The two rings sit 0.2 points and 3% apart, so their labels are placed on opposite sides with a
        # leader line: two annotations stacked on one point is how a reader concludes there is one point.
        dx, dy = (18, -46)
        arrow = dict(arrowstyle='-', color='#9e9e9e', lw=.8, shrinkA=2, shrinkB=4)
    ax1.annotate(label, (tok, acc), textcoords='offset points', xytext=(dx, dy), fontsize=8.4,
                 arrowprops=arrow)

ax1.set_xscale('log')
ax1.set_xlabel('Prompt tokens per question (log scale)')
ax1.set_ylabel('LongMemEval-S accuracy (%)')
ax1.set_title('Accuracy against cost, published points only')
ax1.grid(alpha=.25, which='both')
ax1.set_ylim(88, 97.5)
ax1.set_xlim(3800, 52000)

# The frontier line through the published cost points.
xs = [4400, 6800, 7400]
ys = [90.2, 94.4, 95.6]
ax1.plot(xs, ys, '--', color='#616161', lw=1, alpha=.7, zorder=2)

def handle(kind, label):
    style = dict(STYLE[kind])
    for key in ('s', 'zorder', 'facecolors', 'edgecolors', 'linewidths', 'alpha'):
        style.pop(key, None)
    return Line2D([], [], linestyle='none', markersize=9, label=label,
                  markerfacecolor='none' if kind == 'pending' else style.pop('color', 'k'),
                  markeredgecolor=STYLE[kind].get('edgecolors', STYLE[kind].get('color', 'k')),
                  **style)

handles = [
    handle('oss-ts', 'self-hosted, TypeScript'),
    handle('oss-py', 'open source, Python'),
    handle('closed', 'closed cloud service'),
    handle('pending', 'cortex, reading not yet confirmed'),
]
ax1.legend(handles=handles, fontsize=8.4, loc='lower right')

order = sorted(ALL_ROWS, key=lambda r: r[1])
ypos = range(len(order))
for y, (label, acc, kind) in zip(ypos, order):
    ax2.barh(y, acc, height=.62, color=STYLE[kind].get('color', '#c62828'), alpha=.9, zorder=3)
    ax2.text(acc + .35, y, f'{acc:.1f}', va='center', fontsize=8.6)
ax2.set_yticks(list(ypos))
ax2.set_yticklabels([r[0] for r in order], fontsize=8.6)
ax2.set_xlim(84, 101)
ax2.set_xlabel('LongMemEval-S accuracy (%)')
ax2.set_title('The board, whether or not a cost was published')
ax2.grid(axis='x', alpha=.25, zorder=0)
ax2.axvline(91.20, color='#c62828', ls='-', lw=1.2, alpha=.55, zorder=4)
ax2.axvline(93.60, color='#c62828', ls=':', lw=1.4, zorder=4)

fig.suptitle('cortex position, 2026-11-25: shipped 91.20% at 7,448 tokens/question; +2.40 points priced by a '
             'replication still short of p=0.05',
             fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.95))
OUT = pathlib.Path(__file__).resolve().parents[1] / 'evidence' / 'longmemeval' / 'position-2026-11-25.png'
fig.savefig(OUT, dpi=170)
print(f'wrote {OUT}')
