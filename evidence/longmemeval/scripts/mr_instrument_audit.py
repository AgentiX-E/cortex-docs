#!/usr/bin/env python3
"""Measure how often the MR diagnostic instrument can see the answer evidence.

`benchmark-mr-diagnostics.json` records `answer_sessions_content` (the gold
sessions only) but the `decision.retrieved` field is the prompt the engine
actually built from the FULL `haystack_sessions` (~48 sessions per instance).
Every earlier MR analysis — including the stage attribution in
`p10-mr-stability.md` — compared gold evidence against a prompt the engine may
never have had access to, because it read `answer_sessions_content` as if it
were the retrieval input.

This script quantifies the gap: for each MR question it checks whether the
prompt contains evidence from a gold session at all, and reports the
distribution so any future MR claim can state whether it rests on the gold
sessions or on incidentally-retrieved ones.

Usage:
  mr_instrument_audit.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def coverage(body: str, prompt: str) -> float:
    """Fraction of a gold session's 60-char shingles present in the prompt."""
    n = norm(body)
    if len(n) < 60:
        return 1.0 if n and n in norm(prompt) else 0.0
    shingles = [n[i : i + 60] for i in range(0, len(n) - 60, 60)]
    if not shingles:
        return 0.0
    p = norm(prompt)
    return sum(1 for s in shingles if s in p) / len(shingles)


def main(argv: list[str]) -> int:
    run_dirs = [Path(a) for a in argv[1:]]
    if not run_dirs:
        print(__doc__)
        return 2

    for run_dir in run_dirs:
        path = run_dir / "benchmark-mr-diagnostics.json"
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        records = json.loads(path.read_text())

        buckets = {"none": 0, "partial": 0, "full": 0}
        abstain_buckets = {"none": 0, "partial": 0, "full": 0}
        worst: list[tuple[float, str]] = []

        for r in records:
            d = r.get("decision") or {}
            prompt = d.get("retrieved") or ""
            bodies = [b for b in (r.get("answer_sessions_content") or []) if b]
            if not bodies:
                continue
            covs = [coverage(b, prompt) for b in bodies]
            best = max(covs)
            label = "full" if best >= 0.99 else ("partial" if best > 0 else "none")
            buckets[label] += 1
            if d.get("abstained"):
                abstain_buckets[label] += 1
            worst.append((best, r["question_id"]))

        n = sum(buckets.values())
        print(f"# MR diagnostic instrument audit -- {run_dir.parent.name}\n")
        print(f"MR questions with gold evidence: {n}\n")
        print("| gold-session coverage in logged prompt | questions | share |")
        print("|---|---|---|")
        for k in ("none", "partial", "full"):
            print(f"| {k} | {buckets[k]} | {100 * buckets[k] / max(1, n):.1f}% |")
        print()
        print("## Restricted to abstained questions\n")
        na = sum(abstain_buckets.values())
        print(f"abstained: {na}\n")
        print("| coverage | questions | share |")
        print("|---|---|---|")
        for k in ("none", "partial", "full"):
            print(
                f"| {k} | {abstain_buckets[k]} | "
                f"{100 * abstain_buckets[k] / max(1, na):.1f}% |"
            )
        print()
        worst.sort()
        print("## Lowest coverage (3):\n")
        for cov, qid in worst[:3]:
            print(f"- {qid}: {100 * cov:.0f}%")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
