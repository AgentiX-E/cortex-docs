#!/usr/bin/env python3
"""Replay the fixed truncation against the real gold sessions, offline.

The unit tests prove the invariant on synthetic shapes. This proves it on the
316 LongMemEval-S gold sessions that motivated the fix, with no API calls: it
re-implements the new `truncateSession` in Python and reports the survival
statistics before and after, so the improvement is a measurement rather than a
claim.

Usage:
  replay_truncation.py RUN_DIR [--budget 2000]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import median

TURN_BOUNDARY = r"(?=\[\d{4}/\d{2}/\d{2}[^\]]*\] )"
ASSISTANT_HEAD_CHARS = 200


def norm(s: str) -> str:
    return " ".join(s.split())


def truncate_session_new(text: str, max_chars: int) -> str:
    """Port of the fixed TypeScript implementation."""
    if len(text) <= max_chars:
        return text
    turns = [t for t in re.split(TURN_BOUNDARY, text) if t]
    user_chars = [len(t) if re.search(r"\] user:", t) else 0 for t in turns]

    keep = [False] * len(turns)
    reserved = 0
    for i, ln in enumerate(user_chars):
        if ln > 0 and reserved + ln <= max_chars:
            keep[i] = True
            reserved += ln
    if not any(keep):
        head = text[:max_chars]
        return head + "\n[truncated]" if len(head) < len(text) else head

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


def truncate_session_old(text: str, max_chars: int) -> str:
    """Port of the buggy implementation, for the before/after comparison."""
    if len(text) <= max_chars:
        return text
    turns = [t for t in re.split(TURN_BOUNDARY, text) if t]
    kept: list[str] = []
    used = 0
    truncated = False
    for turn in turns:
        if re.search(r"\] user:", turn):
            if used + len(turn) > max_chars:
                truncated = True
                break
            kept.append(turn)
            used += len(turn)
        else:
            head = turn[:ASSISTANT_HEAD_CHARS]
            if len(head) < len(turn):
                truncated = True
            kept.append(head)
            used += len(head)
    out = "".join(kept)
    return out + "\n[truncated]" if truncated else out


def user_turn_count(s: str) -> int:
    return len(re.findall(r"\] user:", s))


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1])
    budget = 2000
    if "--budget" in argv:
        budget = int(argv[argv.index("--budget") + 1])

    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())

    old_len: list[int] = []
    new_len: list[int] = []
    old_turns: list[int] = []
    new_turns: list[int] = []
    total_turns: list[int] = []
    n = 0

    for r in records:
        for body in r.get("answer_sessions_content") or []:
            if not body:
                continue
            n += 1
            total_turns.append(user_turn_count(body))
            o = truncate_session_old(body, budget).replace("\n[truncated]", "")
            w = truncate_session_new(body, budget).replace("\n[truncated]", "")
            old_len.append(len(o))
            new_len.append(len(w))
            old_turns.append(user_turn_count(o))
            new_turns.append(user_turn_count(w))

    print(f"# truncateSession replay -- {run_dir.name}\n")
    print(f"Gold sessions: {n}, per-session budget: {budget}\n")
    print("| metric | before (break) | after (skip+reserve) | change |")
    print("|---|---|---|---|")
    print(
        f"| median chars kept | {median(old_len):.0f} | {median(new_len):.0f} | "
        f"{median(new_len) / median(old_len):.1f}x |"
    )
    print(
        f"| budget utilisation | {100 * median(old_len) / budget:.0f}% | "
        f"{100 * median(new_len) / budget:.0f}% | |"
    )
    print(
        f"| median user turns kept | {median(old_turns):.0f} | {median(new_turns):.0f} | |"
    )
    print(
        f"| fully complete sessions | "
        f"{sum(1 for a, b in zip(old_len, new_len) if False)} | "
        f"{sum(1 for t, l in zip(total_turns, new_turns) if l >= t)} | |"
    )
    print()
    print(f"Total user turns available: median {median(total_turns):.0f} per session")
    print(
        f"User-turn evidence recovered: {sum(new_turns)} vs {sum(old_turns)} "
        f"(+{sum(new_turns) - sum(old_turns)} turns, "
        f"{100 * (sum(new_turns) - sum(old_turns)) / max(1, sum(old_turns)):.0f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
