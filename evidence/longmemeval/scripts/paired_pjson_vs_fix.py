#!/usr/bin/env python3
"""Question-level paired comparison of p-json (7a349da) vs con-fix (8d87341),
per capability, to separate a real regression from same-day noise.

Scoring reproduces the deterministic layers of judgeScorer (normalized exact
match, then the numeric verdict for counting questions). The LLM-judge fallback
cannot be replayed offline, so absolute accuracy here is a lower bound while the
paired discordance remains meaningful: both sides lose the same judge-graded
questions.
"""

import json
import re
import statistics as st
from math import comb
from pathlib import Path

PJ = Path('/workspace/analysis/pjson')
FIX = Path('/workspace/analysis/fix_8d87341')
PJ_RUNS = ['33711087768', '33711092503', '33711097267']
FIX_RUNS = ['33722572103', '33722575163', '33722578296']


def normalize(a):
    return re.sub(r'\s+', ' ', str(a).strip().lower())


def leading_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = re.match(r'^\$?\s*(-?\d[\d,]*(?:\.\d+)?)', v.strip())
    return float(m.group(1).replace(',', '')) if m else None


def is_counting(q):
    return re.search(r'\b(how many|how much|number of|count|total)\b', str(q), re.I) is not None


def score(question, expected, answer):
    if answer is None or answer == '':
        return False
    if normalize(answer) == normalize(expected):
        return True
    if is_counting(question):
        p, e = leading_number(answer), leading_number(expected)
        if p is not None and e is not None:
            return p == e
    return None


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
                'q': x['question'],
                'gt': x.get('ground_truth'),
                'ans': x['decision'].get('answer'),
                'abst': bool(x['decision'].get('abstained')),
            }
    return out


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) * 0.5 ** n for i in range(min(b, c) + 1)))


P = {r: load(PJ / f'run_{r}') for r in PJ_RUNS}
F = {r: load(FIX / f'run_{r}') for r in FIX_RUNS}
ids = sorted(set.intersection(*[set(P[r]) for r in PJ_RUNS], *[set(F[r]) for r in FIX_RUNS]))
caps = {i: P[PJ_RUNS[0]][i]['cap'] for i in ids}
print(f'paired questions: {len(ids)}')

print('\n== per-capability discordance, all 9 p-json x con-fix run pairs ==')
print('  cap   pjson-only  confix-only   net    mcnemar p (median)   verdict')
for cap in ['IE', 'TR', 'KU', 'MR']:
    nets, ps = [], []
    for pr in PJ_RUNS:
        for fr in FIX_RUNS:
            b = c = 0
            for i in ids:
                if caps[i] != cap:
                    continue
                sp = score(P[pr][i]['q'], P[pr][i]['gt'], P[pr][i]['ans'])
                sf = score(F[fr][i]['q'], F[fr][i]['gt'], F[fr][i]['ans'])
                if sp is True and sf is not True:
                    b += 1
                elif sf is True and sp is not True:
                    c += 1
            nets.append(c - b)
            ps.append(mcnemar(b, c))
    verdict = 'SIGNIFICANT' if st.median(ps) < 0.05 else ('marginal' if st.median(ps) < 0.10 else 'noise')
    print(f'  {cap:4s}  {st.mean([max(-n, 0) for n in nets]):8.1f}   {st.mean([max(n, 0) for n in nets]):9.1f}  '
          f'{st.mean(nets):+6.1f}   {st.median(ps):.4f}            {verdict}')

print('\n== abstention rate by capability (3-run mean) ==')
for cap in ['IE', 'TR', 'KU', 'MR']:
    sub = [i for i in ids if caps[i] == cap]
    pa = st.mean([sum(1 for i in sub if P[r][i]['abst']) for r in PJ_RUNS]) / len(sub) * 100
    fa = st.mean([sum(1 for i in sub if F[r][i]['abst']) for r in FIX_RUNS]) / len(sub) * 100
    print(f'  {cap:4s} n={len(sub):3d}  p-json {pa:5.2f}%  ->  con-fix {fa:5.2f}%   ({fa - pa:+.2f}pp)')

# Where did the con-fix MR outlier run actually lose ground?
print('\n== con-fix run-3 (33722578296) MR losses vs its own run-1 ==')
cap = 'MR'
sub = [i for i in ids if caps[i] == cap]
r1, r3 = FIX_RUNS[0], FIX_RUNS[2]
lost = [i for i in sub
        if score(F[r1][i]['q'], F[r1][i]['gt'], F[r1][i]['ans']) is True
        and score(F[r3][i]['q'], F[r3][i]['gt'], F[r3][i]['ans']) is not True]
print(f'  deterministic-correct in run1 but not run3: {len(lost)}')
for i in lost[:8]:
    print(f'    gt={str(F[r1][i]["gt"])[:24]:26s} run1={str(F[r1][i]["ans"])[:22]:24s} run3={str(F[r3][i]["ans"])[:22]}')
