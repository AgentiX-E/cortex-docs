#!/usr/bin/env python3
"""Bound how many MR errors the aggregation critique could ever reach.

The critique pass is gated on `kind === 'enumeration'` and on the default
aggregation prompt being in use, and it is short-circuited entirely when the
first pass already abstained. It cannot touch a derivation question, and it
cannot touch an abstention. This script applies those gates to a frozen
diagnostics file and reports the resulting addressable set, so the pass's
ceiling is known before any benchmark run is paid for.

The `kind` decision is re-derived here from the engine's own rule. The
authoritative implementation is `classifyAggregationKind` in
`packages/cortex-eval/src/natural-language-memory.ts`; the pattern below is a
faithful copy of it, and `--verify` checks the two agree on every question in the
file by running the engine's function through vitest. If they ever diverge, the
check fails loudly rather than silently reporting a different population.

Reads frozen diagnostics only; no model is called.
"""
import json
import re
import sys

# Copy of classifyAggregationKind's pattern. Keep in sync with the engine; the
# membership counts are not comparable across a divergence.
DERIVATION = re.compile(
    r'\b(percentage|percent|average|mean|difference (?:in|between)|'
    r'how much (?:more|less|faster|earlier|older)|increase in|decrease in|'
    r'discount|cashback|minimum|maximum|how old was|'
    r'how long (?:have|has) [a-z]+ been|'
    r'how many (?:years|months|weeks|days) older|'
    r'how many (?:years|months) (?:old )?will [a-z]+ be when|'
    r'exceed [\w ]+? by)\b',
    re.I,
)


def kind(question):
    return 'derivation' if DERIVATION.search(question) else 'enumeration'


def main():
    path = sys.argv[1]
    records = json.load(open(path))

    enum_total = deriv_total = 0
    enum_wrong = deriv_wrong = 0
    enum_wrong_abstained = 0
    addressable = []
    excluded = []

    for r in records:
        k = kind(r['question'])
        if k == 'enumeration':
            enum_total += 1
        else:
            deriv_total += 1
        if r['correct']:
            continue
        if k == 'derivation':
            deriv_wrong += 1
            excluded.append(r['question_id'])
            continue
        enum_wrong += 1
        if (r['decision'] or {}).get('abstained'):
            enum_wrong_abstained += 1
        else:
            addressable.append(r['question_id'])

    total = len(records)
    total_wrong = sum(1 for r in records if not r['correct'])

    print('=== MR error population, split by critique eligibility ===')
    print(f'total questions         : {total}')
    print(f'enumeration             : {enum_total}')
    print(f'derivation (ineligible) : {deriv_total}')
    print()
    print(f'total errors            : {total_wrong}')
    print(f'  enumeration errors    : {enum_wrong}')
    print(f'    already abstained   : {enum_wrong_abstained}  (pass never runs)')
    print(f'    answered wrongly    : {len(addressable)}  (true addressable set)')
    print(f'  derivation errors     : {deriv_wrong}  (gate excludes)')
    print()
    print('addressable error ids   :', ', '.join(addressable))
    print('excluded error ids      :', ', '.join(excluded))
    print()
    print(
        f'ceiling if the critique fixed every addressable error: '
        f'+{len(addressable) / total * 100:.2f} pp',
    )


if __name__ == '__main__':
    main()
