#!/usr/bin/env python3
"""Root-cause analysis of the multi-session reasoning (MR) capability, the
weakest dimension at ~64-68%.

The question this answers: when an MR question is answered wrong, is the
evidence session retrieved at all, or is it retrieved and then miscounted?
Those two failures need opposite fixes — the first is a retrieval problem, the
second is an aggregation/arithmetic problem — so the split decides where the
next iteration's effort belongs.
"""

import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

RUNS = ['33722572103', '33722575163', '33722578296']
ROOT = Path('/workspace/analysis/fix_8d87341')


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


def score(question, expected, answer):
    if answer is None or answer == '':
        return False
    if normalize(answer) == normalize(expected):
        return True
    if re.search(r'\b(how many|how much|number of|count|total)\b', str(question), re.I):
        p, e = leading_number(answer), leading_number(expected)
        if p is not None and e is not None:
            return p == e
    return None


def fingerprint(text, n=60):
    """A short normalised signature used to test whether an evidence session's
    content survived retrieval."""
    return re.sub(r'\W+', '', str(text).lower())[:n]


totals = Counter()
rows = []
for run in RUNS:
    data = json.loads((ROOT / f'run_{run}' / 'benchmark-mr-diagnostics.json').read_text())
    for x in data:
        d = x['decision']
        retrieved = d.get('retrieved', '') or ''
        answer = d.get('answer')
        gt = x.get('ground_truth')
        abstained = bool(d.get('abstained'))

        # How many of the evidence sessions can be found in the retrieved text?
        found = 0
        for content in x.get('answer_sessions_content', []) or []:
            fp = fingerprint(content)
            if fp and fp in fingerprint(retrieved, len(fp) + 40 if False else 10 ** 6):
                found += 1
        n_evidence = len(x.get('answer_sessions_content', []) or [])
        recall = found / n_evidence if n_evidence else 0.0

        verdict = score(x['question'], gt, answer)
        rows.append({
            'qid': x['question_id'],
            'q': x['question'],
            'gt': gt,
            'ans': answer,
            'abstained': abstained,
            'recall': recall,
            'n_evidence': n_evidence,
            'verdict': verdict,
            'counting': bool(re.search(r'\b(how many|how much|number of|count|total)\b', x['question'], re.I)),
        })

n = len(rows)
print(f'MR questions analysed: {n} (3 runs pooled: {n//3} questions x 3)')

decided = [r for r in rows if r['verdict'] is not None]
undecided = [r for r in rows if r['verdict'] is None]
print(f'  deterministic verdict: {len(decided)}   needs judge: {len(undecided)}')

correct = [r for r in decided if r['verdict'] is True]
wrong = [r for r in decided if r['verdict'] is False]
print(f'  deterministically correct: {len(correct)}   wrong: {len(wrong)}')

print('\n== among deterministically WRONG answers: was the evidence retrieved? ==')
full = sum(1 for r in wrong if r['recall'] >= 0.999)
partial = sum(1 for r in wrong if 0 < r['recall'] < 0.999)
none_ = sum(1 for r in wrong if r['recall'] == 0)
print(f'  all evidence sessions retrieved : {full:3d}  ({full/max(1,len(wrong))*100:5.1f}%)  <- aggregation/arithmetic failure')
print(f'  partially retrieved             : {partial:3d}  ({partial/max(1,len(wrong))*100:5.1f}%)')
print(f'  no evidence retrieved           : {none_:3d}  ({none_/max(1,len(wrong))*100:5.1f}%)  <- retrieval failure')

print('\n== evidence recall distribution (all MR questions) ==')
print(f'  mean recall: {st.mean([r["recall"] for r in rows])*100:.1f}%')
for lo, hi, label in [(0.999, 1.1, 'full (100%)'), (0.5, 0.999, 'partial (50-99%)'),
                      (0.001, 0.5, 'low (1-49%)'), (-0.1, 0.001, 'zero')]:
    c = sum(1 for r in rows if lo <= r['recall'] < hi)
    print(f'  {label:20s} {c:4d}  ({c/n*100:5.1f}%)')

print('\n== how often the retrieved text contains ANY evidence, by verdict ==')
for label, group in (('correct', correct), ('wrong', wrong)):
    anyev = sum(1 for r in group if r['recall'] > 0)
    print(f'  {label:8s} n={len(group):3d}  has-evidence={anyev:3d} ({anyev/max(1,len(group))*100:5.1f}%)  '
          f'mean recall={st.mean([r["recall"] for r in group])*100:5.1f}%')

print('\n== counting vs non-counting ==')
for label, flag in (('counting', True), ('non-counting', False)):
    sub = [r for r in decided if r['counting'] is flag]
    ok = sum(1 for r in sub if r['verdict'] is True)
    print(f'  {label:13s} n={len(sub):3d}  correct={ok:3d}  ({ok/max(1,len(sub))*100:5.1f}%)')

print('\n== abstention among MR ==')
ab = sum(1 for r in rows if r['abstained'])
print(f'  abstained: {ab}/{n} ({ab/n*100:.1f}%)')

print('\n== sample wrong answers with FULL evidence retrieved (aggregation failures) ==')
shown = 0
for r in wrong:
    if r['recall'] >= 0.999 and shown < 8:
        print(f'  Q: {r["q"][:88]}')
        print(f'     gt={str(r["gt"])[:26]:28s} predicted={str(r["ans"])[:26]}')
        shown += 1
