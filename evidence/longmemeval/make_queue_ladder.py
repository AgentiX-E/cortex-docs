"""What the remaining queue costs, priced two ways (cortex, 2026-11-25).

Left: the seven remaining steps as they were priced (whole file x 4 repetitions x 2 arms) against what
they cost once the population and the repetitions are the ones the mechanism needs.
Right: every design `tools/spend-projection.mjs` can price today, with measured bills filled and
census-scaled floors hatched -- the distinction the dispatch gate keys on.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# (label, old CNY, new CNY, basis)  basis: measured | floor | scaled
STEPS = [
    ('⑨ Step-N heading contract\n(MR only)', 16.00, 5.87, 'measured'),
    ('⑤ KU conflict block\n(KU only)', 4.60, 1.03, 'floor'),
    ('④ 60-question pinned judge', 2.00, 0.86, 'scaled'),
    ('⑧ thinking confound\n(MR, two dispatches)', 16.00, 5.88, 'measured'),
    ('③c file confirmation\n(third repetition)', 16.00, 3.57, 'scaled'),
    ('⑥ 600 width\n(MR + TR)', 15.64, 7.68, 'mixed'),
    ('⑦ zhipu:glm-4.6 reader\n(MR)', 26.00, 1.81, 'floor'),
]

# (label, CNY, basis)
LADDER = [
    ('60 q x 1', 0.43, 'scaled'),
    ('60 q x 2', 0.86, 'scaled'),
    ('TR x 2', 1.81, 'floor'),
    ('MR x 1', 2.94, 'measured'),
    ('file x 1', 3.57, 'scaled'),
    ('MR x 2', 5.87, 'measured'),
    ('file x 2', 7.13, 'scaled'),
    ('MR x 4', 11.74, 'measured'),
    ('file x 4', 14.26, 'measured'),
]

FILL = {'measured': '#c62828', 'floor': '#ef6c00', 'scaled': '#1565c0', 'mixed': '#6a1b9a'}
OLD = '#bdbdbd'

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 6.6), gridspec_kw={'width_ratios': [1.45, 1]})

# ---------------------------------------------------------------- left: the queue, two prices
labels = [row[0] for row in STEPS]
old = [row[1] for row in STEPS]
new = [row[2] for row in STEPS]
y = list(range(len(STEPS)))[::-1]
height = 0.36

ax1.barh([v + height / 2 + 0.02 for v in y], old, height=height, color=OLD, edgecolor='#757575',
         linewidth=.6, label='priced as whole file x 4 repetitions x 2 arms')
for v, value, basis in zip(y, new, [row[3] for row in STEPS]):
    ax1.barh(v - height / 2 - 0.02, value, height=height, color=FILL[basis],
             edgecolor='#263238', linewidth=.7,
             hatch='//' if basis in ('floor', 'mixed') else None)
ax1.set_yticks(y)
ax1.set_yticklabels(labels, fontsize=9.5)
ax1.set_ylim(-1.35, len(STEPS) - 0.45)
ax1.set_xscale('log')
ax1.set_xlim(0.3, 60)
ax1.set_xticks([0.5, 1, 2, 5, 10, 20, 50])
ax1.set_xticklabels(['0.5', '1', '2', '5', '10', '20', '50'])
ax1.set_xlabel('CNY per dispatch (log scale)', fontsize=10)
ax1.axvline(10, color='#2e7d32', lw=1.6, ls='--')
ax1.text(10.4, -0.95, '¥10 budget', color='#2e7d32', fontsize=10, fontweight='bold', va='center')

total_old = sum(old)
total_new = sum(new)
ax1.set_title(
    f'The same seven steps, priced two ways: ¥{total_old:.0f} → ¥{total_new:.0f}\n'
    'and ⑨+⑤+④ = ¥7.76 fits under the line',
    fontsize=12, loc='left')

for v, o, n in zip(y, old, new):
    ax1.text(o * 1.06, v + height / 2 + 0.02, f'{o:.2f}' if o < 10 else f'{o:.0f}',
             va='center', fontsize=8.5, color='#616161')
    ax1.text(n * 1.06, v - height / 2 - 0.02, f'{n:.2f}', va='center', fontsize=9,
             fontweight='bold', color='#263238')

# ---------------------------------------------------------------- right: the priced ladder
names = [row[0] for row in LADDER]
values = [row[1] for row in LADDER]
basis = [row[2] for row in LADDER]
positions = list(range(len(LADDER)))[::-1]
bars = ax2.barh(positions, values, height=.62,
                color=[FILL[b] for b in basis], edgecolor='#263238', linewidth=.7)
for bar, b in zip(bars, basis):
    if b == 'floor':
        bar.set_hatch('//')
ax2.set_yticks(positions)
ax2.set_yticklabels(names, fontsize=10)
ax2.set_xlim(0, 17)
ax2.set_xlabel('CNY per dispatch', fontsize=10)
ax2.axvline(10, color='#2e7d32', lw=1.6, ls='--')
for pos, value in zip(positions, values):
    ax2.text(value + 0.3, pos, f'{value:.2f}', va='center', fontsize=9.5, fontweight='bold',
             color='#263238')
ax2.set_title('Every design the projection prices today\n'
              'filled = billed · hatched = census-scaled floor',
              fontsize=12, loc='left')

legend = [
    Patch(facecolor=FILL['measured'], edgecolor='#263238', label='measured from a bill'),
    Patch(facecolor=FILL['floor'], edgecolor='#263238', hatch='//', label='floor (no bill yet)'),
    Patch(facecolor=FILL['scaled'], edgecolor='#263238', label='file-scaled, exact'),
    Patch(facecolor=FILL['mixed'], edgecolor='#263238', hatch='//', label='mixed: measured + floor'),
    Patch(facecolor=OLD, edgecolor='#757575', label='the old price (whole file x 4 x 2 arms)'),
    Line2D([0], [0], color='#2e7d32', ls='--', lw=1.6, label='¥10'),
]
fig.legend(handles=legend, loc='lower center', ncol=3, fontsize=9.5, frameon=False,
           bbox_to_anchor=(0.5, -0.015))

fig.suptitle('A cheap design could not be quoted, so every step looked expensive',
             fontsize=14, fontweight='bold', x=0.012, ha='left', y=0.985)
fig.text(0.012, 0.935,
         'MR\'s question-run is 0.0243 CNY against the file\'s 0.0064 (3.8x, it carries the reasoning), '
         'so the census was the right unit for how many questions\na scoped run asks and the wrong unit for '
         'what they cost. The bill is now in the baseline and the rate is derived from it.',
         fontsize=9.5, color='#424242', va='top')

fig.tight_layout(rect=[0, 0.055, 1, 0.90])
fig.savefig('cortex-queue-ladder-2026-11-25.png', dpi=200, bbox_inches='tight', facecolor='white')
print('wrote cortex-queue-ladder-2026-11-25.png')
