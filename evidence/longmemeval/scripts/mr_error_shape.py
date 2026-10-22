#!/usr/bin/env python3
"""Locate the MR error precisely: ledger membership, not ledger arithmetic.

Why this exists
---------------
The P7 plan assumed the failure was "enumerate then count, with the count not
derivable from the enumeration", and proposed forcing a numbered ledger with a
self-consistency check. Before implementing that, it is worth testing whether the
premise holds. It does not.

Reading the frozen `llmRaw` for the 121 MR questions, the model's Step 2 is
already a careful DISTINCT count over its own Step 1 list, including correct
merging of duplicate mentions:

    - Dr. Smith (primary care physician)
    - ENT specialist (2023/05/21) -- same person as Dr. Patel on 2023/05/22
    - Dr. Patel (ENT specialist)
    - Dr. Lee (dermatologist)
    Distinct doctors: Dr. Smith, Dr. Patel (ENT specialist), Dr. Lee = 3

That question is graded correct. So a self-consistency check between the ledger
and the answer would add nothing: the arithmetic is sound, and in the correct
cases the ledger is intentionally LONGER than the answer because duplicates are
folded at Step 2.

This script measures the one property that does separate the classes:

    is the gold item set a subset of what the model described?

That is not decidable in general, but two proxies are, and both are reported:

  * LEDGER vs ANSWER — how often the Step 1 list length equals the answer. A
    forced-ledger prompt would only help if this were frequently violated; it is
    not.

  * DIRECTION — for numeric answers, whether the prediction is below or above
    the gold. Under-count and over-count point at different causes: under-count
    suggests a missed item, over-count suggests an item that should have been
    merged or excluded.

Usage:
  mr_error_shape.py RUN_DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STEP1 = re.compile(r"Step 1(.*?)(?=Step 2|\Z)", re.S)
BULLET = re.compile(r"^\s*[-*]\s+", re.M)
NUM = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")

# The pipeline strips assistant turns before retrieval; the diagnostics keep the
# unfiltered body, so the same filter has to be applied on this side.
TURN_BOUNDARY = r"(?=\[\d{4}/\d{2}/\d{2}[^\]]*\] )"
ASSISTANT_TURN = re.compile(r"(?:^|\]\s*)assistant:")


def user_only(body: str) -> str:
    turns = [t for t in re.split(TURN_BOUNDARY, body) if t]
    return "".join(t for t in turns if not ASSISTANT_TURN.search(t))


def fact_present(body: str, frame: str, window: int = 150) -> bool:
    flat = " ".join(user_only(body).split())
    if not flat:
        return False
    if len(flat) <= window:
        return flat in frame
    step = max(1, len(flat) // 8)
    return any(flat[i : i + window] in frame for i in range(0, len(flat) - window + 1, step))


def ledger_len(raw: str) -> int | None:
    m = STEP1.search(raw)
    return len(BULLET.findall(m.group(1))) if m else None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    run_dir = Path(argv[1])
    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())

    complete = []
    for r in records:
        frame = " ".join((r.get("decision", {}).get("retrieved") or "").split())
        if all(fact_present(b, frame) for b in r.get("answer_sessions_content") or []):
            complete.append(r)

    print(f"# MR error shape -- {run_dir.name}\n")
    print(f"Instances: {len(records)}, evidence complete: {len(complete)}\n")

    stats = {"correct": {"ledger==ans": 0, "ledger!=ans": 0, "no_ledger": 0},
             "wrong": {"ledger==ans": 0, "ledger!=ans": 0, "no_ledger": 0}}
    under = over = equal = 0
    for r in complete:
        raw = r["decision"].get("llmRaw") or ""
        ans = r["decision"].get("answer")
        key = "correct" if r["correct"] else "wrong"
        n = ledger_len(raw)
        if n is None:
            stats[key]["no_ledger"] += 1
        else:
            m = NUM.search(str(ans)) if ans is not None else None
            # Only a plain integer answer can be compared to a list length;
            # "3.5 weeks" is a computed value and "2,500" is a sum, not a count.
            if m and "." not in m.group() and "," not in m.group() and n == int(m.group()):
                stats[key]["ledger==ans"] += 1
            else:
                stats[key]["ledger!=ans"] += 1
        gm = NUM.search(str(r["ground_truth"]))
        pm = NUM.search(str(ans)) if ans is not None else None
        if gm and pm:
            g, p = float(gm.group().replace(",", "")), float(pm.group().replace(",", ""))
            if p < g:
                under += 1
            elif p > g:
                over += 1
            else:
                equal += 1

    print("## Step 1 ledger length vs stated answer\n")
    print("| class | ledger == answer | ledger != answer | no ledger |")
    print("|---|---|---|---|")
    for k in ("correct", "wrong"):
        s = stats[k]
        print(f"| {k} | {s['ledger==ans']} | {s['ledger!=ans']} | {s['no_ledger']} |")

    print("\n## Direction of numeric error (evidence-complete instances)\n")
    print("| direction | n |")
    print("|---|---|")
    print(f"| prediction < gold (under) | {under} |")
    print(f"| prediction > gold (over) | {over} |")
    print(f"| prediction == gold | {equal} |")

    print(
        "\nInterpretation: a ledger/answer mismatch is the NORMAL case in correct "
        "answers too, because Step 2 folds duplicate mentions. A forced "
        "ledger-equality check would therefore penalise correct behaviour. The "
        "discriminating step is which items enter the ledger, which no "
        "arithmetic guard can repair."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
