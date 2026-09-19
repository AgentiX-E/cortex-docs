#!/usr/bin/env python3
"""MR attribution, corrected to compare like with like.

Why this supersedes `mr_attribution.py`
---------------------------------------
`answerSessions` strips assistant turns from every session BEFORE retrieval and
truncation:

    const factSessions = sessions.map(s => s.filter(t => !isAssistantTurn(t)));

The diagnostics' `answer_sessions_content`, however, stores the UNFILTERED body.
Matching a full body against the rendered frame therefore breaks at the first
assistant turn, which made earlier runs of this analysis report a ~2% survival
rate that was an artifact of the comparison, not a property of the pipeline.

This script filters assistant turns out of the gold body first, so both sides of
the comparison are in the same form as what the model actually receives.

Usage:
  mr_attribution_v2.py RUN_DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TURN_BOUNDARY = r"(?=\[\d{4}/\d{2}/\d{2}[^\]]*\] )"
ASSISTANT_TURN = re.compile(r"(?:^|\]\s*)assistant:")


def norm(s: str) -> str:
    return " ".join(s.split())


def user_only(body: str) -> str:
    """Mirror `answerSessions`: drop assistant turns, keep the rest."""
    turns = [t for t in re.split(TURN_BOUNDARY, body) if t]
    return "".join(t for t in turns if not ASSISTANT_TURN.search(t))


def fact_present(body: str, frame: str, window: int = 150) -> bool:
    """True when a fact-bearing window of the (user-only) body is in the frame."""
    flat = norm(user_only(body))
    if not flat:
        return False
    if len(flat) <= window:
        return flat in frame
    step = max(1, len(flat) // 8)
    return any(flat[i : i + window] in frame for i in range(0, len(flat) - window + 1, step))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    run_dir = Path(argv[1])
    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())

    present, missing = [], []
    for r in records:
        frame = norm(r.get("decision", {}).get("retrieved") or "")
        bodies = r.get("answer_sessions_content") or []
        if not bodies:
            continue
        miss = [b for b in bodies if not fact_present(b, frame)]
        (missing if miss else present).append((r, len(miss)))

    total = len(present) + len(missing)
    correct = sum(1 for r in records if r["correct"])
    print(f"# MR attribution (corrected) -- {run_dir.name}\n")
    print(f"Instances: {total}, correct: {correct} ({100 * correct / total:.1f}%)\n")
    print("| evidence state | n | correct | accuracy |")
    print("|---|---|---|---|")
    for label, rows in (("PRESENT", present), ("MISSING", missing)):
        if not rows:
            continue
        n = len(rows)
        c = sum(1 for r, _ in rows if r["correct"])
        print(f"| {label} | {n} | {c} | {100 * c / n:.1f}% |")

    errs = total - correct
    m_err = sum(1 for r, _ in missing if not r["correct"])
    print(f"\nErrors: {errs}. With >=1 gold session absent: {m_err}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
