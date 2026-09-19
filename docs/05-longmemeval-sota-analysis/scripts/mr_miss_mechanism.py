#!/usr/bin/env python3
"""Separate the two mechanisms behind an MR retrieval miss.

Why this exists
---------------
`mr_attribution.py` shows that 22 of 121 MR instances are handed an incomplete
evidence set, and that this costs ~0.099 accuracy. But two very different
mechanisms produce that state, and they are fixed in different places:

  RANKING    the gold session never made the top-k, so the frame never had it.
             Remedy: ranking (query expansion, hybrid lexical recall, scoring).
  TRUNCATION the gold session DID make the frame but its body was cut short
             before the sentence carrying the fact, so the fact is absent even
             though the session is "there".
             Remedy: per-session budget / adaptive allocation.

The diagnostics record the rendered `retrieved` text, which contains both the
`[truncated]` marker and every rendered session body. A gold session that
appears with a `[truncated]` marker and whose fact-bearing window is absent is a
TRUNCATION miss; one that does not appear at all is a RANKING miss.

This distinction is the whole point of the script: the two remedies are in
different files, and applying the wrong one wastes a benchmark run.

Usage:
  mr_miss_mechanism.py RUN_DIR [--window 200]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TRUNC_MARKER = "[truncated]"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _windows(text: str, window: int) -> list[str]:
    flat = _norm(text)
    if len(flat) <= window:
        return [flat] if flat else []
    step = max(1, len(flat) // 8)
    return [flat[i : i + window] for i in range(0, len(flat) - window + 1, step)]


def _split_sessions(retrieved: str) -> list[str]:
    """Split the rendered frame back into session bodies.

    Sessions are joined with a blank line and each begins with a dated turn.
    """
    return [s for s in re.split(r"\n{2,}", retrieved) if s.strip()]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    run_dir = Path(argv[1])
    window = 200
    if "--window" in argv:
        window = int(argv[argv.index("--window") + 1])

    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())

    tally = {"PRESENT": 0, "RANKING": 0, "TRUNCATION": 0}
    details: dict[str, list[tuple]] = {"RANKING": [], "TRUNCATION": []}

    for r in records:
        retrieved = r.get("decision", {}).get("retrieved") or ""
        frames = _split_sessions(retrieved)
        frames_flat = _norm(retrieved)
        missing_any = False
        for body in r.get("answer_sessions_content") or []:
            probes = _windows(body, window)
            if any(p and p in frames_flat for p in probes):
                continue  # fact-bearing text is present
            missing_any = True
            # Did the session make the frame at all? Approximate by finding a
            # leading fragment of the body inside any frame.
            head = _norm(body)[:window]
            in_frame = any(head and head[:80] in _norm(f) for f in frames) if head else False
            key = "TRUNCATION" if in_frame else "RANKING"
            tally[key] += 1
            details[key].append((r, body))
        if not missing_any:
            tally["PRESENT"] += 1

    n = len(records)
    correct = sum(1 for r in records if r["correct"])
    print(f"# MR miss mechanism -- {run_dir.name}\n")
    print(f"Instances: {n}, correct: {correct} ({100 * correct / n:.1f}%)\n")
    print("| mechanism | gold-session misses |")
    print("|---|---|")
    for k in ("PRESENT", "RANKING", "TRUNCATION"):
        print(f"| {k} | {tally[k]} |")
    print()
    miss = tally["RANKING"] + tally["TRUNCATION"]
    if miss:
        print(
            f"Of {miss} missing gold sessions: {tally['RANKING']} ranking "
            f"({100 * tally['RANKING'] / miss:.0f}%), {tally['TRUNCATION']} truncation "
            f"({100 * tally['TRUNCATION'] / miss:.0f}%)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
