#!/usr/bin/env python3
"""Separate deterministic MR failures from run-to-run noise.

A single benchmark run reports ~23 MR errors, but the endpoint is not
reproducible across calls even at temperature=0, so most of that list is flake.
Fixing a flaky question is unverifiable and is not a capability gain. This script
replays every recorded run, counts how often each question actually fails, and
prints the deterministic set — which is the only set a fix can be validated
against.

Usage:
  mr_stability.py <dir containing run_*/longmemeval-s-report/benchmark-mr-diagnostics.json>

Reads frozen diagnostics only; no model is called.
"""
import glob
import json
import os
import sys
from collections import defaultdict

root = sys.argv[1] if len(sys.argv) > 1 else '.'
paths = sorted(glob.glob(os.path.join(root, 'run_*/longmemeval-s-report/benchmark-mr-diagnostics.json')))
if not paths:
    sys.exit(f'no diagnostics files found under {root}')

runs = []
for p in paths:
    records = json.load(open(p))
    runs.append((os.path.basename(os.path.dirname(os.path.dirname(p))), records))

n_runs = len(runs)
fail = defaultdict(int)
question_order = []
for _, records in runs:
    for r in records:
        if r['question_id'] not in question_order:
            question_order.append(r['question_id'])
        if not r['correct']:
            fail[r['question_id']] += 1

total = len(question_order)
always = sorted(q for q in question_order if fail[q] == n_runs)
sometimes = sorted(q for q in question_order if 0 < fail[q] < n_runs)
never = [q for q in question_order if fail[q] == 0]

print(f'runs replayed : {n_runs}')
print(f'MR questions  : {total}')
print()
print(f'  always wrong (deterministic) : {len(always):3d}  {len(always) / total * 100:5.1f}%')
print(f'  sometimes wrong (flaky)      : {len(sometimes):3d}  {len(sometimes) / total * 100:5.1f}%')
print(f'  never wrong                  : {len(never):3d}  {len(never) / total * 100:5.1f}%')
print()

print('=== per-run accuracy (identical configuration) ===')
accs = []
for name, records in runs:
    correct = sum(1 for r in records if r['correct'])
    acc = correct / len(records) * 100
    accs.append(acc)
    print(f'  {name}: {correct}/{len(records)} = {acc:.2f}%')
print(f'  spread: {max(accs) - min(accs):.2f} pp')
print()

print('=== error-count inflation from flake ===')
mean_errors = sum(len([r for r in recs if not r['correct']]) for _, recs in runs) / n_runs
print(f'  mean errors per run      : {mean_errors:.1f}')
print(f'  deterministic failures   : {len(always)}')
print(f'  apparent/real ratio      : {mean_errors / len(always):.2f}x')
print()

print('=== deterministic failure ids (the valid target set) ===')
for q in always:
    print(f'  {q}')
print()
print(f'ceiling if all deterministic failures were fixed: '
      f'{(total - len(always)) / total * 100:.2f}% (floor, before flake luck)')
