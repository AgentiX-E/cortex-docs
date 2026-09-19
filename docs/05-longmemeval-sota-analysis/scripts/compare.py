#!/usr/bin/env python3
"""Paired question-level analysis of the P-json (7a349da) benchmark runs against
the same-day CP4 baseline (da4fe96).

Scoring reproduces the deterministic layers of `judgeScorer` in
packages/cortex-eval/src/metrics.ts (normalized exact match, then numeric
verdict for counting questions). The LLM-judge fallback cannot be replayed
offline, so every number below is a conservative lower bound: pairs where the
judge would have supplied the verdict are scored as misses on both sides and
therefore cancel out of the paired comparison.
"""

import json
import re
import statistics as st
from pathlib import Path

BASE = Path('/workspace/analysis/baseline_da4fe96')
PJ = Path('/workspace/analysis/pjson')
BASE_RUNS = ['33704477428', '33704482878', '33704488080']
PJ_RUNS = ['33711087768', '33711092503', '33711097267']


def normalize(a):
    return str(a).strip().lower().replace('\s+', ' ') if False else re.sub(r'\s+', ' ', str(a).strip().lower())


def leading_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = v.strip().match if False else re.match(r'^\$?\s*(-?\d[\d,]*(?:\.\d+)?)', v.strip())
    return float(m.group(1).replace(',', '')) if m else None


def is_counting(q):
    return re.search(r'\b(how many|how much|number of|count|total)\b', str(q), re.I) is not None


def score(question, expected, answer):
    """Deterministic part of judgeScorer: returns True/False/None (needs judge)."""
    if answer is None or answer == '':
        return False
    if normalize(answer) == normalize(expected):
        return True
    if is_counting(question):
        p = leading_number(answer)
        e = leading_number(expected)
        if p is not None and e is not None:
            return p == e
    return None  # undecidable offline


def load_run(path):
    """Return {question_id: {capability, question, expected, answer, abstained}}."""
    out = {}
    for name, default_cap in (
        ('benchmark-single-session-diagnostics.json', None),
        ('benchmark-mr-diagnostics.json', 'MR'),
    ):
        f = path / name
        if not f.exists():
            continue
        for item in json.loads(f.read_text()):
            d = item['decision']
            out[item['question_id']] = {
                'capability': item.get('capability', default_cap or '?'),
                'question': item['question'],
                'expected': item.get('ground_truth'),
                'answer': d.get('answer'),
                'abstained': bool(d.get('abstained')),
                'llmRaw': d.get('llmRaw'),
            }
    return out


def binom_cdf(k, n, p=0.5):
    from math import comb
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * binom_cdf(min(b, c), n, 0.5))


B = {r: load_run(BASE / f'run_{r}') for r in BASE_RUNS}
P = {r: load_run(PJ / f'run_{r}') for r in PJ_RUNS}

ids = sorted(set.intersection(*[set(B[r]) for r in BASE_RUNS], *[set(P[r]) for r in PJ_RUNS]))
caps = {}
for r in BASE_RUNS:
    for i, v in B[r].items():
        caps[i] = v['capability']
print(f'paired questions: {len(ids)}  (capabilities: '
      + ', '.join(f'{c}={sum(1 for i in ids if caps[i] == c)}' for c in sorted({caps[i] for i in ids})) + ')')

# --- deterministic (judge-free) accuracy per run ----------------------------
print('\n== deterministic accuracy (exact-match + numeric only, no LLM judge) ==')
for label, R in (('baseline', B), ('p-json', P)):
    for r, data in R.items():
        ok = sum(1 for i in ids if score(data[i]['question'], data[i]['expected'], data[i]['answer']) is True)
        und = sum(1 for i in ids if score(data[i]['question'], data[i]['expected'], data[i]['answer']) is None)
        print(f'  {label:9s} {r}  correct={ok:3d}/{len(ids)} ({ok / len(ids) * 100:5.2f}%)  undecided={und}')

# --- paired McNemar over the 3x3 same-day grid ------------------------------
print('\n== paired McNemar (all 9 same-day baseline x p-json run pairs) ==')
print('  pair                b(base-only)  c(pjson-only)   p-value')
ps = []
for br in BASE_RUNS:
    for pr in PJ_RUNS:
        b = c = 0
        for i in ids:
            sb = score(B[br][i]['question'], B[br][i]['expected'], B[br][i]['answer'])
            sp = score(P[pr][i]['question'], P[pr][i]['expected'], P[pr][i]['answer'])
            if sb is True and sp is not True:
                b += 1
            elif sp is True and sb is not True:
                c += 1
        p = mcnemar(b, c)
        ps.append(p)
        print(f'  {br[-5:]} x {pr[-5:]}      {b:6d}        {c:6d}      {p:.4f}')
print(f'  median p = {st.median(ps):.4f}   max p = {max(ps):.4f}')

# --- per-capability discordance on the aligned run triples ------------------
print('\n== per-capability wins/losses (aligned run index 1:1, 2:2, 3:3) ==')
per_cap = {}
for k in range(3):
    br, pr = BASE_RUNS[k], PJ_RUNS[k]
    for i in ids:
        sb = score(B[br][i]['question'], B[br][i]['expected'], B[br][i]['answer'])
        sp = score(P[pr][i]['question'], P[pr][i]['expected'], P[pr][i]['answer'])
        cap = caps[i]
        d = per_cap.setdefault(cap, {'b': 0, 'c': 0})
        if sb is True and sp is not True:
            d['b'] += 1
        elif sp is True and sb is not True:
            d['c'] += 1
for cap, d in sorted(per_cap.items()):
    print(f'  {cap:4s} baseline-only correct={d["b"]:3d}  pjson-only correct={d["c"]:3d}  net={d["c"] - d["b"]:+d}'
          f'  mcnemar p={mcnemar(d["b"], d["c"]):.4f}')

# --- abstention behaviour ---------------------------------------------------
print('\n== abstention rate (paired subset) ==')
for label, R in (('baseline', B), ('p-json', P)):
    for r, data in R.items():
        a = sum(1 for i in ids if data[i]['abstained'])
        print(f'  {label:9s} {r}  abstained={a:3d}/{len(ids)} ({a / len(ids) * 100:5.2f}%)')

# --- answer-shape health check (CoN narration leakage) ----------------------
print('\n== answer-shape health (single-session + MR) ==')
for label, R in (('baseline', B), ('p-json', P)):
    long_ans = 0
    step_leak = 0
    for r, data in R.items():
        for i in ids:
            a = data[i]['answer']
            if not isinstance(a, str) or a == '':
                continue
            if len(a) > 120:
                long_ans += 1
            if re.search(r'(?i)\bstep\s*[12]\b', a):
                step_leak += 1
    print(f'  {label:9s} answers>120 chars={long_ans}  step-marker leakage={step_leak}  (across {len(ids)}x3 answers)')
