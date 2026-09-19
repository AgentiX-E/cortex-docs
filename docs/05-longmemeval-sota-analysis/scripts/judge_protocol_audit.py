#!/usr/bin/env python3
"""Offline audit of the judge protocol against the official LongMemEval one.

Why this exists
---------------
`judge.ts` grades every answer with a single prompt:

    "Decide whether the predicted answer is semantically EQUIVALENT to the
     ground-truth answer."

The official LongMemEval protocol (`evaluate_qa.py`, Wu et al. 2025) dispatches
by question type and is materially looser in ways that matter:

  * default / multi-session: "answer yes if the response CONTAINS the correct
    answer ... If the response is equivalent to the correct answer OR CONTAINS
    ALL THE INTERMEDIATE STEPS to get the correct answer, you should also answer
    yes. If the response only contains A SUBSET of the information required by
    the answer, answer no."
    Note the tension the official prompt carries deliberately: containment is
    credited, but a strict subset is not.

  * temporal-reasoning adds: "do not penalize OFF-BY-ONE errors for the number
    of days."

  * knowledge-update replaces the subset clause with: "If the response contains
    some previous information along with an updated answer, the response should
    be considered as correct as long as the updated answer is the required
    answer."

  * abstention: judged separately, against an explanation, and the trap answer
    is withheld.

Because equivalence is strictly stronger than containment, our accuracy is
measured on a ruler that is not the published one, so it is not directly
comparable to published LongMemEval numbers.

What this script does NOT do
----------------------------
It does not re-grade. Deciding containment is a semantic judgement and only an
LLM can make it; a string heuristic would fabricate a number. What it DOES do is
enumerate every case where the two protocols provably disagree by construction:

  ABS      the prediction abstains and the gold sanctions abstention. The
           official protocol grades this as CORRECT; ours asks whether a null
           answer is "equivalent" to an explanatory sentence and returns NO.
           This is a protocol difference, not a model error, and it is
           decidable without an LLM.

  SUBSET   gold enumerates several items and the prediction supplies fewer. The
           official prompt says answer NO, so both protocols agree; these are
           NOT protocol differences and must not be counted as such.

  DISJUNCT gold contains an explicit alternative ("X or Y", "or Z if ..."). A
           prediction matching the alternative is correct under any reasonable
           reading, but a judge prompted for "equivalence" tends to answer NO.

The output is a bounded, auditable list of questions whose grade is determined by
the protocol rather than by the answer, so the size of the validity problem is
known before any re-grading is attempted.

Usage:
  judge_protocol_audit.py RUN_DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Markers the dataset uses to say "the answer is that the information is absent".
ABSTENTION_GOLD = re.compile(
    r"(did not mention|not enough|information provided is not|"
    r"you did not|no information|not mentioned)",
    re.I,
)
# An explicit alternative in the gold, e.g. "(or 12 days, if ...)".
DISJUNCTION = re.compile(r"\((?:or|alternatively)\b|\bor\s+\d", re.I)


def _load(run_dir: Path) -> list[dict]:
    out: list[dict] = []
    for name in ("benchmark-mr-diagnostics.json", "benchmark-single-session-diagnostics.json"):
        p = run_dir / name
        if p.exists():
            for r in json.loads(p.read_text()):
                r.setdefault("_source", name)
                out.append(r)
    return out


def _tri(r: dict) -> tuple[str, str, bool]:
    """(gold, predicted, graded_correct) with types normalised."""
    gold = str(r["ground_truth"])
    pred = r.get("decision", {}).get("answer")
    pred = "" if pred is None else str(pred)
    correct = r["correct"] if isinstance(r["correct"], bool) else str(r["correct"]) == "True"
    return gold, pred, correct


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    run_dir = Path(argv[1])
    records = _load(run_dir)

    abs_cases: list[dict] = []
    disjunct: list[dict] = []
    grades = {"correct": 0, "wrong": 0}
    for r in records:
        gold, pred, correct = _tri(r)
        grades["correct" if correct else "wrong"] += 1
        abstained = bool(r.get("decision", {}).get("abstained")) or pred in ("", "None")
        if abstained and ABSTENTION_GOLD.search(gold):
            abs_cases.append(r)
        elif not correct and DISJUNCTION.search(gold):
            disjunct.append(r)

    total = len(records)
    print(f"# Judge protocol audit -- {run_dir.name}\n")
    print(f"Graded questions: {total} ({grades['correct']} correct, {grades['wrong']} wrong)\n")

    print("## A. Abstention cases the official protocol credits")
    print(
        "The dataset's gold sanctions abstention and the system abstained. "
        "The official protocol grades this CORRECT by construction; ours asks "
        "whether a null answer is 'equivalent' to an explanatory sentence.\n"
    )
    credited = sum(1 for r in abs_cases if r["correct"])
    print("| capability | n | graded correct by us | officially correct |")
    print("|---|---|---|---|")
    caps: dict[str, list[dict]] = {}
    for r in abs_cases:
        caps.setdefault(r.get("capability", "MR"), []).append(r)
    for cap in sorted(caps):
        rows = caps[cap]
        c = sum(1 for r in rows if r["correct"])
        print(f"| {cap} | {len(rows)} | {c} | {len(rows)} |")
    if abs_cases:
        print(
            f"\nUnderstated by at least {len(abs_cases) - credited} question(s) on this "
            f"axis alone ({len(abs_cases)} abstentions, {credited} credited)."
        )

    print("\n## B. Gold with an explicit alternative the prediction may match")
    print(
        "A judge prompted for equivalence tends to answer NO when the gold "
        "offers 'X or Y' and the prediction states only Y, even though the gold "
        "sanctions Y. These are candidate false negatives.\n"
    )
    for r in disjunct:
        gold, pred, _ = _tri(r)
        print(f"- gold={gold[:110]!r}")
        print(f"  pred={pred[:60]!r} | {r['question'][:80]}")

    if not disjunct:
        print("- none matched by the pattern (absence does not prove absence)")

    print("\n## C. Bounds")
    print(
        "- (A) is a lower bound on protocol-attributable error: those cases are "
        "decidable without semantics.\n"
        "- (B) is a candidate list, not a count: confirming each requires a "
        "re-grade.\n"
        "- Semantic containment differences (prediction states more than the "
        "gold, with the gold answer included) are NOT captured here and only an "
        "LLM re-grade can size them."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
