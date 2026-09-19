#!/usr/bin/env python3
"""Test the "unsatisfiable premise" hypothesis for the deterministic MR set.

`37f165cf` turned out not to be an engine failure: the model enumerated the
sessions, correctly observed that none mentions finishing a novel in January or
March, and abstained. The gold session dates are May 22 and May 27. The premise
the question states is not present in the corpus, so `UNANSWERABLE` is the
correct response and the gold `856` is unreachable.

If that pattern generalises, a chunk of the "deterministic failure" set is not a
capability gap at all — it is the benchmark grading an answer against a premise
the retrieved evidence cannot satisfy. This script checks, for each deterministic
failure, whether the question's decisive qualifier (the month, the date, the
ordinal) occurs anywhere in the haystack, and whether the gold sessions in
particular are silent about it.

Usage:
  mr_premise_check.py [--data PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DEFAULT = Path("/tmp/lme-data/lme.json")

MONTHS = (
    "january february march april may june july august september october "
    "november december"
).split()

# question -> the qualifier tokens whose presence decides whether the premise is
# satisfiable, and a human label for what the question asks for.
CASES: dict[str, tuple[list[str], str]] = {
    "37f165cf": (["january", "march"], "novels finished in Jan and Mar"),
    "8e91e7d9": (["sister", "brother"], "siblings"),
    "10d9b85a": (["april"], "April workshops/lectures/conferences"),
    "0a995998": (["dress", "clothing", "shirt"], "clothing items"),
    "b5ef892d": (["doctor", "visit", "appointment"], "doctor visits"),
    "3fe836c9": (["purchase", "bought", "order"], "purchases"),
    "27016adc": (["read", "author", "book"], "books read"),
    "2318644b": (["museum", "art", "exhibit"], "museum visits"),
    "c18a7dc8": (["salary", "raise", "pay"], "salary changes"),
}


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def render_session(inst: dict, idx: int) -> str:
    date = inst["haystack_dates"][idx] if idx < len(inst.get("haystack_dates", [])) else None
    prefix = f"[{date}] " if date else ""
    return "\n".join(f"{prefix}{t['role']}: {t['content']}" for t in inst["haystack_sessions"][idx])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DATA_DEFAULT)
    args = ap.parse_args()

    if not args.data.exists() or args.data.stat().st_size == 0:
        print(f"dataset unavailable: {args.data}")
        return 2

    instances = {i["question_id"]: i for i in json.loads(args.data.read_text())}

    print("# Premise-satisfiability check for deterministic MR failures\n")
    print("| question | asks for | qualifier in gold sessions | qualifier in ANY session | sessions |")
    print("|---|---|---|---|---|")

    for qid, (tokens, label) in CASES.items():
        inst = instances.get(qid)
        if inst is None:
            print(f"| {qid} | {label} | - | NOT FOUND | - |")
            continue

        gold_ids = set(inst.get("answer_session_ids", []))
        gold_text = ""
        all_text = ""
        for idx in range(len(inst["haystack_sessions"])):
            body = norm(render_session(inst, idx))
            all_text += body + "\n"
            sid = inst["haystack_session_ids"][idx]
            if sid in gold_ids:
                gold_text += body + "\n"

        in_gold = [t for t in tokens if t in gold_text]
        in_all = [t for t in tokens if t in all_text]
        n_sessions = len(inst["haystack_sessions"])

        print(
            f"| {qid} | {label} | "
            f"{('YES (' + ', '.join(in_gold) + ')') if in_gold else '**NO**'} | "
            f"{('YES (' + ', '.join(in_all) + ')') if in_all else '**NO**'} | "
            f"{n_sessions} |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
