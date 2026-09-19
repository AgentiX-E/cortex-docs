#!/usr/bin/env python3
"""Dump the raw evidence for the deterministic abstention questions.

`mr_budget_stage.py` produced a result that refutes the working hypothesis:
neither `truncateSession` nor `maxAggregationChars` is eating the needle. The
joined text is 3.9 KB against a 20 KB clip, so Candidate B is arithmetically
impossible, and `8e91e7d9` keeps both needles through every stage.

That leaves one question (`8e91e7d9`) whose needles reach the prompt yet whose
answer is a bare abstention token. This script prints the raw material needed to
decide *why*: the gold, the decision, and a window around each needle inside the
logged prompt, so the claim rests on the bytes rather than on my reading.

Usage:
  mr_needle_forensics.py RUN_DIR QUESTION_ID [needle ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(s: str) -> str:
    return " ".join(s.split())


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1])
    qid = argv[2]
    needles = argv[3:]

    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())
    r = next((x for x in records if x["question_id"] == qid), None)
    if r is None:
        print(f"question {qid} not found")
        return 2

    d = r["decision"]
    print(f"## {qid}")
    print(f"Q: {r['question']}")
    print(f"GOLD: {r['ground_truth']!r}")
    print(f"correct: {r['correct']}")
    print(f"reason: {d['reason']!r}  abstained={d['abstained']}  top1={d['top1Score']}")
    print(f"answer: {d['answer']!r}")
    print(f"expansionQueries: {d.get('expansionQueries')}")
    print(f"retrieved chars: {len(d['retrieved'])}")
    print(f"llmRaw: {d.get('llmRaw')!r}"[:600])
    print()

    bodies = [b for b in (r.get("answer_sessions_content") or []) if b]
    prompt = norm(d["retrieved"])
    for needle in needles:
        n = norm(needle).lower()
        for i, b in enumerate(bodies):
            nb = norm(b).lower()
            j = nb.find(n)
            print(f"--- needle {needle!r} in answer_session[{i}] (len={len(b)}): found={j >= 0}")
            if j >= 0:
                print(f"    gold ctx: ...{nb[max(0, j - 160):j + 160]}...")
        j = prompt.lower().find(n)
        print(f"--- needle {needle!r} in logged prompt: found={j >= 0}")
        if j >= 0:
            print(f"    prompt ctx: ...{prompt[max(0, j - 300):j + 300]}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
