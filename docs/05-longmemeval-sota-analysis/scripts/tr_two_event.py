"""Quantify the two-event temporal bug found in `computeTemporalAnswer`.

For `kind === 'relative'` the engine computes

    elapsed(normalized[0].date, questionDate)

unconditionally: it always measures to the QUESTION DATE and always takes the
FIRST event the LLM listed. A question like

    "How many days had passed since I started ukulele lessons
     when I took my guitar to the tech?"

names TWO events and asks for elapsed(A -> B), so the engine answers
elapsed(A -> questionDate) instead — measured 59 against a gold of 24, stable
across all 4 runs because the computation is deterministic.

This splits the `relative` bucket by whether the question names a second event
(the word "when") and compares accuracy, which tests the mechanism directly: if
the two-event subset is markedly worse, the reference date is the bug.

Usage: python3 tr_two_event.py [root] [arm]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/analysis/ab_turn")
ARM = sys.argv[2] if len(sys.argv) > 2 else "treatment"

LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
# "since A when B" / "had I been X when Y" / "ago did I A when I B"
TWO_EVENT = re.compile(r"\bwhen\b", re.I)
SINCE_WHEN = re.compile(r"\bsince\b.*\bwhen\b", re.I)

DAYS = {"day": 1, "week": 7, "month": 30}


def norm(v) -> str:
    return re.sub(r"\s+", "", str(v).strip().lower())


def lead(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def gold_nums(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)", str(text)):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def correct(answer, gold) -> bool | None:
    if answer is None:
        return False
    if norm(answer) == norm(gold):
        return True
    nums = gold_nums(gold)
    p = lead(answer)
    if p is not None and nums:
        return any(abs(p - g) < 1e-9 for g in nums)
    return None


def main() -> None:
    data = json.loads((ROOT / f"tr_census_{ARM}.json").read_text())
    qs = data["questions"]
    runs = len(data["runs"])

    print(f"=== {ARM}: {len(qs)} TR questions x {runs} runs\n")
    print(f"{'subset':<44}{'n':>4}{'acc':>8}{'stable wrong':>14}")
    for label, sel in (
        ("relative, no second event", [q for q in qs if q["kind"] == "relative" and not TWO_EVENT.search(q["question"])]),
        ("relative, NAMES a second event ('when')", [q for q in qs if q["kind"] == "relative" and TWO_EVENT.search(q["question"])]),
        ("  ... of which 'since ... when'", [q for q in qs if q["kind"] == "relative" and SINCE_WHEN.search(q["question"])]),
        ("interval / ordering (engine, control)", [q for q in qs if q["kind"] in ("interval", "ordering")]),
    ):
        if not sel:
            continue
        good = sum(1 for q in sel if all(correct(a, q["gold"]) is not False for a in q["answers"]))
        stable = sum(
            1
            for q in sel
            if all(correct(a, q["gold"]) is False for a in q["answers"])
        )
        print(f"{label:<44}{len(sel):>4}{good / len(sel):>8.1%}{stable:>14}")

    print("\n--- two-event relative questions, one row each ---")
    two = [q for q in qs if q["kind"] == "relative" and TWO_EVENT.search(q["question"])]
    for q in two:
        vs = [correct(a, q["gold"]) for a in q["answers"]]
        tag = "OK " if all(v is not False for v in vs) else "BAD"
        g = gold_nums(q["gold"])
        p = lead(q["answers"][0])
        gap = ""
        if g and p is not None:
            gap = f"  gap={p - min(g, key=lambda x: abs(x - p)):+g}"
        print(f"  {tag} gold={str(q['gold'])[:22]:<22} got={str(q['answers'][0])[:8]:<8}{gap}")
        print(f"       {q['question'][:100]}")

    print("\n--- non-relative TR questions that also name two events ---")
    other_two = [
        q for q in qs if q["kind"] != "relative" and TWO_EVENT.search(q["question"])
    ]
    for q in other_two:
        vs = [correct(a, q["gold"]) for a in q["answers"]]
        tag = "OK " if all(v is not False for v in vs) else "BAD"
        print(f"  [{q['kind']:<11}] {tag} gold={str(q['gold'])[:20]:<20} "
              f"got={str(q['answers'][0])[:14]:<14} {q['question'][:76]}")


if __name__ == "__main__":
    main()
