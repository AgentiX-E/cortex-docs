#!/usr/bin/env python3
"""S9: the product's own index against the harness's, paired by question.

Two artifacts of the `cortex-memory` arm, one dispatch per ranking signal, everything else held at
the same 22 inputs except the two departures both sides carry (`limit=200`, `ablation_runs=2`).
The reading is the paired difference in correct answers, plus the two cost counters the treatment
side publishes in `memoryArmConfig.selfIndex`.

Why this is a script and not a paragraph: the number feeds `S9` in the acceptance matrix, and a
number that a reader has to reconstruct from two 20 MB artifacts is a number nobody re-checks. It
prints every reading it computes, refuses to pair artifacts that are not about the same instrument,
and writes the evidence JSON the matrix reads.

Usage:
  python3 self_index_analysis.py control.json treatment.json [--write ../self-index.json]
"""
from __future__ import annotations

import json
import sys
from math import comb
from typing import Any


def load(path: str) -> dict[str, Any]:
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar, which is the binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    # Sum the tails at or below the observed split; the min(b, c) bound keeps it symmetric.
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def per_question(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row['questionId']: row for row in report['questions']}


def verdicts(report: dict[str, Any]) -> dict[str, bool]:
    """First-repetition verdict per question, which is what the arm's own tables pair on."""
    return {row['questionId']: bool(row['correct']) for row in report['questions']}


def per_question_means(report: dict[str, Any]) -> dict[str, float]:
    """Each question's mean correct over the repetitions.

    `ablation.featureCorrectByRun` is one `0`/`1` bitstring per repetition, aligned with the
    question order (the same alignment `featureAnswers` uses), so the per-question mean is exact
    rather than reconstructed from an aggregate. Falling back to the first-repetition vector would
    turn a two-repetition mean into a one-repetition verdict and quietly halve the instrument.
    """
    runs = report['ablation']['featureCorrectByRun']
    ids = [row['questionId'] for row in report['questions']]
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], str):
        return {qid: float(hit) for qid, hit in verdicts(report).items()}
    for index, bits in enumerate(runs):
        if len(bits) != len(ids):
            raise SystemExit(
                f'refusing: run {index} carries {len(bits)} verdicts for {len(ids)} questions, so the '
                'bitstring is not aligned with the roster and a per-question mean would be a guess'
            )
    return {
        qid: sum(1 for bits in runs if bits[position] == '1') / len(runs)
        for position, qid in enumerate(ids)
    }


def verdict(delta_questions: float, cost: dict[str, Any], n: int, tier: str) -> dict[str, Any]:
    """The pre-committed decision rule of `docs/MEASURE-SELF-INDEX.md` section 4, applied in code.

    Two conditions, both written before the run: the paired delta at or above the -15 the matrix
    registers, and a cost of at most one embedded text per corpus turn per question. The second is
    the one that stops a tie from being called a win -- a ranking that doubles the embedding bill to
    tie is not an improvement, it is the same answer for more money.
    """
    threshold = -15.0
    turns = cost['turns'] / cost['indexes']
    texts = cost['embedTexts'] / cost['indexes']
    cost_met = texts <= turns
    within = delta_questions >= threshold
    decided = within and cost_met
    return {
        'thresholdQuestions': threshold,
        'deltaQuestions': round(delta_questions, 4),
        'withinThreshold': within,
        'costCondition': {
            'textsPerIndex': round(texts, 2),
            'turnsPerIndex': round(turns, 2),
            'limit': 'at most one text per corpus turn per question',
            'met': cost_met,
        },
        'ruleSatisfied': decided,
        # Adoption is a registration change, and a screening pair is not the instrument the rule was
        # written against. `decided` says the mechanism cleared the bar it was given; `adopted` stays
        # false until the registered pair runs, because flipping the arm's default on a 200 x 2 screen
        # would be reading a 7.5-point band as if it were a 3-point one.
        'adopted': False,
        'adoptionBlocker': (
            f'measured on {n} questions x 2 repetitions; S9 is registered on 500 x 4, where -15 '
            'questions is -3.0 points rather than -7.5'
            if tier == 'screening'
            else 'none: this is the registered instrument'
        ),
    }

def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    control = load(argv[1])
    treatment = load(argv[2])
    write_to = None
    if '--write' in argv:
        write_to = argv[argv.index('--write') + 1]
    # `S9` is registered on 500 questions and four repetitions. A 200 x 2 pair answers "are the two
    # sides in the same neighbourhood", not the registered question, so its delta is written under
    # `screening` and the matrix's key (`paired.deltaQuestions`) stays absent -- a row that appears
    # to pass on a weaker instrument is the one class of number a later re-reading cannot repair.
    tier = 'registered'
    if '--tier' in argv:
        tier = argv[argv.index('--tier') + 1]
        if tier not in ('screening', 'registered'):
            raise SystemExit(f'refusing: --tier {tier!r} is neither screening nor registered')

    # ---- the three readability checks, done rather than assumed ------------------------------
    checks: list[tuple[str, bool, str]] = []

    same_corpus = control['datasetFingerprint'] == treatment['datasetFingerprint']
    checks.append(('corpus', same_corpus, control['datasetFingerprint']))

    reader_c = control['memoryArmConfig']['reader']
    reader_t = treatment['memoryArmConfig']['reader']
    judge_c = control['memoryArmConfig']['judge']
    judge_t = treatment['memoryArmConfig']['judge']
    checks.append(('reader', reader_c == reader_t, f"{reader_c['model']} thinking={reader_c['thinking']}"))
    checks.append(('judge', judge_c == judge_t, f"{judge_c['model']}"))

    # The prompt outside the ranking: the same evidence set must produce the same digest, and a
    # different one must be attributable to the ranking rather than to the renderer.
    cq, tq = per_question(control), per_question(treatment)
    if set(cq) != set(tq):
        checks.append(('question set', False, f'{len(cq)} vs {len(tq)} ids'))
    else:
        checks.append(('question set', True, f'{len(cq)} ids'))

    # The treatment is exactly three fields: which signal ranked the turns, the parameters that
    # signal carries (`anchorParams` exists only when a harness index was built), and the census the
    # product publishes about its own. Everything else has to match or the delta is two variables.
    treatment_fields = {'relevanceSignal', 'anchorParams', 'selfIndex'}
    config_delta = []
    moved_with_treatment = []
    for key, value in treatment['memoryArmConfig'].items():
        if key in treatment_fields:
            continue
        if control['memoryArmConfig'].get(key) != value:
            config_delta.append(key)
    for key in treatment_fields - {'selfIndex'}:
        if control['memoryArmConfig'].get(key) != treatment['memoryArmConfig'].get(key):
            moved_with_treatment.append(key)
    checks.append(
        (
            'config apart from the signal',
            not config_delta,
            ','.join(config_delta) or f'none (the treatment moves {",".join(sorted(moved_with_treatment))})',
        )
    )

    for name, ok, detail in checks:
        print(f'check  {name:28s} {"ok" if ok else "MISMATCH"}  {detail}')
    if not all(ok for _, ok, _ in checks):
        print('refusing: the two artifacts are not one instrument, so a delta is not attributable')
        return 1

    # ---- the paired accuracy reading ---------------------------------------------------------
    ids = sorted(cq)
    b = c = 0
    for qid in ids:
        hit_c = bool(cq[qid]['correct'])
        hit_t = bool(tq[qid]['correct'])
        if hit_c and not hit_t:
            b += 1
        elif hit_t and not hit_c:
            c += 1
    p = mcnemar(b, c)

    # The all-runs figure, per question rather than from the aggregate: the two must agree, and the
    # agreement is asserted below because an aggregate that disagreed with its own roster is the
    # defect that makes a published accuracy unreadable.
    mean_c = per_question_means(control)
    mean_t = per_question_means(treatment)
    n = len(ids)
    ctrl_mean = control['ablation']['featureAggregate']['avg']
    treat_mean = treatment['ablation']['featureAggregate']['avg']
    delta_questions = sum(mean_t[qid] - mean_c[qid] for qid in ids)
    delta_first = sum(int(tq[q]['correct']) - int(cq[q]['correct']) for q in ids)

    for label, means, aggregate in (
        ('control', mean_c, ctrl_mean),
        ('treatment', mean_t, treat_mean),
    ):
        recomputed = sum(means.values()) / n
        if abs(recomputed - aggregate) > 1e-9:
            raise SystemExit(
                f'refusing: {label} recomputes to {recomputed:.6f} from the per-run bitstrings but '
                f'the aggregate says {aggregate:.6f}; one of the two is wrong and a delta built on '
                'either would be a number nobody could reconcile'
            )

    by_capability: dict[str, dict[str, Any]] = {}
    for qid in ids:
        cap = tq[qid]['capability']
        row = by_capability.setdefault(
            cap, {'total': 0, 'controlMean': 0.0, 'treatmentMean': 0.0, 'b': 0, 'c': 0}
        )
        row['total'] += 1
        row['controlMean'] += mean_c[qid]
        row['treatmentMean'] += mean_t[qid]
        hit_c = bool(cq[qid]['correct'])
        hit_t = bool(tq[qid]['correct'])
        row['b'] += int(hit_c and not hit_t)
        row['c'] += int(hit_t and not hit_c)
    for row in by_capability.values():
        row['deltaQuestions'] = round(row['treatmentMean'] - row['controlMean'], 4)
        row['controlMean'] = round(row['controlMean'], 4)
        row['treatmentMean'] = round(row['treatmentMean'], 4)
        row['mcnemarP'] = mcnemar(row['b'], row['c'])

    # ---- the two cost readings ---------------------------------------------------------------
    cost = treatment['memoryArmConfig']['selfIndex']
    corpus_turns = cost['turns'] / cost['indexes']
    texts_per_index = cost['embedTexts'] / cost['indexes']
    hits_per_index = cost['memoHits'] / cost['indexes']
    per_question_texts = cost['embedTexts'] / n
    per_question_turns = cost['turns'] / n

    print()
    print(f'control   {control["ablation"]["featureAggregate"]["avg"]:.4f} mean correct '
          f'({control["ablation"]["featureAggregate"]["avg"] * n:.2f} of {n})')
    print(f'treatment {treat_mean:.4f} mean correct ({treat_mean * n:.2f} of {n})')
    print(f'paired delta (all-runs means, in questions): {delta_questions:+.2f}')
    print(f'paired delta (first repetition, in questions): {delta_first:+d}')
    print(f'discordant: control✓treat✗ {b}, control✗treat✓ {c}, McNemar p {p:.4g}')
    print()
    print(f'selfIndex indexes {cost["indexes"]}, turns {cost["turns"]}, texts {cost["embedTexts"]}, '
          f'hits {cost["memoHits"]}, reuse {cost["reuse"]}, rerank {cost["rerankCalls"]}/'
          f'{cost["rerankDegraded"]}')
    print(f'per index: turns {corpus_turns:.2f}, texts {texts_per_index:.2f}, hits {hits_per_index:.2f}, '
          f'calls {cost["embedCalls"] / cost["indexes"]:.2f}')
    print(f'per question: turns {per_question_turns:.1f}, texts {per_question_texts:.1f}')
    print(f'texts/attempts {cost["embedTexts"] / (cost["embedTexts"] + cost["memoHits"]):.4f}')

    payload = {
        '$comment': (
            'S9. The product builds the index for each question (treatment) against the harness '
            'building it before the run (control), same 22 inputs apart from the signal and the two '
            'departures both sides carry (limit=200, ablation_runs=2). Paired by question id, '
            'per-question mean over the repetitions. Written under `screening` because the '
            'registered instrument is 500 questions x 4 repetitions and this is not it.'
            if tier == 'screening'
            else 'S9 on the registered instrument: 500 questions, four repetitions, paired by question id.'
        ),
        'arm': 'cortex-memory',
        'dataset': {
            'name': control['dataset'],
            'fingerprint': control['datasetFingerprint'],
            'questions': n,
            'repetitions': control['runs'],
        },
        'runs': {
            'control': control.get('generatedAt'),
            'treatment': treatment.get('generatedAt'),
        },
        'configDelta': config_delta,
        'selfIndex': cost,
        'cost': {
            'corpusTurnsPerIndex': round(corpus_turns, 2),
            'textsPerIndex': round(texts_per_index, 2),
            'memoHitsPerIndex': round(hits_per_index, 2),
            'textsPerQuestion': round(per_question_texts, 1),
            'turnsPerQuestion': round(per_question_turns, 1),
            'textsPerAttempt': round(cost['embedTexts'] / (cost['embedTexts'] + cost['memoHits']), 4),
        },
        tier: {
            'control': {
                'run': control.get('generatedAt'),
                'relevanceSignal': control['memoryArmConfig']['relevanceSignal'],
                'meanCorrect': ctrl_mean,
            },
            'treatment': {
                'run': treatment.get('generatedAt'),
                'relevanceSignal': treatment['memoryArmConfig']['relevanceSignal'],
                'meanCorrect': treat_mean,
            },
            'deltaQuestions': round(delta_questions, 4),
            'deltaQuestionsFirstRepetition': delta_first,
            'discordant': {'controlCorrectTreatmentWrong': b, 'treatmentCorrectControlWrong': c},
            'mcnemarP': p,
            'byCapability': by_capability,
            'instrument': f'per-question mean over {control["runs"]} repetitions, paired by question id',
            'verdict': verdict(delta_questions, cost, n, tier),
        },
    }
    if write_to is not None:
        with open(write_to, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2)
            handle.write('\n')
        print(f'wrote {write_to}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
