#!/usr/bin/env python3
"""Taxonomy of MR counting errors, corrected.

Two failure modes need separating because they have different fixes:

  * COUNT questions ("how many items/times/people") are answered by the NUMBER
    OF BULLET LINES the model lists.
  * SUM questions ("how much money", "how many hours/days in total") are answered
    by ADDING the numeric value on each bullet line.

An earlier pass conflated them and treated the year in a date (`2023/05/12`) as
a summable value, which inflated the arithmetic bucket. This version strips
dates first and classifies each question before scoring.
"""

import json
import re
import statistics as st
from pathlib import Path

RUNS = ['33722572103', '33722575163', '33722578296']
ROOT = Path('/workspace/analysis/fix_8d87341')

DATE_RE = re.compile(r'\d{4}/\d{1,2}/\d{1,2}')
YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')

SUM_CUES = re.compile(r'\b(how much|how many (?:hours|days|minutes|dollars|money)|total (?:money|amount|cost|hours|days|time))\b', re.I)


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = re.match(r'^\$?\s*(-?[\d,]+(?:\.\d+)?)', v.strip())
    return float(m.group(1).replace(',', '')) if m else None


def bullets(raw):
    """Return the bullet lines of a narration, dates stripped."""
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not re.match(r'^[-*•]\s', s):
            continue
        cleaned = YEAR_RE.sub(' ', DATE_RE.sub(' ', s))
        m = re.search(r'\$?\s*(-?[\d,]+(?:\.\d+)?)', cleaned)
        val = None
        if m and m.group(1).strip():
            try:
                val = float(m.group(1).replace(',', ''))
            except ValueError:
                val = None
        out.append((cleaned.strip(), val))
    return out


rows = []
for run in RUNS:
    for x in json.loads((ROOT / f'run_{run}' / 'benchmark-mr-diagnostics.json').read_text()):
        d = x['decision']
        rows.append({'q': x['question'], 'gt': x.get('ground_truth'),
                     'ans': d.get('answer'), 'raw': d.get('llmRaw', '') or ''})

buckets = {'sum': [], 'count': []}
for r in rows:
    g, a = num(r['gt']), num(r['ans'])
    if g is None or a is None:
        continue
    bl = bullets(r['raw'])
    kind = 'sum' if SUM_CUES.search(r['q']) else 'count'
    buckets[kind].append((r, g, a, bl))

total_fixable = 0
for kind in ('count', 'sum'):
    items = buckets[kind]
    exact = sum(1 for _, g, a, _ in items if abs(g - a) < 1e-6)
    off = [(r, g, a, bl) for r, g, a, bl in items if abs(g - a) >= 1e-6]
    print(f'\n== {kind.upper()} questions: n={len(items)}  exact={exact} ({exact/max(1,len(items))*100:.1f}%)  wrong={len(off)} ==')

    arith = enum = unparseable = 0
    for r, g, a, bl in off:
        if not bl:
            unparseable += 1
            continue
        if kind == 'count':
            derived = len(bl)
        else:
            vals = [v for _, v in bl if v is not None]
            derived = sum(vals) if vals else None
        if derived is None:
            unparseable += 1
        elif abs(derived - a) < 1e-6:
            enum += 1
        else:
            arith += 1
    n_off = max(1, len(off))
    print(f'  arithmetic error (own list contradicts its answer): {arith:3d}  ({arith/n_off*100:5.1f}% of errors)  <- deterministic aggregation fixes these')
    print(f'  enumeration error (own list agrees, list is wrong) : {enum:3d}  ({enum/n_off*100:5.1f}%)')
    print(f'  no parseable bullet list                           : {unparseable:3d}  ({unparseable/n_off*100:5.1f}%)')
    total_fixable += arith

all_items = len(buckets['count']) + len(buckets['sum'])
print(f'\n== upper bound for deterministic aggregation ==')
print(f'  errors where the model\'s own list sums/counts to something other than its')
print(f'  stated answer: {total_fixable} pooled over 3 runs = {total_fixable / 3:.1f} per run')
print(f'  = {total_fixable / all_items * 100:.1f}pp of the scored MR questions'
      f'  = {total_fixable / 3 / 500 * 100:.1f}pp of the 500-question benchmark (upper bound)')
print('  Caveat: fixing the arithmetic makes the answer equal the model\'s list, which is')
print('  only correct when the list itself is right. The enumeration errors above are the')
print('  residue that no amount of deterministic arithmetic can recover.')
