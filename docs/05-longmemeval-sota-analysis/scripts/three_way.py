#!/usr/bin/env python3
"""Three-way same-day comparison: CP4 baseline (da4fe96) -> P-json (7a349da)
-> CoN contract fix (8d87341), on the `nl-abstain-feature` system.

Usage: python3 three_way.py <fix_run_id> [<fix_run_id> ...]
"""

import json
import math
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path('/workspace/analysis')
BASE = ROOT / 'baseline_da4fe96'
PJ = ROOT / 'pjson'
FIX = ROOT / 'fix_8d87341'
BASE_RUNS = ['33704477428', '33704482878', '33704488080']
PJ_RUNS = ['33711087768', '33711092503', '33711097267']
CATS = ['IE', 'MR', 'KU', 'TR', 'ABS']
FIX_RUNS = sys.argv[1:]


def metrics(path, run):
    m = json.loads((path / f'run_{run}' / 'benchmark-report.json').read_text())['feature']['metrics']
    d = {'overall': m['accuracy'], 'abst': m['abstentionRate']}
    for c in CATS:
        d[c] = m['perCapability'][c]['accuracy']
    return d


def betacf(a, b, x):
    MAXIT, EPS, FPMIN = 200, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = FPMIN if abs(d) < FPMIN else d
    d = 1 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = FPMIN if abs(d) < FPMIN else d
        c = 1 + aa / c
        c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = FPMIN if abs(d) < FPMIN else d
        c = 1 + aa / c
        c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    )
    return bt * betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * betacf(b, a, 1 - x) / b


def welch(x, y):
    nx, ny = len(x), len(y)
    vx, vy = st.variance(x), st.variance(y)
    se = math.sqrt(vx / nx + vy / ny)
    if se == 0:
        return 0.0, 1.0
    t = (st.mean(x) - st.mean(y)) / se
    df = (vx / nx + vy / ny) ** 2 / ((vx / nx) ** 2 / (nx - 1) + (vy / ny) ** 2 / (ny - 1))
    return t, betai(df / 2, 0.5, df / (df + t * t))


groups = [
    ('baseline da4fe96', [metrics(BASE, r) for r in BASE_RUNS]),
    ('p-json  7a349da', [metrics(PJ, r) for r in PJ_RUNS]),
]
if FIX_RUNS:
    groups.append(('con-fix 8d87341', [metrics(FIX, r) for r in FIX_RUNS]))

print('== per-run overall accuracy ==')
for name, g in groups:
    vals = [d['overall'] for d in g]
    print(f'  {name}: ' + ', '.join(f'{v*100:.2f}%' for v in vals) +
          f'   avg={st.mean(vals)*100:.2f}%  min={min(vals)*100:.2f}%  std={st.pstdev(vals)*100:.2f}')

print('\n== per-metric deltas vs the previous stage ==')
for i in range(1, len(groups)):
    prev, cur = groups[i - 1], groups[i]
    print(f'\n  {prev[0]}  ->  {cur[0]}')
    print(f'    {"metric":8s} {"prev":>9s} {"cur":>9s} {"delta pp":>9s} {"t":>7s} {"p":>8s}  verdict')
    for c in ['overall', 'abst'] + CATS:
        a = [d[c] for d in prev[1]]
        b = [d[c] for d in cur[1]]
        t, p = welch(b, a)
        verdict = 'SIGNIFICANT' if p < 0.05 else ('marginal' if p < 0.10 else 'not significant')
        print(f'    {c:8s} {st.mean(a)*100:8.2f}% {st.mean(b)*100:8.2f}% '
              f'{(st.mean(b)-st.mean(a))*100:+8.2f}  {t:6.2f}  {p:7.4f}  {verdict}')

# ---- failure-mode quantification ------------------------------------------
def load(path):
    out = {}
    for f, cap in (('benchmark-single-session-diagnostics.json', None),
                   ('benchmark-mr-diagnostics.json', 'MR')):
        p = path / f
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            out[x['question_id']] = {
                'cap': x.get('capability', cap),
                'ans': x['decision'].get('answer'),
                'raw': x['decision'].get('llmRaw', '') or '',
            }
    return out


def leak_stats(path, runs):
    counts, longest = [], 0
    for r in runs:
        d = load(path / f'run_{r}')
        n = sum(1 for v in d.values()
                if isinstance(v['ans'], str)
                and re.search(r'(?i)\bstep\s*[12]\b', v['ans'])
                and not re.search(r'(?im)^\s*\*{0,2}(?:final )?answer\s*\*{0,2}\s*:', v['raw']))
        counts.append((n, len(d)))
        longest = max(longest, max((len(v['ans']) for v in d.values() if isinstance(v['ans'], str)), default=0))
    return counts, longest


print('\n== chain-of-note format collapse ==')
for name, path, runs in (
    ('baseline da4fe96', BASE, BASE_RUNS),
    ('p-json  7a349da', PJ, PJ_RUNS),
    ('con-fix 8d87341', FIX, FIX_RUNS),
):
    if not runs:
        continue
    counts, longest = leak_stats(path, runs)
    tot = counts[0][1]
    rate = st.mean([c[0] for c in counts]) / tot * 100
    print(f'  {name}: leaked {[c[0] for c in counts]} / {tot}  ({rate:.2f}% avg)  longest answer={longest} chars')
