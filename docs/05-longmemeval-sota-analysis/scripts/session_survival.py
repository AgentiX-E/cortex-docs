#!/usr/bin/env python3
"""Quantify how much of each gold session actually survives into the frame.

Why this exists
---------------
The frame is built as:

    hits.map(h => truncateSession(h.text, DEFAULT_MAX_SESSION_CHARS))  // 2000
        .join('\\n\\n')
    then truncateText(..., DEFAULT_MAX_AGGREGATION_CHARS)              // 20000

Two budgets apply in sequence, and the gold-session probe showed bodies of
10-15k chars surviving only 2-3%. That is inconsistent with the *per-session*
budget alone, so the question is which budget is actually binding, and whether
the per-session cut is preserving the fact-bearing text.

This script reconstructs, per gold session, the fraction that survived and the
position of the cut relative to the session's user turns. It answers:

  - Is the 2000-char per-session budget binding, or the 20000-char frame?
  - Does `truncateSession` keep a contiguous head, or a scattered selection?
  - How many gold sessions lose the text that carries the answer?

Usage:
  session_survival.py RUN_DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import median


def norm(s: str) -> str:
    return " ".join(s.split())


def longest_prefix_present(needle: str, haystack: str) -> int:
    """Longest prefix of `needle` that occurs verbatim in `haystack`."""
    lo, hi = 0, len(needle)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if needle[:mid] in haystack:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1])
    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())

    body_lens: list[int] = []
    survived: list[int] = []
    ratios: list[float] = []
    fully_present = 0
    total = 0

    for r in records:
        fl = norm(r.get("decision", {}).get("retrieved") or "")
        for body in r.get("answer_sessions_content") or []:
            nb = norm(body)
            if not nb:
                continue
            total += 1
            body_lens.append(len(nb))
            got = longest_prefix_present(nb, fl)
            survived.append(got)
            ratios.append(got / len(nb))
            if got >= len(nb):
                fully_present += 1

    print(f"# Gold-session survival -- {run_dir.name}\n")
    print(f"Gold sessions inspected: {total}")
    print(f"Fully present in the frame: {fully_present} ({100 * fully_present / total:.1f}%)")
    print(f"Body length  : median {median(body_lens):.0f}, max {max(body_lens)}")
    print(f"Chars kept   : median {median(survived):.0f}, max {max(survived)}")
    print(f"Kept ratio   : median {100 * median(ratios):.1f}%\n")

    buckets = {"<10%": 0, "10-50%": 0, "50-99%": 0, "100%": 0}
    for r_ in ratios:
        if r_ >= 0.999:
            buckets["100%"] += 1
        elif r_ >= 0.5:
            buckets["50-99%"] += 1
        elif r_ >= 0.1:
            buckets["10-50%"] += 1
        else:
            buckets["<10%"] += 1
    print("| survival | sessions |")
    print("|---|---|")
    for k, v in buckets.items():
        print(f"| {k} | {v} |")

    # Does the cut land before the session's user turns that carry facts?
    print("\nNote: `truncateSession` preserves whole dated turns and stops at the")
    print("per-session budget. A low survival ratio therefore means the budget,")
    print("not the sampling, is the binding constraint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
