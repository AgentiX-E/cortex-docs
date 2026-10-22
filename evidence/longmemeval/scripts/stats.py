#!/usr/bin/env python3
"""Welch t-test on the 3-run aggregates + focused quantification of the
chain-of-note format-collapse failure mode."""

import json
import math
import re
import statistics as st
from pathlib import Path

BASE = Path('/workspace/analysis/baseline_da4fe96')
PJ = Path('/workspace/analysis/pjson')
BASE_RUNS = ['33704477428', '33704482878', '33704488080']
PJ_RUNS = ['33711087768', '33711092503', '33711097267']
CATS = ['IE', 'MR', 'KU', 'TR', 'ABS']


def metrics(path, run):
    m = json.loads((path / f'run_{run}' / 'benchmark-report.json').read_text())['feature']['metrics']
    d = {'overall': m['accuracy'], 'abst': m['abstentionRate']}
    for c in CATS:
        d[c] = m['perCapability'][c]['accuracy']
    return d


B = [metrics(BASE, r) for r in BASE_RUNS]
P = [metrics(PJ, r) for r in PJ_RUNS]


def welch(x, y):
    nx, ny = len(x), len(y)
    vx, vy = st.variance(x), st.variance(y)
    se = math.sqrt(vx / nx + vy / ny)
    if se == 0:
        return float('inf'), float('nan')
    t = (st.mean(x) - st.mean(y)) / se
    df = (vx / nx + vy / ny) ** 2 / ((vx / nx) ** 2 / (nx - 1) + (vy / ny) ** 2 / (ny - 1))
    # two-sided p from Student t via incomplete beta (regularized)
    def betacf(a, b, x):
        MAXIT, EPS, FPMIN = 200, 3e-16, 1e-300
        qab, qap, qam = a + b, a + 1, a - 1
        c, d = 1.0, 1 - qab * x / qap
        if abs(d) < FPMIN:
            d = FPMIN
        d = 1 / d
        h = d
        for m in range(1, MAXIT + 1):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1 + aa * d
            if abs(d) < FPMIN:
                d = FPMIN
            c = 1 + aa / c
            if abs(c) < FPMIN:
                c = FPMIN
            d = 1 / d
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1 + aa * d
            if abs(d) < FPMIN:
                d = FPMIN
            c = 1 + aa / c
            if abs(c) < FPMIN:
                c = FPMIN
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
        lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        bt = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
        if x < (a + 1) / (a + b + 2):
            return bt * betacf(a, b, x) / a
        return 1 - bt * betacf(b, a, 1 - x) / b

    p = betai(df / 2, 0.5, df / (df + t * t))
    return t, p


print('== Welch t-test on 3-run aggregates (baseline n=3 vs p-json n=3) ==')
print(f'{"metric":8s} {"base avg":>9s} {"pjson avg":>10s} {"delta pp":>9s} {"t":>7s} {"p":>8s}  verdict')
for c in ['overall', 'abst'] + CATS:
    bv = [d[c] for d in B]
    pv = [d[c] for d in P]
    t, p = welch(pv, bv)
    verdict = 'SIGNIFICANT' if p < 0.05 else ('marginal' if p < 0.10 else 'not significant')
    print(f'{c:8s} {st.mean(bv)*100:8.2f}% {st.mean(pv)*100:9.2f}% '
          f'{(st.mean(pv)-st.mean(bv))*100:+8.2f}  {t:6.2f}  {p:7.4f}  {verdict}')

# ---- chain-of-note format collapse ----------------------------------------
def load(path):
    out = {}
    for f, cap in (('benchmark-single-session-diagnostics.json', None),
                   ('benchmark-mr-diagnostics.json', 'MR')):
        for x in json.loads((path / f).read_text()):
            out[x['question_id']] = {
                'cap': x.get('capability', cap),
                'q': x['question'],
                'gt': x.get('ground_truth'),
                'ans': x['decision'].get('answer'),
                'raw': x['decision'].get('llmRaw', '') or '',
            }
    return out


print('\n== chain-of-note format collapse (no "Answer:" line, narration leaked into the answer) ==')
rows = []
for label, path, runs in (('baseline', BASE, BASE_RUNS), ('p-json', PJ, PJ_RUNS)):
    per_run = []
    for r in runs:
        d = load(path / f'run_{r}')
        leak = [i for i, v in d.items()
                if isinstance(v['ans'], str)
                and re.search(r'(?i)\bstep\s*[12]\b', v['ans'])
                and not re.search(r'(?im)^\s*\*{0,2}(?:final )?answer\s*\*{0,2}\s*:', v['raw'])]
        per_run.append((len(leak), len(d), d, leak))
    n = [x[0] for x in per_run]
    print(f'  {label:9s} leaked answers per run: {n}  (of {per_run[0][1]} diagnosed questions, '
          f'{st.mean(n)/per_run[0][1]*100:.1f}% avg)')
    caps = {}
    for _, _, d, leak in per_run:
        for i in leak:
            caps[d[i]['cap']] = caps.get(d[i]['cap'], 0) + 1
    print(f'            by capability (3 runs pooled): {caps}')
    rows.append((label, per_run))

# how many leaked questions still carry the correct answer somewhere in the narration
d = load(PJ / f'run_{PJ_RUNS[0]}')
leak = [i for i, v in d.items()
        if isinstance(v['ans'], str) and re.search(r'(?i)\bstep\s*[12]\b', v['ans'])]
contained = 0
for i in leak:
    gt = str(d[i]['gt']).strip().lower()
    if gt and gt in str(d[i]['ans']).lower():
        contained += 1
print(f'\n  p-json run1: {len(leak)} leaked answers; the ground-truth string is present verbatim '
      f'in the narration in {contained} of them -> recoverable by a better parser')

# runaway generations
print('\n== runaway generations (answer > 1000 chars) ==')
for label, path, runs in (('baseline', BASE, BASE_RUNS), ('p-json', PJ, PJ_RUNS)):
    cnt = 0
    mx = 0
    for r in runs:
        d = load(path / f'run_{r}')
        for v in d.values():
            if isinstance(v['ans'], str):
                if len(v['ans']) > 1000:
                    cnt += 1
                mx = max(mx, len(v['ans']))
    print(f'  {label:9s} count={cnt:3d} (3 runs pooled)  longest answer={mx} chars')
