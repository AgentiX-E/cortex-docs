#!/usr/bin/env python3
"""Same-instant A/B: control 7a349da vs treatment 8d87341.

Both arms were dispatched within 14 seconds of each other (08:36:41-08:36:55Z)
so that same-day LLM-service drift cannot favour either arm. This is the
definitive read on the chain-of-note contract fix.
"""

import json
import math
import re
import statistics as st
from pathlib import Path

CATS = ['IE', 'MR', 'KU', 'TR', 'ABS']
CTRL = ['33734287180', '33734290087', '33734293014']
TREAT = ['33734298345', '33734302150', '33734307358']
PC = Path('/workspace/analysis/ab_pjson')
PT = Path('/workspace/analysis/ab_fix')


def load(path, run):
    m = json.loads((path / f'run_{run}' / 'benchmark-report.json').read_text())['feature']['metrics']
    d = {'overall': m['accuracy'], 'abst': m['abstentionRate'], 'correct': m['correct']}
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
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1 - x))
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


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


C = [load(PC, r) for r in CTRL]
T = [load(PT, r) for r in TREAT]

print('== same-instant A/B: control 7a349da vs treatment 8d87341 ==')
print('   (dispatched 08:36:41-08:36:55Z, 14 s apart)\n')
hdr = f'{"arm":10s} {"run":12s} ' + ' '.join(f'{c:>7s}' for c in ['overall', 'abst'] + CATS)
print(hdr)
for label, runs, data in (('CONTROL', CTRL, C), ('TREATMENT', TREAT, T)):
    for r, d in zip(runs, data):
        print(f'{label:10s} {r[-6:]:12s} ' + ' '.join(f'{d[c]*100:6.2f}%' for c in ['overall', 'abst'] + CATS))

print(f'\n== deltas (Welch t-test, n=3 per arm) ==')
print(f'{"metric":9s} {"control":>9s} {"treat":>9s} {"delta pp":>9s} {"t":>7s} {"p":>8s}  {"95% CI of delta":>22s}  verdict')
for c in ['overall', 'abst'] + CATS:
    a = [d[c] for d in C]
    b = [d[c] for d in T]
    t, p = welch(b, a)
    # CI on the difference via Welch-Satterthwaite
    va, vb = st.variance(a), st.variance(b)
    se = math.sqrt(va / 3 + vb / 3)
    df = (va / 3 + vb / 3) ** 2 / ((va / 3) ** 2 / 2 + (vb / 3) ** 2 / 2)
    tc = 2.776 if df < 3 else (2.571 if df < 6 else 1.96)  # conservative
    lo, hi = (st.mean(b) - st.mean(a)) - tc * se, (st.mean(b) - st.mean(a)) + tc * se
    verdict = 'SIGNIFICANT' if p < 0.05 else ('marginal' if p < 0.10 else 'not significant')
    print(f'{c:9s} {st.mean(a)*100:8.2f}% {st.mean(b)*100:8.2f}% {(st.mean(b)-st.mean(a))*100:+8.2f}  '
          f'{t:6.2f}  {p:7.4f}  [{lo*100:+6.2f}, {hi*100:+6.2f}] pp  {verdict}')

print('\n== min / max per arm (robustness: does the worst case improve?) ==')
for c in ['overall', 'IE', 'TR']:
    a = [d[c] for d in C]
    b = [d[c] for d in T]
    print(f'  {c:8s} control min={min(a)*100:6.2f}% max={max(a)*100:6.2f}% std={st.pstdev(a)*100:5.2f}  |  '
          f'treat min={min(b)*100:6.2f}% max={max(b)*100:6.2f}% std={st.pstdev(b)*100:5.2f}')

print('\n== Wilson 95% CI on pooled overall (correct / 500 x 3 runs) ==')
for label, data in (('control', C), ('treatment', T)):
    k = sum(d['correct'] for d in data)
    n = 500 * len(data)
    lo, hi = wilson(k, n)
    print(f'  {label:10s} {k}/{n} = {k/n*100:5.2f}%  95% CI [{lo*100:5.2f}%, {hi*100:5.2f}%]')

# Failure mode check on the treatment arm
print('\n== chain-of-note format collapse (treatment arm, same-instant) ==')
for run in TREAT:
    leaked = 0
    longest = 0
    for f in ('benchmark-single-session-diagnostics.json', 'benchmark-mr-diagnostics.json'):
        p = PT / f'run_{run}' / f
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            ans = x['decision'].get('answer')
            raw = x['decision'].get('llmRaw', '') or ''
            if isinstance(ans, str):
                longest = max(longest, len(ans))
                if re.search(r'(?i)\bstep\s*[12]\b', ans) and not re.search(
                        r'(?im)^\s*\*{0,2}(?:final )?answer\s*\*{0,2}\s*:', raw):
                    leaked += 1
    print(f'  {run}: leaked={leaked}  longest answer={longest} chars')
