#!/usr/bin/env python3
"""`S10`: the per-turn window against the registered rendering, paired across two dispatches.

## Why two artifacts rather than two sides of one pass

`S12` pairs inside one artifact because its treatment is a switch of the same class as the pairing variable:
`CORTEX_MEMORY_AB=carry` builds both sides from one constructor with one flag between them. `S10` is not that
shape. Its two sides are the **registered configuration** and the same configuration with
`cortex_memory_max_turn_chars=400::match`, each dispatched as its own run -- which is what
`MEASURE-TURN-WINDOW.md` §2 registered and what §9 executed (`43433744411` against `43437140082`).

Two dispatches can be mispaired in ways one artifact cannot, so this file refuses rather than assumes:

| check | why it is a refusal and not a comment |
| --- | --- |
| the question sets are equal | a delta over the intersection reported as the whole is a number about a population nobody dispatched |
| the repetition counts are equal | a mean over two against a mean over four is not a pair |
| the reader and judge are equal | every difference would be attributed to the window |

## Why the alignment is by question id

`ablation.{side}CorrectByRun` is one bitstring per repetition, aligned with that artifact's own roster. Two
artifacts of one population can list the questions in different orders -- a shard merge assembles its parts in
whatever order the artifacts arrive -- and pairing by position would swap two questions and publish the sum of
two unrelated differences. The vectors are therefore indexed by id and rebuilt in one order.

## What `P1` is, and what it is not

`P1` asks what share of the turns the control cut now carries an elision. That share is **item-level**, and
two run-level totals cannot supply it: the treatment's `cut` counts windowed turns and the control's counts
head-cut turns, and the two sets overlap without being equal. What this file publishes is therefore the four
counts from both sides plus `reached = treatment.marked / control.cut` as a **run-level approximation**, named
as such. `MEASURE-TURN-WINDOW.md` §9.3 is the record of what happens when a share is inferred from something
that is not a count of the event, and the approximation is labelled rather than promoted.

Usage:
  python3 turn_window_analysis.py control.json treatment.json [--write ../turn-window.json]
      [--tier registered|screening] [--run-control ID] [--run-treatment ID]
"""
from __future__ import annotations

import json
import sys
from math import comb
from typing import Any

DELTA_FLOOR = -5


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
    """Each question's mean correct over the repetitions, keyed by id.

    The length of every bitstring is checked rather than trusted: a vector that is not aligned with its own
    roster would make every per-question mean a guess that looks like a number.
    """
    rows = report["questions"]
    ids = [row["questionId"] for row in rows]
    runs = report["ablation"][f"{side}CorrectByRun"]
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], str):
        raise SystemExit(
            f"refusing: {side} carries no `{side}CorrectByRun` bitstrings, so the pairing cannot be "
            "recomputed and a verdict from `questions[].correct` would be a one-repetition reading of a "
            "multi-repetition run"
        )
    for index, bits in enumerate(runs):
        if len(bits) != len(ids):
            raise SystemExit(
                f"refusing: {side} run {index} carries {len(bits)} verdicts for {len(ids)} questions, so "
                "the bitstring is not aligned with the roster"
            )
    return {
        qid: sum(1 for bits in runs if bits[position] == "1") / len(runs)
        for position, qid in enumerate(ids)
    }


def first_repetition(report: dict[str, Any], side: str) -> dict[str, bool]:
    runs = report["ablation"][f"{side}CorrectByRun"]
    ids = [row["questionId"] for row in report["questions"]]
    return {qid: runs[0][position] == "1" for position, qid in enumerate(ids)}


def reader_of(report: dict[str, Any]) -> tuple[Any, Any]:
    config = report.get("memoryArmConfig", {})
    return (
        (config.get("reader") or {}).get("model"),
        (config.get("judge") or {}).get("model"),
    )


def compare(control: dict[str, Any], treatment: dict[str, Any]) -> None:
    """The three refusals, before any number is computed."""
    left = {row["questionId"] for row in control["questions"]}
    right = {row["questionId"] for row in treatment["questions"]}
    if left != right:
        only_control = sorted(left - right)
        only_treatment = sorted(right - left)
        raise SystemExit(
            "refusing: the two artifacts do not carry the same population. "
            f"Control only: {only_control[:10]}{'...' if len(only_control) > 10 else ''}. "
            f"Treatment only: {only_treatment[:10]}{'...' if len(only_treatment) > 10 else ''}. "
            "A delta over the intersection would be a number about a population nobody dispatched."
        )
    control_runs = len(control["ablation"]["featureCorrectByRun"])
    treatment_runs = len(treatment["ablation"]["featureCorrectByRun"])
    if control_runs != treatment_runs:
        raise SystemExit(
            f"refusing: the sides ran {control_runs} and {treatment_runs} repetitions. A mean over "
            f"{control_runs} against a mean over {treatment_runs} is not a pair, and the delta would be a "
            "difference between two instruments rather than between two windows."
        )
    if reader_of(control) != reader_of(treatment):
        raise SystemExit(
            f"refusing: the reader or judge differs between the sides: {reader_of(control)} against "
            f"{reader_of(treatment)}. Every difference would then be attributed to the window."
        )


def window_block(control: dict[str, Any], treatment: dict[str, Any]) -> dict[str, Any]:
    """`P1`'s counts, or nothing at all when either side does not report them."""
    left = control.get("turnWindow")
    right = treatment.get("turnWindow")
    if left is None or right is None:
        return {}
    cut = left.get("cut", 0)
    marked = right.get("marked", 0)
    return {
        "control": left,
        "treatment": right,
        # Named as an approximation because it is one: the two `cut` sets overlap without being equal, so
        # this is a ratio of two run-level counts, not the share of the control's cut items that the
        # treatment marked. `MEASURE-TURN-WINDOW.md` §9.3 is why the distinction is stated rather than
        # glossed -- a share inferred from something that is not a count of the event is how `P1` became
        # unreadable in the first place.
        "reached": None if cut == 0 else round(marked / cut, 4),
        "reachedBasis": "run-level: treatment.marked / control.cut, not an item-level pairing",
    }


def usage_of(*reports: dict[str, Any]) -> dict[str, int]:
    totals = {"calls": 0, "promptTokens": 0, "cacheHitPromptTokens": 0, "completionTokens": 0}
    seen = False
    for report in reports:
        usage = report.get("llmUsage")
        if usage is None:
            continue
        missing = [key for key in totals if not isinstance(usage.get(key), int)]
        if missing:
            raise SystemExit(f"refusing: llmUsage carries no integer {', '.join(missing)}")
        for key in totals:
            totals[key] += usage[key]
        seen = True
    return totals if seen else {}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    control = load(argv[0])
    treatment = load(argv[1])
    write_to = argv[argv.index("--write") + 1] if "--write" in argv else None
    tier = argv[argv.index("--tier") + 1] if "--tier" in argv else "registered"
    if tier not in ("screening", "registered"):
        raise SystemExit(f"refusing: --tier {tier!r} is neither screening nor registered")

    compare(control, treatment)

    means_control = per_question_means(control, "feature")
    means_treatment = per_question_means(treatment, "feature")
    ids = sorted(means_control)
    delta = sum(means_treatment[qid] - means_control[qid] for qid in ids)

    left = first_repetition(control, "feature")
    right = first_repetition(treatment, "feature")
    lost = [qid for qid in ids if left[qid] and not right[qid]]
    gained = [qid for qid in ids if right[qid] and not left[qid]]
    p = mcnemar(len(lost), len(gained))

    print(f"population: {len(ids)} questions, {len(control['ablation']['featureCorrectByRun'])} repetitions")
    print(f"reader: {reader_of(control)[0]}  judge: {reader_of(control)[1]}")
    print(f"paired delta: {delta:+.4f} questions over {len(ids)}")
    print(f"mcnemar (first repetition): b={len(lost)} c={len(gained)} p={p:.4f}")

    window = window_block(control, treatment)
    print(f"window: {window.get('control')} -> {window.get('treatment')}")
    usage = usage_of(control, treatment)
    if usage:
        print(f"usage: {usage}")

    evidence: dict[str, Any] = {
        "generatedBy": "evidence/longmemeval/scripts/turn_window_analysis.py",
        "tier": tier,
        "sources": {
            "control": argv[argv.index("--run-control") + 1]
            if "--run-control" in argv
            else control.get("sourceRun"),
            "treatment": argv[argv.index("--run-treatment") + 1]
            if "--run-treatment" in argv
            else treatment.get("sourceRun"),
        },
        "population": {
            "questions": len(ids),
            "runs": len(control["ablation"]["featureCorrectByRun"]),
        },
        "arm": {
            "reader": reader_of(control)[0],
            "judge": reader_of(control)[1],
            "maxTurnChars": control.get("memoryArmConfig", {}).get("maxTurnChars"),
            "window": {
                "control": control.get("memoryArmConfig", {}).get("turnWindow", "head"),
                "treatment": treatment.get("memoryArmConfig", {}).get("turnWindow", "head"),
            },
        },
        "windows": {
            "paired": {
                "n": len(ids),
                "deltaQuestions": round(delta, 4),
                "discordant": {"controlOnly": len(lost), "treatmentOnly": len(gained)},
            }
        },
        "mcnemar": {"p": round(p, 6), "b": len(lost), "c": len(gained)},
        **({} if not window else {"turnWindow": window}),
        **({} if not usage else {"usage": usage}),
        "verdict": {
            "withinThreshold": delta >= DELTA_FLOOR,
            "rule": f"paired delta >= {DELTA_FLOOR} questions",
        },
    }
    # The registered key is written only by a registered pair, for the reason `semantic_carry_analysis.py`
    # gives: a screening pair leaves it absent, so the row that reads it stays `unrun` rather than appearing
    # to pass on an instrument it was not registered on.
    if tier == "registered":
        evidence["paired"] = evidence["windows"]["paired"]
    else:
        evidence["screening"] = {
            **evidence["windows"]["paired"],
            "blocker": "measured on a scoped population; S10 is registered on 500 questions x 4 repetitions",
        }
    print(f"verdict: {evidence['verdict']}")

    if write_to is not None:
        with open(write_to, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2)
            handle.write("\n")
        print(f"wrote {write_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
