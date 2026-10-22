"""Reconstruct the two events of every two-event `relative` failure.

`computeTemporalAnswer` is pure, so the six production failures can be replayed
offline WITHOUT an LLM. The reconstruction is exact:

  * the engine answers elapsed(A -> questionDate), so A = questionDate - answer;
  * the gold is elapsed(A -> B), so B = A + gold.

The reconstruction is self-checking: B must fall on or before the question date
(an event that has not happened yet cannot be the anchor). If that holds for all
six, the fixtures below are faithful and can be turned straight into unit tests.

Usage: python3 tr_reconstruct_fixtures.py [root] [arm]
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/analysis/ab_turn")
ARM = sys.argv[2] if len(sys.argv) > 2 else "treatment"

# (question fragment, observed wrong answer, gold number, unit)
CASES = [
    ("baking class", 5, 21, "day"),
    ("Evelyn Hugo", 44, 18, "day"),
    ("ukulele", 59, 24, "day"),
    ("flu", 38, 15, "week"),
    ("website", 24, 19, "day"),
    ("Adidas", 24, 14, "day"),
]


def main() -> None:
    data = json.loads((ROOT / f"tr_census_{ARM}.json").read_text())
    qs = [q for q in data["questions"] if q["kind"] == "relative"]

    print(f"=== reconstructed fixtures ({ARM}) ===\n")
    ok_all = True
    for frag, got, gold, unit in CASES:
        match = next((q for q in qs if frag.lower() in q["question"].lower()), None)
        if match is None:
            print(f"  {frag}: NOT FOUND")
            ok_all = False
            continue
        y, m, d = (int(x) for x in match["questionDate"][:10].split("/"))
        qdate = date(y, m, d)
        span = timedelta(weeks=got) if unit == "week" else timedelta(days=got)
        gap = timedelta(weeks=gold) if unit == "week" else timedelta(days=gold)
        a = qdate - span
        b = a + gap
        consistent = b <= qdate
        ok_all = ok_all and consistent
        print(f"  {frag}")
        print(f"    {match['question'][:92]}")
        print(f"    qdate={qdate}  A={a}  B={b}  B<=qdate={consistent}")
        print(f"    observed={got}  gold={gold}  elapsed(A,B)={gap.days}d -> {got and gold}"
              f"  [{unit}]")
        print(f"    answers across runs = {match['answers']}")
        print()

    print(f"all reconstructions self-consistent: {ok_all}")


if __name__ == "__main__":
    main()
