"""The reader-axis pair decomposed: where the 36 questions went, and what separates the rest.

Left panel  -- paired 2x2 per capability, `40698867439` (deepseek-chat) against `40698883428` (deepseek-v4-pro).
Right panel -- the one predicate that separates, on both readers, so the marker is read as a property of the
               contract rather than of the model.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CAPS = ['IE', 'MR', 'KU', 'TR', 'ABS']
N = [150, 121, 72, 127, 30]
LOST = [14, 13, 10, 21, 0]
GAINED = [2, 10, 2, 7, 1]
NET = [g - l for l, g in zip(LOST, GAINED)]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.0, 6.4), gridspec_kw={'width_ratios': [1.25, 1]})

xs = range(len(CAPS))
width = 0.38
bars_lost = ax1.bar([x - width / 2 for x in xs], LOST, width, color='#c62828', label='lost (control right, treatment wrong)')
bars_gain = ax1.bar([x + width / 2 for x in xs], GAINED, width, color='#2e7d32', label='gained (treatment right)')
for x, lost, gained, net, n in zip(xs, LOST, GAINED, NET, N):
    ax1.text(x, max(lost, gained) + 0.6, f'net {net:+d}', ha='center', va='bottom', fontsize=11, fontweight='bold',
             color='#c62828' if net < 0 else '#2e7d32')
    ax1.text(x, -2.6, f'n={n}', ha='center', va='top', fontsize=9, color='#616161')
ax1.axhline(0, color='#424242', linewidth=1)
ax1.set_xticks(list(xs))
ax1.set_xticklabels(CAPS)
ax1.set_ylim(-4, 25)
ax1.set_ylabel('questions')
ax1.set_title('Net -36 is 58 lost against 22 gained, and ABS moves the other way', fontsize=11)
ax1.legend(loc='upper left', fontsize=9, frameon=False)
ax1.spines[['top', 'right']].set_visible(False)

# Right panel: the discriminant, as two pairs of bars, one pair per reader.
groups = ['instantiated\nheading', 'generic\n"Step N" heading']
control = [87.6, 67.9]
treatment = [79.4, 66.1]
counts = [('394', '106'), ('379', '121')]

xs2 = range(len(groups))
b1 = ax2.bar([x - width / 2 for x in xs2], control, width, color='#1565c0', label='deepseek-chat (control)')
b2 = ax2.bar([x + width / 2 for x in xs2], treatment, width, color='#ef6c00', label='deepseek-v4-pro (treatment)')
for x, c, t, (cn, tn) in zip(xs2, control, treatment, counts):
    ax2.text(x - width / 2, c + 0.8, f'{c:.1f}%\nn={cn}', ha='center', va='bottom', fontsize=9)
    ax2.text(x + width / 2, t + 0.8, f'{t:.1f}%\nn={tn}', ha='center', va='bottom', fontsize=9)
ax2.set_xticks(list(xs2))
ax2.set_xticklabels(groups)
ax2.set_ylim(0, 118)
ax2.set_ylabel('accuracy (%)')
ax2.set_title('The marker separates on both readers: 19.7 and 13.3 points', fontsize=11)
for x, gap in zip(xs2, [-19.7, -13.3]):
    ax2.text(x, 12, f'{gap:+.1f} pp', ha='center', va='center', fontsize=11, fontweight='bold', color='#424242',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#bdbdbd'))
ax2.legend(loc='upper center', ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, 1.02))
ax2.spines[['top', 'right']].set_visible(False)

fig.suptitle('Reader axis 417 -> 381: the loss is not declines, and the marker is the contract\'s', fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig('/workspace/charts/cortex-reader-axis-2026-11-25.png', dpi=150)
print('wrote cortex-reader-axis-2026-11-25.png')
