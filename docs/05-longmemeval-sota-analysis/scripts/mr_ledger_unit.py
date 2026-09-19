#!/usr/bin/env python3
"""Classify the `ledger_wrong` MR errors by the mechanism that actually failed.

The previous iteration established that a membership audit cannot fix these, and
that "deduplicate more" is not a rule: `2788b940` needs entries KEPT distinct
while `a9f6b44c` needs them MERGED. This script tests whether a single principle
separates them, by reading the question's counting unit alongside the ledger.

For each case it reports:
  unit          what the question asks the count to be over (a class, a bike,
                an item, a dollar amount), inferred from the question's noun and
                verb, and whether the ledger entries are that unit or events
  predicted     the count implied by reading the ledger at the question's unit
  gold          the recorded gold, so agreement is checkable rather than assumed

Reads frozen diagnostics only; no model is called.
"""
import json
import re
import sys

path = sys.argv[1]
records = {r['question_id']: r for r in json.load(open(path))}

CASES = [
    '2788b940', '129d1232', '60472f9c', 'a9f6b44c', 'gpt4_ab202e7f',
    'gpt4_731e37d7', 'bf659f65', 'gpt4_372c3eed', '9ee3ecd6',
]

# The counting unit a question asks for, keyed on the noun in the question.
UNIT = [
    (re.compile(r'\bhow many bikes?\b', re.I), 'bike'),
    (re.compile(r'\bhow many (?:fitness )?classes?\b', re.I), 'class type'),
    (re.compile(r'\bhow many (?:music )?(?:albums?|EPs?)\b', re.I), 'album'),
    (re.compile(r'\bhow many kitchen items?\b', re.I), 'item'),
    (re.compile(r'\bhow many projects?\b', re.I), 'project'),
    (re.compile(r'\bhow (?:much|many) (?:money|points)\b', re.I), 'amount'),
    (re.compile(r'\bhow many years\b', re.I), 'duration'),
    (re.compile(r'\bhow many (?:days|times|hours)\b', re.I), 'event count'),
]


def unit_of(question):
    for pattern, label in UNIT:
        if pattern.search(question):
            return label
    return 'unknown'


def ledger_entries(raw):
    head = raw.split('Step 2')[0] if 'Step 2' in raw else raw
    lines = [l.strip() for l in head.splitlines() if re.match(r'^\s*[-*]\s+\S', l)]
    if not lines:
        lines = [f'<item>{x}</item>' for x in re.findall(r'<item>(.*?)</item>', head, re.S)]
    return lines


def entity(line):
    """The named thing an entry is about, with the event qualifier removed."""
    s = re.sub(r'^[-*]\s+', '', line)
    s = re.sub(r'^<item>|</item>$', '', s).strip()
    name = s.split('|')[0].strip()
    name = re.sub(r'\s*\(.*', '', name).strip().lower()
    return name


def number(value):
    m = re.search(r'\d[\d,]*(?:\.\d+)?', str(value).replace('$', ''))
    return m.group(0).replace(',', '') if m else None


print(f'{"id":14s} {"unit":10s} {"entries":>7s} {"distinct":>8s} {"pred":>7s} {"gold":>7s}  verdict')
print('-' * 96)

agree = 0
for qid in CASES:
    r = records[qid]
    raw = r['decision']['llmRaw']
    u = unit_of(r['question'])
    entries = ledger_entries(raw)
    distinct = len({entity(e) for e in entries if entity(e)})
    pred = r['decision']['answer']
    gold = r['ground_truth']
    # Does reading the ledger at "distinct entity" recover the gold?
    recovered = False
    gold_n = number(gold)
    if gold_n and u != 'amount':
        recovered = str(distinct) == str(gold_n)
    verdict = 'unit=entity recovers gold' if recovered else 'does NOT recover'
    if recovered:
        agree += 1
    print(f'{qid:14s} {u:10s} {len(entries):7d} {distinct:8d} '
          f'{str(pred)[:6]:>7s} {str(gold)[:6]:>7s}  {verdict}')

print()
print(f'reading the ledger at the question\'s entity unit recovers the gold in '
      f'{agree}/{len(CASES)} cases')
