#!/usr/bin/env python3
"""TR date-anchored recall A/B: control (semantic/lexical) vs treatment
(date-proximity re-rank) on the TR mechanism endpoint, with per-capability
guards and exact permutation tests.
"""
import json
import glob
import os
import itertools

ROOT = '/workspace/analysis/ab_tr_date'
IDS_FILE = '/workspace/analysis/run-ids/ab_tr_date_run_ids.tsv'
CAPS = ['IE', 'MR', 'KU', 'TR', 'ABS']


def arm_of(run_id):
    ids = {}
    with open(IDS_FILE) as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            if p[0] == 'arm':
                continue
            ids[p[1]] = p[0]
    return ids.get(run_id, 'unknown')


def load_report(d):
    f = glob.glob(os.path.join(d, '*', 'benchmark-report.json'))
    return json.load(open(f[0])) if f else None


def main():
    per = {arm: {c: [] for c in CAPS} for arm in ['control', 'treatment']}
    overall = {arm: [] for arm in ['control', 'treatment']}
    for d in sorted(glob.glob(f'{ROOT}/run_*')):
        rid = os.path.basename(d).replace('run_', '')
        arm = arm_of(rid)
        if arm not in ('control', 'treatment'):
            continue
        rep = load_report(d)
        if not rep:
            continue
        feat = rep['feature']['metrics']
        overall[arm].append((feat.get('correct', 0), feat.get('total', 0)))
        pc = feat['perCapability']
        for c in CAPS:
            m = pc.get(c, {})
            per[arm][c].append((m.get('correct', 0), m.get('abstained', 0), m.get('total', 0)))

    for cap in CAPS:
        vals = {arm: per[arm][cap] for arm in ['control', 'treatment']}
        print(f'=== {cap} per run (correct/abstained/total) ===')
        for arm in ['control', 'treatment']:
            v = vals[arm]
            corr = [x[0] for x in v]
            abst = [x[1] for x in v]
            acc = 100 * sum(corr) / sum(x[2] for x in v) if v else 0
            print(f'  {arm:9}: correct {corr}  abst {abst}  acc {acc:.2f}%')
        print()

    print('=== OVERALL ===')
    for arm in ['control', 'treatment']:
        c = sum(v[0] for v in overall[arm])
        t = sum(v[1] for v in overall[arm])
        print(f'  {arm:9}: {c}/{t} = {100*c/t:.2f}%')

    print()
    for cap in ['TR', 'IE', 'MR', 'KU']:
        c = [v[0] for v in per['control'][cap]]
        t = [v[0] for v in per['treatment'][cap]]
        obs = sum(t) / 4 - sum(c) / 4
        pool = c + t
        cnt = 0
        for combo in itertools.combinations(range(8), 4):
            a = [pool[i] for i in combo]
            b = [pool[i] for i in range(8) if i not in combo]
            if (sum(b) - sum(a)) / 4 >= obs:
                cnt += 1
        sep = 'COMPLETE' if min(t) > max(c) else ('overlap+' if obs >= 0 else 'REGRESSION')
        print(f'{cap}: delta {obs:+.2f}/run; exact permutation (increase) {cnt}/70 = {cnt/70:.4f}; '
              f'control {c} vs treatment {t} -> {sep}')


if __name__ == '__main__':
    main()
