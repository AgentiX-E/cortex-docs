import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

RULES = ['scoped-name','semver','one-version','description','license-file','files-dist-only',
         'public-access','engines-node','repository-directory','entry-inside-dist','workspace-targets-exist']
PKGS = ['cortex-ai','cortex-core','cortex-eval','cortex-memory','cortex-storage']
RED_BEFORE = {'public-access','engines-node','repository-directory'}

fig, (ax, ax2) = plt.subplots(1, 2, figsize=(16.5, 6.4), gridspec_kw={'width_ratios':[1.45,1]})
fig.patch.set_facecolor('white')

for i, pkg in enumerate(PKGS):
    for j, rule in enumerate(RULES):
        before = rule in RED_BEFORE
        ax.add_patch(Rectangle((j + 0.03, i + 0.10), 0.44, 0.80,
                               facecolor='#c62828' if before else '#cfd8dc',
                               edgecolor='white', linewidth=1.0))
        ax.add_patch(Rectangle((j + 0.53, i + 0.10), 0.44, 0.80,
                               facecolor='#2e7d32', edgecolor='white', linewidth=1.0))
ax.set_xlim(0, len(RULES)); ax.set_ylim(-0.55, len(PKGS))
ax.set_xticks([j + 0.5 for j in range(len(RULES))])
ax.set_xticklabels(RULES, rotation=40, ha='right', fontsize=8, rotation_mode='anchor')
ax.set_yticks([i + 0.5 for i in range(len(PKGS))])
ax.set_yticklabels(PKGS, fontsize=10)
ax.set_title('Fifteen consumer-visible facts were missing across five packages; now none are\n'
             'each cell is one reading before (left half) and after (right half) this round\n'
             '15 red  ->  0 red,  of 55 readings',
             fontsize=11, loc='left', pad=10)
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)

lines = [
    ('publishConfig.access',   'inside',  'cleared'),
    ('engines.node',           'inside',  'cleared'),
    ('repository.directory',   'inside',  'cleared'),
    ('workspace:* needs pnpm', 'inside',  'cleared'),
    ('no release workflow',    'inside',  'cleared'),
    ('NPM_TOKEN secret',       'outside', 'open'),
    ('org secret scanning',    'outside', 'open'),
]
ax2.axis('off')
ax2.set_title('What blocked a first publish, and what is left', fontsize=11, loc='left', pad=12)
for k, (label, side, state) in enumerate(reversed(lines)):
    colour = '#2e7d32' if state == 'cleared' else '#ef6c00'
    ax2.add_patch(Rectangle((0.02, k - 0.26), 0.045, 0.52, facecolor=colour, edgecolor='none'))
    ax2.text(0.10, k, label, fontsize=10.5, va='center', family='monospace')
    ax2.text(0.66, k, side, fontsize=9.5, va='center', color='#546e7a')
    ax2.text(0.82, k, state, fontsize=9.5, va='center', color=colour, fontweight='bold')
ax2.set_xlim(0, 1); ax2.set_ylim(-1.2, len(lines) - 0.3)
ax2.text(0.02, -0.85, 'the two that remain are credential provisioning,\nnot engineering: neither blocks the code',
         fontsize=10, style='italic', color='#37474f', va='top')

plt.tight_layout()
plt.savefig('cortex-release-readiness-2026-11-27.png', dpi=170, facecolor='white')
print('ok')
