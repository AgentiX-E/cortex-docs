#!/usr/bin/env python3
"""Model a deterministic Step 2 against the frozen gold set.

The `aggregation` errors share a shape: the first pass lists the right items and
then miscounts them. This script asks whether replacing the model's Step 2 with a
rule would help, and — more importantly — how many currently-CORRECT answers the
same rule would break. A fix that trades wrong for wrong is not a fix.

Two candidate rules are modelled, because they differ on the exchange case:

  raw_entry_count      count the ledger entries as written (no re-dedup)
  distinct_item_count  collapse entries naming the same product

The second is the intuitive implementation and the one that regresses 0a995998,
so both are reported side by side.

Reads frozen diagnostics only; no model is called.
"""
import json
import re
import sys

path = sys.argv[1]
records = json.load(open(path))

ENTRY = re.compile(r'^\s*[-*]\s+\S')
BULLET_ATOM = re.compile(r'^\s*[-*]\s+(.*)$', re.M)
# "<name> | <action> | <date>" is the ledger's own column format.
COLUMNS = re.compile(r'^\s*[-*]\s+(?P<name>[^|]+?)\s*\|\s*(?P<action>[^|]+?)\s*\|')


def leading_number(value):
    m = re.search(r'-?[\d,]+(?:\.\d+)?', str(value).replace('$', ''))
    return m.group(0).replace(',', '') if m else None


def gold_int(gold):
    if not gold:
        return None
    try:
        return int(float(gold))
    except ValueError:
        return None


def entries(raw):
    head = raw.split('Step 2')[0] if 'Step 2' in raw else raw
    found = []
    for line in head.splitlines():
        if ENTRY.match(line):
            found.append(line.strip())
    if not found:
        found = re.findall(r'<item>(.*?)</item>', head, re.S)
        found = [f'<item>{x}</item>' for x in found]
    return found


def raw_count(raw):
    return len(entries(raw))


def distinct_count(raw):
    """Collapse entries that name the same product, keyed on the name column."""
    names = set()
    simple = 0
    for line in entries(raw):
        m = COLUMNS.match(line)
        if m:
            names.add(m.group('name').strip().lower())
        else:
            simple += 1
    return len(names) + simple


fixes = {'raw': 0, 'distinct': 0}
breaks = {'raw': 0, 'distinct': 0}
detail = []

for r in records:
    dec = r['decision'] or {}
    raw = dec.get('llmRaw') or ''
    g = gold_int(leading_number(r['ground_truth']))
    if g is None or not raw:
        continue
    rc = raw_count(raw)
    dc = distinct_count(raw)
    # Only count questions whose answer is a count, i.e. gold is a bare integer.
    if not re.fullmatch(r'\s*\d+\s*', str(r['ground_truth'])):
        continue

    was_correct = r['correct']
    for label, val in (('raw', rc), ('distinct', dc)):
        if not was_correct and val == g:
            fixes[label] += 1
        if was_correct and val != g:
            breaks[label] += 1
    if not was_correct:
        detail.append((r['question_id'], g, rc, dc))

print('=== deterministic Step 2, modelled on count questions only ===')
print(f'{"rule":10s} {"errors fixed":>13s} {"correct broken":>15s}')
for label in ('raw', 'distinct'):
    print(f'{label:10s} {fixes[label]:>13d} {breaks[label]:>15d}')
print()
print('=== error cases: gold vs the two rules ===')
print(f'{"id":14s} {"gold":>5s} {"raw":>5s} {"distinct":>9s}')
for qid, g, rc, dc in detail:
    note = ''
    if dc != g and rc == g:
        note = '  <- distinct regresses, raw is right'
    print(f'{qid:14s} {g:>5d} {rc:>5d} {dc:>9d}{note}')
