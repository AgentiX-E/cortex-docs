#!/usr/bin/env python3
"""Break the MR counting errors into arithmetic errors (fixable deterministically)
versus enumeration errors (not fixable by arithmetic alone).

If the LLM lists the right items but sums them wrong, moving the sum into code
removes the error. If it omits or invents an item, no amount of deterministic
arithmetic helps. The split therefore bounds what a deterministic aggregation
step can win.
"""

import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

RUNS = ['33722572103', '33722575163', '33722578296']
ROOT = Path('/workspace/analysis/fix_8d87341')


def money(v):
    if isinstance(v, str):
        m = re.match(r'^\$?\s*(-?[\d,]+(?:\.\d+)?)', v.strip())
        return float(m.group(1).replace(',', '')) if m else None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


rows = []
for run in RUNS:
    for x in json.loads((ROOT / f'run_{run}' / 'benchmark-mr-diagnostics.json').read_text()):
        d = x['decision']
        rows.append({
            'q': x['question'],
            'gt': x.get('ground_truth'),
            'ans': d.get('answer'),
            'raw': d.get('llmRaw', '') or '',
            'abstained': bool(d.get('abstained')),
        })

# Only counting questions with numeric ground truth and a numeric prediction.
pairs = []
for r in rows:
    g, a = money(r['gt']), money(r['ans'])
    if g is not None and a is not None:
        pairs.append((r, g, a))

print(f'counting questions with numeric gt AND numeric prediction: {len(pairs)}')

exact = sum(1 for _, g, a in pairs if g == a)
print(f'  exact: {exact} ({exact/len(pairs)*100:.1f}%)')

off = [(r, g, a) for r, g, a in pairs if g != a]
print(f'  off by something: {len(off)} ({len(off)/len(pairs)*100:.1f}%)')

# Does the model's own enumeration (the bullet list in its narration) sum to its
# stated answer? If yes -> enumeration error. If no -> arithmetic error.
def bullets_total(raw):
    """Sum the money-looking or plain numbers on bullet lines."""
    vals = []
    for line in raw.splitlines():
        s = line.strip()
        if not re.match(r'^[-*•]', s):
            continue
        m = re.search(r'\$?\s*(-?[\d,]+(?:\.\d+)?)', s)
        if m:
            try:
                vals.append(float(m.group(1).replace(',', '')))
            except ValueError:
                pass
    return vals


arith = 0      # listed items sum to something other than the stated answer
enum = 0       # listed items sum to the stated answer -> the list itself is wrong
unknown = 0
for r, g, a in off:
    vals = bullets_total(r['raw'])
    if not vals:
        unknown += 1
        continue
    s = sum(vals)
    if abs(s - a) < 1e-6:
        enum += 1          # internally consistent: it enumerated wrong
    else:
        arith += 1         # its own list sums to a different number

print(f'\n  arithmetic error (own list sums to something else): {arith}  <- fixable in code')
print(f'  enumeration error (own list sums to its answer)   : {enum}  <- needs better recall/listing')
print(f'  no parseable bullet list                          : {unknown}')

n_off = max(1, len(off))
print(f'\n  share of counting errors that are arithmetic: {arith/n_off*100:.1f}%')

# Where the money/count is wrong, how large is the gap?
gaps = [abs(g - a) for _, g, a in off]
print(f'  median absolute gap: {st.median(gaps):.1f}   max: {max(gaps):.1f}')

print('\n== sample arithmetic errors (deterministic summing would fix) ==')
shown = 0
for r, g, a in off:
    vals = bullets_total(r['raw'])
    if vals and abs(sum(vals) - a) >= 1e-6 and shown < 6:
        print(f'  Q: {r["q"][:76]}')
        print(f'     gt={g}  predicted={a}  own-list-sum={sum(vals)}  items={vals}')
        shown += 1

print('\n== sample enumeration errors ==')
shown = 0
for r, g, a in off:
    vals = bullets_total(r['raw'])
    if vals and abs(sum(vals) - a) < 1e-6 and shown < 6:
        print(f'  Q: {r["q"][:76]}')
        print(f'     gt={g}  predicted={a}  own-list-sum={sum(vals)}  items={vals}')
        shown += 1
