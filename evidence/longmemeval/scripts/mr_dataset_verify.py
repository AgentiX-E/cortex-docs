#!/usr/bin/env python3
"""Verify needle presence in the OFFICIAL dataset, not in the diagnostic dump.

`p11-mr-instrument-defect.md` showed that `benchmark-mr-diagnostics.json` stores
`answer_sessions_content` (gold sessions) beside a prompt built from all
haystack sessions, so any check that reads the diagnostic field is checking the
wrong object. This script goes to the source: `/tmp/lme-data/lme.json`.

For each deterministic MR failure it answers two questions that the diagnostic
artifact could not:

  1. Is the needle actually present in the gold session(s)?
  2. Is the gold session's text retrievable from the haystack by the words the
     question and its expansion phrases would use?

Question 1 separates "the dataset genuinely states the fact" from "the fact is
implied and the gold is aggressive". Question 2 estimates an upper bound on
lexical recall: if a plain keyword scan over the 47 sessions cannot reach the
gold session, no embedding retriever should be expected to either.

Usage:
  mr_dataset_verify.py [--data PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DEFAULT = Path("/tmp/lme-data/lme.json")

# Deterministic failures and the evidence terms each question turns on. The
# terms are the question's own content words plus the obvious paraphrase; they
# are used for a lexical recall upper bound, so being generous is the point.
PROBES: dict[str, list[str]] = {
    "8e91e7d9": ["sibling", "sister", "brother"],
    "37f165cf": ["child", "children", "kid", "son", "daughter"],
    "10d9b85a": ["child", "children", "kid", "son", "daughter"],
    "0a995998": ["dress", "clothes", "clothing", "shirt", "pants"],
    "b5ef892d": ["doctor", "appointment", "visit", "clinic"],
    "3fe836c9": ["item", "purchase", "bought", "order"],
    "27016adc": ["book", "read", "author", "title"],
    "6a1eabeb": ["class", "course", "lesson", "workshop"],
    "gpt4_8279ba03": ["concert", "show", "ticket", "performance"],
    "gpt4_59149c78": ["hike", "trail", "km", "miles", "walk"],
    "2318644b": ["museum", "exhibit", "gallery", "art"],
    "6040dd4d": ["recipe", "cook", "meal", "dish"],
    "c18a7dc8": ["salary", "raise", "income", "pay"],
}


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def turn_text(turn: dict, date: str | None) -> str:
    prefix = f"[{date}] " if date else ""
    return f"{prefix}{turn['role']}: {turn['content']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DATA_DEFAULT)
    args = ap.parse_args()

    if not args.data.exists() or args.data.stat().st_size == 0:
        print(f"dataset unavailable: {args.data}")
        return 2

    instances = {i["question_id"]: i for i in json.loads(args.data.read_text())}
    print("# Official-dataset verification of deterministic MR failures\n")
    print("| question | gold | needle in gold? | gold reachable by | sessions matching |")
    print("|---|---|---|---|---|")

    for qid, probes in PROBES.items():
        inst = instances.get(qid)
        if inst is None:
            print(f"| {qid} | - | NOT FOUND | - | - |")
            continue

        ids = inst.get("haystack_session_ids", [])
        dates = inst.get("haystack_dates", [])
        sessions = inst.get("haystack_sessions", [])
        answer_ids = set(inst.get("answer_session_ids", []))
        gold = inst.get("answer")
        qtext = norm(inst.get("question", ""))

        # Render every session once.
        rendered: list[tuple[str, str]] = []
        for idx, sess in enumerate(sessions):
            body = "\n".join(
                turn_text(t, dates[idx] if idx < len(dates) else None) for t in sess
            )
            sid = ids[idx] if idx < len(ids) else f"#{idx}"
            rendered.append((sid, body))

        gold_bodies = [b for sid, b in rendered if sid in answer_ids]
        gold_text = norm("\n".join(gold_bodies))

        # Which probe terms appear in the gold at all?
        gold_hits = [p for p in probes if p in gold_text]
        # Which probe terms are question words (so a retriever would use them)?
        q_hits = [p for p in probes if p in qtext]
        # How many sessions echo the question's own terms, and is the gold among them?
        matching = [sid for sid, b in rendered if any(p in norm(b) for p in q_hits)]
        gold_in_matching = any(sid in answer_ids for sid in matching)

        print(
            f"| {qid} | {gold!r} | "
            f"{'YES (' + ', '.join(gold_hits) + ')' if gold_hits else 'NO'} | "
            f"{', '.join(q_hits) if q_hits else '-'} | "
            f"{len(matching)}{' (gold included)' if gold_in_matching else ' (GOLD ABSENT)'} |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
