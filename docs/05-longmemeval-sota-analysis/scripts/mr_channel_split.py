#!/usr/bin/env python3
"""Recover the per-channel decomposition of a logged MR prompt.

`retrieveSessionsForQuestion` builds `hits` in two stages: `reciprocalRankFusion`
of the centroid and expansion channels (capped at `sessionTopK`), then
`hits.push(...turnHits)` from turn recall. Because turn recall **appends**, the
channel that produced any given session is recoverable from its position in the
logged prompt — no instrumentation of the running engine required.

This lets a frozen diagnostics file answer "which retrieval channel missed the
gold session", which is the question that decides where a recall fix belongs.

Usage:
  mr_channel_split.py RUN_DIR QUESTION_ID [--topk 10]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SESSION_START = re.compile(r"\[(\d{4}/\d{2}/\d{2} \([A-Za-z]{3}\) \d{2}:\d{2})\]")
TRUNCATED = "[truncated]"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("question_id")
    ap.add_argument("--topk", type=int, default=10, help="sessionTopK (RRF cap)")
    ap.add_argument("--gold-dates", nargs="*", default=None)
    args = ap.parse_args()

    path = Path(args.run_dir) / "benchmark-mr-diagnostics.json"
    records = json.loads(path.read_text())
    r = next((x for x in records if x["question_id"] == args.question_id), None)
    if r is None:
        print(f"question {args.question_id} not found in {path}")
        return 2

    d = r["decision"]
    print(f"## {args.question_id}")
    print(f"Q: {r['question']}")
    print(f"gold: {r['ground_truth']!r}")
    print(f"expansionQueries: {d.get('expansionQueries')}")
    print()

    # Blocks separated by the join('\n\n') the engine uses; markers are separate
    # blocks because the marker text is appended with a leading newline.
    blocks = [
        b.strip()
        for b in d["retrieved"].split("\n\n")
        if b.strip() and not b.strip().startswith(TRUNCATED)
    ]

    gold_dates = args.gold_dates or []
    print(f"| slot | channel | session date | gold? |")
    print(f"|---|---|---|---|")
    for i, b in enumerate(blocks):
        m = SESSION_START.match(b)
        date = m.group(1) if m else "?"
        channel = "turn-recall" if i >= args.topk else "RRF"
        is_gold = any(date.startswith(g) for g in gold_dates)
        print(f"| {i} | {channel} | {date} | {'**YES**' if is_gold else ''} |")

    print()
    rrf = [SESSION_START.match(b) for b in blocks[: args.topk]]
    turn = [SESSION_START.match(b) for b in blocks[args.topk :]]
    print(f"RRF slots filled: {sum(1 for m in rrf if m)}/{args.topk}")
    print(f"turn-recall slots filled: {sum(1 for m in turn if m)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
