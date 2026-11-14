#!/usr/bin/env python3
"""E6: the semantic layer's carry, read off one artifact rather than two.

## What this script is for

The artifact `semantic-carry.yml` writes is a **paired** pass: `CORTEX_MEMORY_AB=carry` puts the
same cognitive system on both sides with `semanticCarry` off on the baseline and on on the feature,
so `ablation.baselineCorrectByRun` and `ablation.featureCorrectByRun` are two verdict vectors over
one population. The two numbers `S12` and `S13` read are therefore both in this one file --
`deltaQuestions` over the second windows, and `semanticCarry.matched` for the reach -- and neither is
reconstructible from the Markdown a human opens.

## Why the delta is taken over the second windows only

The population asks each corpus twice (`CORTEX_WINDOWS=2`). The first window is the one that
**absorbs** an update; the second is the one a carry can reach, and it is the only window whose
answer the treatment can move. Averaging the two halves would divide a mechanism reading by two
windows that cannot carry the treatment at all, and `S12` is registered over 500 questions -- which
is exactly the count of second windows. So `paired.deltaQuestions` is over `#w2`, and the same
number over every window is published beside it as `paired.deltaQuestionsAllWindows` rather than
instead of it.

## Why the reach is read, not derived

`semanticCarry` is the product's own census (`CortexMemory.semanticCarryCensus()`), folded over every
worker instance the run answered through. `matched` is the number of **prompts** whose window still
carried a record an absorbed update was authorised by. It cannot be derived from `deltaQuestions`:
`0` satisfies `>= -5`, and `0` is also what a mechanism that reached nothing produces. That is why
`S12.requires = ['S13']` and why a run without this number is `void` rather than `pass`.

## The tiers, and the one thing that stops a screening run from filling a registered row

`S12` is registered on 500 corpora x 4 repetitions. A 78-corpus x 2-repetition dispatch answers "can
the mechanism reach a window at all", which is a different question, and its delta is written under
`screening` -- leaving `paired.deltaQuestions` absent, so a row that reads that key stays `unrun`
rather than appearing to pass on a weaker instrument. This is the rule
`self_index_analysis.py` established for `S9`, applied to the row where it matters most: a
`void`-to-`pass` transition on a screening pair would be a claim about a population nobody ran.

Usage:
  python3 semantic_carry_analysis.py report.json [--write ../semantic-carry.json] [--tier screening]
"""
from __future__ import annotations

import json
import sys
from math import comb
from typing import Any

# The two thresholds the rows carry, written here so the script's verdict cannot drift from the
# matrix without one of them being edited in the open.
DELTA_FLOOR = -5
REACH_FLOOR = 1


def load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar: the binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def per_question_means(report: dict[str, Any], side: str) -> dict[str, float]:
    """Each question's mean correct over the repetitions, keyed by the id the roster carries.

    `ablation.{side}CorrectByRun` is one `0`/`1` bitstring per repetition, aligned with the question
    order -- the same alignment `featureAnswers` uses. The length is checked rather than trusted: a
    bitstring that is not aligned with the roster would make every per-question mean a guess that
    looks like a number.
    """
    rows = report["questions"]
    ids = [row["questionId"] for row in rows]
    runs = report["ablation"][f"{side}CorrectByRun"]
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], str):
        raise SystemExit(
            f"refusing: the artifact carries no `{side}CorrectByRun` bitstrings, so the pairing "
            "cannot be recomputed and a verdict from `questions[].correct` would be a "
            "one-repetition reading of a multi-repetition run"
        )
    for index, bits in enumerate(runs):
        if len(bits) != len(ids):
            raise SystemExit(
                f"refusing: run {index} carries {len(bits)} verdicts for {len(ids)} questions, so "
                "the bitstring is not aligned with the roster"
            )
    return {
        qid: sum(1 for bits in runs if bits[position] == "1") / len(runs)
        for position, qid in enumerate(ids)
    }


def first_repetition(report: dict[str, Any], side: str) -> dict[str, bool]:
    """The first repetition's verdict per question, which is what the arm's own tables pair on."""
    runs = report["ablation"][f"{side}CorrectByRun"]
    ids = [row["questionId"] for row in report["questions"]]
    return {qid: runs[0][position] == "1" for position, qid in enumerate(ids)}


def window_of(question_id: str, marker: str) -> int | None:
    """The window a question id names, or `None` when it names none.

    `None` rather than `1` on a missing marker: a population without windows is a different
    population, and reading its ids as first windows would let a one-window dispatch publish a
    second-window delta of zero over an empty selection.
    """
    at = question_id.rfind(marker)
    if at < 0:
        return None
    digits = question_id[at + len(marker) :]
    return int(digits) if digits.isdigit() else None


def paired(readings: dict[str, float], control: dict[str, float], keep: set[str]) -> dict[str, Any]:
    """The paired difference over `keep`, in questions, plus its discordant counts."""
    ids = sorted(keep)
    b = sum(1 for qid in ids if control[qid] > readings[qid])
    c = sum(1 for qid in ids if readings[qid] > control[qid])
    return {
        "n": len(ids),
        "deltaQuestions": round(sum(readings[qid] - control[qid] for qid in ids), 4),
        "discordant": {"baselineOnly": b, "featureOnly": c},
    }


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        return 2
    report = load(argv[0])
    write_to = None
    if "--write" in argv:
        write_to = argv[argv.index("--write") + 1]
    source_run = None
    if "--run" in argv:
        source_run = argv[argv.index("--run") + 1]
    tier = "registered"
    if "--tier" in argv:
        tier = argv[argv.index("--tier") + 1]
        if tier not in ("screening", "registered"):
            raise SystemExit(f"refusing: --tier {tier!r} is neither screening nor registered")

    population = report.get("population")
    if population is None:
        raise SystemExit(
            "refusing: the artifact carries no `population`, so it graded one window per corpus and "
            "the reach is zero by construction (AUDIT-SEMANTIC-REACH.md 15.2). Dispatch with "
            "CORTEX_WINDOWS=2 rather than reading this file"
        )
    marker = population["marker"]
    windows = population["windows"]

    carry = report.get("semanticCarry")
    config = report.get("memoryArmConfig", {})
    print(f"population: {population['corpora']} corpora x {windows} windows, ids carry {marker!r}")
    print(f"reviewPass: {config.get('reviewPass')}  semanticCarry: {config.get('semanticCarry')}")
    print(f"reader: {config.get('reader', {}).get('model')}  judge: {config.get('judge', {}).get('model')}")
    print(f"carry census: {carry}")

    feature = per_question_means(report, "feature")
    control = per_question_means(report, "baseline")
    every = set(feature)
    second = {qid for qid in every if window_of(qid, marker) == windows}
    first = {qid for qid in every if window_of(qid, marker) == 1}
    if not second:
        raise SystemExit(
            f"refusing: no id ends in {marker}{windows}, so the population has no second window to "
            "read. The delta would be over an empty selection and would read as 0"
        )

    overall = paired(feature, control, every)
    second_window = paired(feature, control, second)
    first_window = paired(feature, control, first)
    print(f"all windows:   {overall}")
    print(f"first window:  {first_window}")
    print(f"second window: {second_window}")

    b = first_repetition(report, "baseline")
    f = first_repetition(report, "feature")
    regressions = sorted(qid for qid in second if b[qid] and not f[qid])
    gains = sorted(qid for qid in second if f[qid] and not b[qid])
    p = mcnemar(len(regressions), len(gains))
    print(f"mcnemar on the second window (first repetition): b={len(regressions)} c={len(gains)} p={p:.4f}")
    if gains:
        print(f"  gained: {', '.join(gains)}")
    if regressions:
        print(f"  lost:   {', '.join(regressions)}")

    reach = None if carry is None else carry["matched"]
    verdict = {
        "reached": None if reach is None else reach >= REACH_FLOOR,
        "withinThreshold": second_window["deltaQuestions"] >= DELTA_FLOOR,
        "readable": reach is not None and reach >= REACH_FLOOR,
        "rule": f"delta over the second window >= {DELTA_FLOOR} AND reach >= {REACH_FLOOR}",
    }
    print(f"verdict: {verdict}")

    evidence = {
        "generatedBy": "evidence/longmemeval/scripts/semantic_carry_analysis.py",
        "sourceRun": source_run if source_run is not None else report.get("sourceRun"),
        "tier": tier,
        "population": population,
        "arm": {
            "reviewPass": config.get("reviewPass"),
            "semanticCarry": config.get("semanticCarry"),
            "reader": config.get("reader", {}).get("model"),
            "judge": config.get("judge", {}).get("model"),
            "runs": report.get("runs"),
        },
        # `S13` reads this key. Absent when the build carried no census, which is a different fact
        # from a census of zero -- the rule every optional field in the report follows.
        **({} if carry is None else {"semanticCarry": carry}),
        "windows": {
            "all": overall,
            "first": first_window,
            "second": second_window,
        },
        "mcnemar": {"p": round(p, 6), "b": len(regressions), "c": len(gains)},
        "verdict": verdict,
    }
    # The registered key is written only by a registered run. A screening pair writes its delta under
    # `screening`, so a row reading `paired.deltaQuestions` stays `unrun` rather than appearing to
    # pass on an instrument it was not registered on -- `self_index_analysis.py`'s rule for `S9`.
    if tier == "registered":
        evidence["paired"] = {
            "deltaQuestions": second_window["deltaQuestions"],
            "deltaQuestionsAllWindows": overall["deltaQuestions"],
            "n": second_window["n"],
        }
    else:
        evidence["screening"] = {
            "deltaQuestions": second_window["deltaQuestions"],
            "n": second_window["n"],
            "blocker": (
                "measured on a scoped population; S12 is registered on 500 corpora x 4 repetitions, "
                "where -5 questions is -1.0 point rather than the ratio this sample carries"
            ),
        }
    if write_to is not None:
        with open(write_to, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2)
            handle.write("\n")
        print(f"wrote {write_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
