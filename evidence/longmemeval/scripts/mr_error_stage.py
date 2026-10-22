#!/usr/bin/env python3
"""Re-classify MR errors by WHERE in the pipeline they go wrong.

The critique pass audits LEDGER MEMBERSHIP. It is only the right fix for errors
whose ledger is wrong. Classifying errors by whether "bullets == gold" alone
mislabels abstentions and duplicate-driven over-counts, so this script reads the
first pass's own text to decide, per error, which stage actually failed:

  abstained        the model refused; the critique never runs (short-circuit)
  judge_sanctioned the gold names more than one acceptable value
  ledger_wrong     the enumerated set itself is wrong -> the critique's target
  over_count       duplicate events listed as distinct -> a dedup failure
  aggregation      the set is right, the arithmetic/selection from it is wrong

Reads frozen diagnostics only; no model is called.
"""
import json
import re
import sys

path = sys.argv[1]
records = json.load(open(path))

SAME_EVENT = re.compile(r'same (?:event|trip|person|item)', re.I)
DEDUP_NOTE = re.compile(r'count(?:ed)?\s+once|deduplicat', re.I)


def leading_number(value):
    m = re.search(r'-?[\d,]+(?:\.\d+)?', str(value).replace('$', ''))
    return m.group(0).replace(',', '') if m else None


def gold_as_int(gold):
    """Return the gold count as an int, or None when it is not a plain count."""
    if gold is None or gold == '':
        return None
    try:
        return int(float(gold))
    except ValueError:
        return None


def ledger_head(raw):
    return raw.split('Step 2')[0] if 'Step 2' in raw else raw


def bullets(raw):
    head = ledger_head(raw)
    n = len(re.findall(r'^\s*[-*]\s+\S', head, re.M))
    return n if n else len(re.findall(r'<item>', head))


buckets = {k: [] for k in
           ('abstained', 'judge_sanctioned', 'ledger_wrong', 'over_count', 'aggregation')}

for r in records:
    if r['correct']:
        continue
    dec = r['decision'] or {}
    raw = dec.get('llmRaw') or ''
    gold_raw = str(r['ground_truth'])
    gold = leading_number(gold_raw)
    pred = leading_number(dec.get('answer'))
    qid = r['question_id']

    if dec.get('abstained'):
        buckets['abstained'].append(qid)
        continue

    # Multiple numbers in the gold means either value is accepted.
    if len(re.findall(r'\d[\d,]*(?:\.\d+)?', gold_raw)) > 1 and pred:
        if pred in [n.replace(',', '') for n in re.findall(r'\d[\d,]*(?:\.\d+)?', gold_raw)]:
            buckets['judge_sanctioned'].append(qid)
            continue

    n_bullets = bullets(raw)
    gold_int = gold_as_int(gold)
    over = n_bullets > 0 and gold_int is not None and n_bullets > gold_int
    saw_dup = bool(SAME_EVENT.search(raw) or DEDUP_NOTE.search(raw))

    if over and saw_dup:
        # The list itself flagged repeats, so the failure is in what survived
        # the dedup/selection step, not in whether the item was noticed.
        buckets['over_count'].append(qid)
    elif n_bullets > 0 and gold_int is not None and n_bullets == gold_int:
        buckets['aggregation'].append(qid)
    else:
        buckets['ledger_wrong'].append(qid)

print('=== MR error taxonomy by pipeline stage ===')
total = sum(len(v) for v in buckets.values())
print(f'total errors: {total}\n')
for name, ids in buckets.items():
    print(f'{name:18s} {len(ids):3d}  {", ".join(ids)}')
print()
print('critique membership audit could plausibly address :', len(buckets['ledger_wrong']))
print('critique is the wrong instrument for             :', total - len(buckets['ledger_wrong']))
