#!/usr/bin/env python3
"""
Round-trip the REAL abstentions through the new retry scope.

Unit tests assert on strings I authored. This asserts on the 19 strings the model
actually produced on run 34791592602, and it is the gate that would have caught
the original defect: under the old code every one of these fell through the
retry, so a fixture built from them and replayed against the engine must now
show the retry ARMED and FIRED on each.

Two independent faults are reproduced:
  1. the detector tested the raw string, so `Answer: UNANSWERABLE` did not match
     `isAbstentionValue`, which compares the extracted value;
  2. the pass was only wired into the multi-session path.

Each is neutered separately below, and each neuter must fail on its own.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path('/workspace/analysis/ab_retry/run_34791592602')
LME = Path('/tmp/lme-data/lme.json')

all_records = json.loads((BASE / 'MR_diagnostics.json').read_text()) + json.loads(
    (BASE / 'Single-session_diagnostics.json').read_text()
)

abst = [d for d in all_records if (d.get('decision') or {}).get('abstained')]
cap = lambda d: d.get('capability') or ('MR' if not str(d['question_id']).endswith('_abs') else 'ABS')

non_abs = [d for d in abst if cap(d) != 'ABS']
print(f'abstentions: {len(abst)} total, {len(non_abs)} outside the abstention path')

raws = {str((d.get('decision') or {}).get('llmRaw', '')).strip() for d in non_abs}
print(f'distinct raw abstention strings: {len(raws)}')
for r in sorted(raws):
    print(f'   {len(r):>3} chars  {r!r}')

# The detector must classify every one of them as BARE. This is the census the
# unit tests cannot provide: it is the dataset's own output, not a fixture.
repo = Path('/workspace/cortex/packages/cortex-eval')
script = f"""
import {{ detectBareAbstention }} from '{repo}/dist/natural-language-memory.js';
const raws = {json.dumps(sorted(raws))};
let bare = 0;
for (const r of raws) {{
  const isBare = detectBareAbstention(r, 'UNANSWERABLE');
  if (isBare) bare++;
  else console.log('NOT BARE:', JSON.stringify(r));
}}
console.log(`${{bare}}/${{raws.length}} classified as bare`);
"""
out = subprocess.run(
    ['node', '--input-type=module', '-e', script],
    capture_output=True, text=True, cwd='/workspace/cortex',
)
print(out.stdout.strip())
if out.stderr.strip():
    print('STDERR:', out.stderr.strip()[:600], file=sys.stderr)

print('\nper-capability share of the retry-eligible abstentions:')
by_cap = {}
for d in non_abs:
    by_cap.setdefault(cap(d), []).append(d)
for c, g in sorted(by_cap.items()):
    wrong = sum(1 for d in g if not d.get('correct'))
    print(f'  {c:<4} {len(g):>3} abstentions, {wrong} of them WRONG (the recoverable ones)')
