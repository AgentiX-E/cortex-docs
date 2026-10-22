#!/usr/bin/env python3
"""Drift-corrected estimate of the CoN contract fix's effect.

The fix touches only the four prompts that spread `conInstruction()` and the
`parseQaAnswer` safety net. Verified boundaries:

  * MR uses `buildAggregationQaPrompt` + `parseAggregationAnswer` — a different
    prompt AND a different parser.
  * KU falls back to `buildKnowledgeUpdatePrompt`, whose CoN wording is inlined
    and untouched; its answers are all < 48 chars with zero bullet lines, so the
    narration stripper never fires on them.

KU and MR therefore form an internal control: any change in them is same-day
drift plus LLM-service variance, not the patch. That drift is extrapolated to
the treated capabilities (IE, TR) to separate the fix's effect from the noise.
"""

import json
import statistics as st
from pathlib import Path

CATS = {'IE': 150, 'TR': 127, 'MR': 121, 'KU': 72, 'ABS': 30}
TREATED = ['IE', 'TR']
CONTROL = ['KU', 'MR']
PJ = Path('/workspace/analysis/pjson')
FIX = Path('/workspace/analysis/fix_8d87341')
PJ_RUNS = ['33711087768', '33711092503', '33711097267']
FIX_RUNS = ['33722572103', '33722575163', '33722578296']


def acc(path, run, cap):
    m = json.loads((path / f'run_{run}' / 'benchmark-report.json').read_text())['feature']['metrics']
    return m['perCapability'][cap]['accuracy']


print('== per-capability mean accuracy (3 runs each) ==')
print(f'  {"cap":5s} {"n":>4s} {"p-json":>8s} {"con-fix":>8s} {"delta pp":>9s}  role')
rows = {}
for cap in ['IE', 'TR', 'KU', 'MR', 'ABS']:
    p = st.mean([acc(PJ, r, cap) for r in PJ_RUNS])
    f = st.mean([acc(FIX, r, cap) for r in FIX_RUNS])
    rows[cap] = (p, f)
    role = 'treated' if cap in TREATED else ('control' if cap in CONTROL else 'independent')
    print(f'  {cap:5s} {CATS[cap]:4d} {p*100:7.2f}% {f*100:7.2f}% {(f-p)*100:+8.2f}   {role}')

# Drift measured on the untouched control capabilities, in question counts.
ctrl_n = sum(CATS[c] for c in CONTROL)
ctrl_delta_q = sum((rows[c][1] - rows[c][0]) * CATS[c] for c in CONTROL)
drift = ctrl_delta_q / ctrl_n
print(f'\n== drift estimate from the control capabilities (KU + MR, n={ctrl_n}) ==')
for c in CONTROL:
    dq = (rows[c][1] - rows[c][0]) * CATS[c]
    print(f'  {c}: {(rows[c][1]-rows[c][0])*100:+.2f} pp  =  {dq:+.2f} questions')
print(f'  pooled drift: {ctrl_delta_q:+.2f} questions / {ctrl_n} = {drift*100:+.2f} pp '
      f'(attributable to same-day drift + service variance, not the patch)')

# Apply that drift to the treated capabilities.
treat_n = sum(CATS[c] for c in TREATED)
treat_observed_q = sum((rows[c][1] - rows[c][0]) * CATS[c] for c in TREATED)
treat_expected_drift_q = drift * treat_n
effect_q = treat_observed_q - treat_expected_drift_q
print(f'\n== drift-corrected effect on the treated capabilities (IE + TR, n={treat_n}) ==')
print(f'  observed change      : {treat_observed_q:+.2f} questions')
print(f'  expected drift alone : {treat_expected_drift_q:+.2f} questions')
print(f'  corrected effect     : {effect_q:+.2f} questions  ({effect_q/treat_n*100:+.2f} pp on those {treat_n})')
print(f'  scaled to 500        : {effect_q/500*100:+.2f} pp overall-equivalent')

print('\n== caveat ==')
print('  The correction assumes drift hits every capability equally. KU and MR are')
print('  the best available control because the patch provably cannot reach them, but')
print('  they are not randomised. Treat this as an estimate; only a same-instant A/B')
print('  run (both commits dispatched at the same time) can settle it.')
