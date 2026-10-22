"""Classify every LongMemEval-S MR question by whether deterministic item
counting may safely be applied to it, and cross-tabulate against the current
(treatment-arm) correctness.

The question is scoping, not mechanism: the structured extractor counts
DISTINCT items and collapses duplicates, so it is only valid where the gold
answer is a count of distinct entities. Where the gold answer is a sum of
durations ("how many hours in total") or a count of repeated OCCURRENCES
("how many times did I bake"), deduplicating by item name is systematically
wrong, and those questions must stay on the free-form path.

Read-only on the downloaded A/B artifacts.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ARM = "treatment"
ROOT = Path(__file__).parent / "ab_turn" / ARM

# Units of measure: "how many <unit>" asks for a SUM or a RATE, never a count of
# distinct items. The free-form prompt already says so in its Step 2.
UNITS = (
    r"hours|hour|days|day|weeks|week|months|month|years|year|minutes|minute|"
    r"miles|mile|kilometers|kilometer|pounds|pound|dollars|dollar|pages|page|"
    r"points|point|percent|percentage|episodes|episode|views|view|comments|"
    r"comment|people|meals|meal|gallons|gallon|liters|liter|calories|calorie|"
    r"mpg|steps|step"
)
# Repeated-occurrence nouns: each occurrence is a separate event, so collapsing
# them by name undercounts. "How many doctor's appointments" is 2 events that
# both happen to be named "appointment".
OCCURRENCE = (
    r"times?\b|appointments?\b|visits?\b|sessions?\b|trips?\b|occasions?\b|"
    r"instances?\b|episodes?\b|attempts?\b|rounds?\b|laps?\b"
)
# Derivation triggers, mirroring classifyAggregationKind.
DERIVATION = (
    r"\b(percentage|percent|average|mean|difference (?:in|between)|how much "
    r"(?:more|less|faster|earlier|older)|increase in|decrease in|discount|"
    r"cashback|minimum|maximum|how old was)\b"
)
DERIVATION_UNIT = (
    r"\bhow many (?:years|months|weeks|days|hours|minutes|dollars|points|miles|"
    r"kilometers|pounds|percent|percentage)\s+(?:older|younger|more|less|longer|"
    r"shorter|faster|slower|earlier|later|heavier|lighter|higher|lower|bigger|"
    r"smaller)\b"
)


# NOTE: every alternation below must be wrapped in a non-capturing group before
# it is concatenated into a larger pattern. Without the wrapper the `|` splits
# the WHOLE pattern, so `hour` matches anywhere in the question and nearly every
# counting question is misread as a sum.
MODIFIERS = r"(?:total |different |distinct |other |new |unique )*"


def kind(question: str) -> str:
    q = question.lower()
    if re.search(DERIVATION, q) or re.search(DERIVATION_UNIT, q):
        return "derivation"
    if not re.search(r"\bhow many\b|\bwhat is the total number of\b", q):
        return "other"
    if re.search(r"\bhow many times\b", q):
        return "occurrence"
    if re.search(rf"\bhow many {MODIFIERS}(?:{UNITS})\b", q):
        return "sum"
    if re.search(rf"\bhow many {MODIFIERS}(?:{OCCURRENCE})", q):
        return "occurrence"
    if re.search(rf"\btotal number of (?:{UNITS})\b", q):
        return "sum"
    return "counting"


# Correctness rule copied verbatim from turn_recall_ab.verdict so the two
# analyses never disagree about which answer is right: exact match, else a
# numeric comparison on questions that ask for one.
COUNTING_Q = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")


def norm(a: object) -> str:
    return re.sub(r"\s+", "", str(a).strip().lower())


def lead(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def correct(q: str, answer: object, expected: object) -> bool:
    if answer is None:
        return False
    if norm(answer) == norm(expected):
        return True
    if COUNTING_Q.search(q):
        p, e = lead(answer), lead(expected)
        if p is not None and e is not None:
            return p == e
    return False


def modal(answers: list[str | None]) -> tuple[str | None, int]:
    vals = [a for a in answers if a is not None]
    if not vals:
        return None, 0
    counts: dict[str, int] = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    best = max(counts.values())
    for v, c in counts.items():
        if c == best:
            return v, c
    raise AssertionError


def main() -> None:
    runs = sorted(glob.glob(str(ROOT / "*" / "benchmark-mr-diagnostics.json")))
    per_q: dict[str, list[str | None]] = {}
    gold: dict[str, object] = {}
    for f in runs:
        for r in json.load(open(f)):
            dec = r.get("decision") or {}
            per_q.setdefault(r["question"], []).append(dec.get("answer"))
            gold[r["question"]] = r["ground_truth"]

    rows = []
    for q, answers in per_q.items():
        ans, n = modal(answers)
        g = gold[q]
        # The bucket is decided by a majority vote over the 4 runs, so a 2/2 tie
        # is scored wrong. Using a single run's answer here would contradict the
        # accuracy the A/B reports.
        ok = n * 2 > len(answers) and correct(q, ans, g)
        rows.append((kind(q), ok, n, g, ans, q))

    rows.sort(key=lambda r: (r[0], not r[1]))
    print(f"MR questions: {len(rows)}; runs per question: {len(runs)}")
    print(f"overall correct: {sum(1 for r in rows if r[1])}/{len(rows)}\n")
    tally: dict[str, list[int]] = {}
    for k, c, *_ in rows:
        tally.setdefault(k, [0, 0])
        tally[k][0] += 1
        tally[k][1] += 1 if c else 0

    print(f"{'kind':<12}{'n':>4}{'correct':>9}{'acc':>8}")
    for k in sorted(tally):
        n, c = tally[k]
        print(f"{k:<12}{n:>4}{c:>9}{c / n:>8.1%}")

    print("\n--- counting (the population deterministic counting would take over) ---")
    for k, c, n, g, a, q in rows:
        if k == "counting":
            print(f"  {'OK ' if c else 'BAD'} gold={str(g)[:18]:<18} modal={str(a)[:10]:<10} {q[:78]}")

    print("\n--- excluded on purpose (sum / occurrence) ---")
    for k, c, n, g, a, q in rows:
        if k in ("sum", "occurrence"):
            print(f"  {k:<11}{'OK ' if c else 'BAD'} gold={g!s:<20} {q[:80]}")


if __name__ == "__main__":
    main()
