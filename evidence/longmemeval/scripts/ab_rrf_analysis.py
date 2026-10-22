#!/usr/bin/env python3
"""RRF retrieval-fusion A/B: control (max-merge + lexical cascade) vs treatment
(RRF) on the MR/TR mechanism endpoints, with per-capability guards and exact
permutation tests. Overall accuracy is a noise-floored descriptive estimate only.
"""
import json
import glob
import os
import itertools

ROOT = '/workspace/analysis/ab_rrf_v2'
IDS_FILE = '/workspace/analysis/run-ids/ab_rrf_v2_run_ids.tsv'
CAPS = ['IE', 'MR', 'KU', 'TR', 'ABS']


def load(arm):
    per = {c: [] for c in CAPS}
    overall = []
    for d in sorted(glob.glob(f'{ROOT}/run_*')):
        # only the requested arm; run dirs are tagged via the id file below
        pass
    return per, overall


def arm_of(run_id):
    ids = {}
    with open(IDS_FILE) as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if parts[0] == 'arm':
                continue
            ids[parts[1]] = parts[0]
    return ids.get(run_id, 'unknown')


def main():
    per = {arm: {c: [] for c in CAPS} for arm in ['control', 'treatment']}
    overall = {arm: [] for arm in ['control', 'treatment']}
    for d in sorted(glob.glob(f'{ROOT}/run_*')):
        run_id = os.path.basename(d).replace('run_', '')
        arm = arm_of(run_id)
        if arm not in ('control', 'treatment'):
            continue
        report = glob.glob(os.path.join(d, '*', 'benchmark-report.json'))
        if not report:
            continue
        rep = json.load(open(report[0]))
        feat = rep['feature']['metrics']
        overall[arm].append((feat.get('correct', 0), feat.get('total', 0)))
        pc = feat['perCapability']
        for c in CAPS:
            m = pc.get(c, {})
            per[arm][c].append((m.get('correct', 0), m.get('abstained', 0), m.get('total', 0)))

    def summary(cap):
        print(f'=== {cap} per run (correct/abstained/total) ===')
        for arm in ['control', 'treatment']:
            vals = per[arm][cap]
            corr = [v[0] for v in vals]
            abst = [v[1] for v in vals]
            tot = vals[0][2] if vals else 0
            print(f'  {arm:9}: correct {corr}  abst {abst}  acc {100*sum(corr)/sum([v[2] for v in vals]):.2f}%')
        return vals

    for cap in CAPS:
        summary(cap)
        print()

    print('=== OVERALL ===')
    for arm in ['control', 'treatment']:
        c = sum(v[0] for v in overall[arm])
        t = sum(v[1] for v in overall[arm])
        print(f'  {arm:9}: {c}/{t} = {100*c/t:.2f}%')

    # Exact permutation tests (one-sided in the treatment direction) for MR and TR
    print()
    for cap in ['MR', 'TR']:
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
        sep = 'COMPLETE' if min(t) > max(c) else ('overlap' if obs >= 0 else 'REGRESSION')
        print(f'{cap}: delta {obs:+.2f}/run; exact permutation (increase) {cnt}/70 = {cnt/70:.4f}; '
              f'control {c} vs treatment {t} -> {sep}')


if __name__ == '__main__':
    main()
