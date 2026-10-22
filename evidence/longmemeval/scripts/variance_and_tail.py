#!/usr/bin/env python3
"""Variance and tail analysis of the same-instant A/B.

The mean difference is not significant, but the arms differ sharply in SPREAD.
A patch that removes an occasional catastrophe (a 33 KB runaway, a narration
leaking into the answer) should lift the floor, not the ceiling — which is
exactly the pattern to test for here.
"""

import json
import math
import statistics as st
from pathlib import Path

CATS = ['IE', 'MR', 'KU', 'TR', 'ABS']
CTRL = ['33734287180', '33734290087', '33734293014']
TREAT = ['33734298345', '33734302150', '33734307358']


def load(path, run):
    m = json.loads((Path(path) / f'run_{run}' / 'benchmark-report.json').read_text())['feature']['metrics']
    d = {'overall': m['accuracy'], 'abst': m['abstentionRate'], 'correct': m['correct']}
    for c in CATS:
        d[c] = m['perCapability'][c]['accuracy']
    return d


C = [load('/workspace/analysis/ab_pjson', r) for r in CTRL]
T = [load('/workspace/analysis/ab_fix', r) for r in TREAT]


def f_test(a, b):
    """Two-tailed F-test for equality of variances (a vs b)."""
    va, vb = st.variance(a), st.variance(b)
    if vb == 0:
        return float('inf'), 0.0
    F = va / vb
    df1, df2 = len(a) - 1, len(b) - 1
    # p via the regularized incomplete beta (betai from the Welch helper)
    def betacf(x, aa, bb):
        MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
        qab, qap, qam = aa + bb, aa + 1, aa - 1
        c, d = 1.0, 1 - qab * x / qap
        d = FPMIN if abs(d) < FPMIN else d
        d = 1 / d
        h = d
        for m in range(1, MAXIT + 1):
            m2 = 2 * m
            num = m * (bb - m) * x / ((qam + m2) * (aa + m2))
            d = 1 + num * d
            d = FPMIN if abs(d) < FPMIN else d
            c = 1 + num / c
            c = FPMIN if abs(c) < FPMIN else c
            d = 1 / d
            h *= d * c
            num = -(aa + m) * (qab + m) * x / ((aa + m2) * (qap + m2))
            d = 1 + num * d
            d = FPMIN if abs(d) < FPMIN else d
            c = 1 + num / c
            c = FPMIN if abs(c) < FPMIN else c
            d = 1 / d
            de = d * c
            h *= de
            if abs(de - 1) < EPS:
                break
        return h

    def betai(aa, bb, x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        bt = math.exp(math.lgamma(aa + bb) - math.lgamma(aa) - math.lgamma(bb)
                      + aa * math.log(x) + bb * math.log(1 - x))
        return bt * betacf(x, aa, bb) / aa if x < (aa + 1) / (aa + bb + 2) else 1 - bt * betacf(1 - x, bb, aa) / bb

    x = df2 / (df2 + df1 * F)
    p = 2 * min(betai(df2 / 2, df1 / 2, x), 1 - betai(df2 / 2, df1 / 2, x))
    return F, min(1.0, p)


print('== spread: does the fix remove the tail risk rather than raise the ceiling? ==')
print(f'{"metric":9s} {"ctrl std":>9s} {"treat std":>10s} {"F":>9s} {"p":>8s}  {"ctrl min":>9s} {"treat min":>10s} {"min gain":>10s}')
for c in ['overall', 'IE', 'TR', 'KU', 'MR']:
    a = [d[c] for d in C]
    b = [d[c] for d in T]
    F, p = f_test(a, b)
    print(f'{c:9s} {st.pstdev(a)*100:8.2f}pp {st.pstdev(b)*100:9.2f}pp {F:8.1f} {p:7.4f}  '
          f'{min(a)*100:8.2f}% {min(b)*100:9.2f}% {(min(b)-min(a))*100:+9.2f}pp')

print('\n== the ceiling barely moves, the floor lifts ==')
for c in ['overall']:
    a = sorted(d[c] for d in C)
    b = sorted(d[c] for d in T)
    print(f'  {c}: control  {[round(x*100,2) for x in a]}')
    print(f'  {c}: treatment {[round(x*100,2) for x in b]}')
    print(f'  worst case: {min(a)*100:.2f}% -> {min(b)*100:.2f}%  ({(min(b)-min(a))*100:+.2f}pp)')
    print(f'  best  case: {max(a)*100:.2f}% -> {max(b)*100:.2f}%  ({(max(b)-max(a))*100:+.2f}pp)')

print('\n== how often does each arm dip below a quality floor? ==')
for floor in (0.78, 0.775, 0.77):
    ca = sum(1 for d in C if d['overall'] < floor)
    ta = sum(1 for d in T if d['overall'] < floor)
    print(f'  below {floor*100:.1f}%: control {ca}/3 runs, treatment {ta}/3 runs')

print('\n== abstention (the mechanism) ==')
a = [d['abst'] for d in C]
b = [d['abst'] for d in T]
print(f'  control {st.mean(a)*100:.2f}% (std {st.pstdev(a)*100:.2f})  ->  '
      f'treatment {st.mean(b)*100:.2f}% (std {st.pstdev(b)*100:.2f})   {(st.mean(b)-st.mean(a))*100:+.2f}pp')

print('\n== what the same-instant design changed about the earlier read ==')
print('  Earlier (staggered, 03:22Z vs 06:17Z) the staggered comparison credited IE with')
print('  +2.67pp at p=0.033. Under the same-instant design IE reads -1.11pp at p=0.38:')
print('  that apparent gain was time-of-day drift, not the patch.')
rows = [('IE', 88.89, 89.56, 90.89, 89.78), ('TR', 70.60, 71.39, 70.60, 71.13),
        ('MR', 67.77, 64.19, 63.91, 66.94), ('KU', 78.70, 75.93, 75.46, 77.31)]
print(f'\n  {"cap":4s} {"staggered ctrl":>15s} {"staggered treat":>16s} {"same-inst ctrl":>16s} {"same-inst treat":>16s}')
for cap, a1, b1, a2, b2 in rows:
    print(f'  {cap:4s} {a1:14.2f}% {b1:15.2f}% {a2:15.2f}% {b2:15.2f}%')
