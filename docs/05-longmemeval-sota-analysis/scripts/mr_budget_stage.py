#!/usr/bin/env python3
"""Locate the exact pipeline stage at which the needle sentence is lost.

`p10-mr-stability.md` isolated 4-5 questions that deterministically abstain
across all 8 runs. Two candidate mechanisms were named:

  A. `truncateSession(h.text, maxSessionChars)` drops the user turn holding the
     needle (the `c3a52ee` family).
  B. `truncateText(joined, maxAggregationChars)` clips the tail of the joined
     sessions after each individual session was truncated safely.

These are different budgets and demand different fixes, so the distinction has
to be measured, not assumed. This script replays both stages exactly and, for
each needle phrase present in a gold session, reports the first stage at which
it disappears.

Usage:
  mr_budget_stage.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TURN_BOUNDARY = re.compile(r"(?=\[\d{4}/\d{2}/\d{2}[^\]]*\] )")
ASSISTANT_HEAD_CHARS = 200
MAX_SESSION_CHARS = 2000
MAX_AGGREGATION_CHARS = 20_000

# The 13-question deterministic failure set from p10-mr-stability.md, with the
# needle each question needs. Needles are derived from the gold answer plus the
# answer-session content, and are matched case-insensitively after whitespace
# normalisation.
ABSTAIN_SET: dict[str, list[str]] = {
    "37f165cf": ["3 sisters", "a brother"],
    "8e91e7d9": ["3 sisters", "a brother"],
    "10d9b85a": ["3 sisters", "a brother"],
    "0a995998": [],
    "b5ef892d": [],
}


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def truncate_session(text: str, max_chars: int) -> str:
    """Port of the current TypeScript `truncateSession`."""
    if len(text) <= max_chars:
        return text
    turns = [t for t in TURN_BOUNDARY.split(text) if t]
    user_chars = [len(t) if re.search(r"\] user:", t) else 0 for t in turns]

    keep = [False] * len(turns)
    reserved = 0
    for i, ln in enumerate(user_chars):
        if ln > 0 and reserved + ln <= max_chars:
            keep[i] = True
            reserved += ln
    if not any(keep):
        return truncate_text(text, max_chars)

    suffix = [0] * (len(turns) + 1)
    for i in range(len(turns) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + (user_chars[i] if keep[i] else 0)

    kept: list[str] = []
    used = 0
    truncated = False
    for i, turn in enumerate(turns):
        if user_chars[i] > 0:
            if keep[i]:
                kept.append(turn)
                used += len(turn)
            else:
                truncated = True
            continue
        head = turn[:ASSISTANT_HEAD_CHARS]
        if len(head) < len(turn):
            truncated = True
        if used + len(head) + suffix[i + 1] <= max_chars:
            kept.append(head)
            used += len(head)
        else:
            truncated = True
    out = "".join(kept)
    return out + "\n[truncated]" if truncated else out


def main(argv: list[str]) -> int:
    run_dirs = [Path(a) for a in argv[1:]]
    if not run_dirs:
        print(__doc__)
        return 2

    # Aggregate across runs: a needle's stage should be identical every run if
    # the pipeline is deterministic; disagreement is itself a finding.
    verdicts: dict[str, dict[str, set[str]]] = {}

    for run_dir in run_dirs:
        path = run_dir / "benchmark-mr-diagnostics.json"
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        records = json.loads(path.read_text())
        by_id = {r["question_id"]: r for r in records}

        for qid, needles in ABSTAIN_SET.items():
            r = by_id.get(qid)
            if r is None or not needles:
                continue
            bodies = [b for b in (r.get("answer_sessions_content") or []) if b]
            prompt = norm(r["decision"]["retrieved"])
            per_q = verdicts.setdefault(qid, {})

            for needle in needles:
                n = norm(needle)
                stage = "MISSING_FROM_GOLD"
                if any(n in norm(b) for b in bodies):
                    stage = "LOST_IN_TRUNCATE_SESSION"
                    session_texts = [truncate_session(b, MAX_SESSION_CHARS) for b in bodies]
                    if any(n in norm(s) for s in session_texts):
                        stage = "LOST_IN_AGGREGATION_CLIP"
                        joined = "\n\n".join(session_texts)
                        if n in norm(truncate_text(joined, MAX_AGGREGATION_CHARS)):
                            stage = "PRESENT_IN_PROMPT"
                            if n in prompt:
                                stage = "PRESENT_IN_LOGGED_PROMPT"
                per_q.setdefault(needle, set()).add(stage)

    print("# Needle-loss stage by question\n")
    print("| question | needle | stage (across runs) |")
    print("|---|---|---|")
    for qid in ABSTAIN_SET:
        if qid not in verdicts:
            continue
        for needle, stages in verdicts[qid].items():
            print(f"| {qid} | `{needle}` | {' / '.join(sorted(stages))} |")

    print()
    print("## Prompt budget by abstaining question\n")
    print("| question | retrieved chars | sessions | joined chars | joined > clip? |")
    print("|---|---|---|---|---|")
    for run_dir in run_dirs:
        path = run_dir / "benchmark-mr-diagnostics.json"
        if not path.exists():
            continue
        records = json.loads(path.read_text())
        by_id = {r["question_id"]: r for r in records}
        for qid in ABSTAIN_SET:
            r = by_id.get(qid)
            if r is None:
                continue
            bodies = [b for b in (r.get("answer_sessions_content") or []) if b]
            session_texts = [truncate_session(b, MAX_SESSION_CHARS) for b in bodies]
            joined = "\n\n".join(session_texts)
            print(
                f"| {qid} | {len(r['decision']['retrieved'])} | {len(bodies)} | "
                f"{len(joined)} | {'YES' if len(joined) > MAX_AGGREGATION_CHARS else 'no'} |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
