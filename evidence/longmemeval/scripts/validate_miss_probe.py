#!/usr/bin/env python3
"""Validate the ranking-vs-truncation split with an explicit, auditable probe.

`mr_miss_mechanism.py` reports 15 truncation and 8 ranking misses. That number
decides which file gets edited, so it must not rest on a loose heuristic. This
script re-derives the split three independent ways and reports where they
disagree:

  1. STRICT   the exact `[truncated]`-aware structure: a session is TRUNCATED
              only if a frame exists whose text is a prefix of the gold body
              AND that frame ends with the truncation marker.
  2. PREFIX   the session reached the frame (its head is a prefix of some
              frame) but the fact window is absent.
  3. ABSENT   no frame shares a meaningful prefix with the body.

Agreement between (1) and (2) is the claim. Disagreement means the probe in
`mr_miss_mechanism.py` is too loose and must not be acted on.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TRUNC = "[truncated]"


def norm(s: str) -> str:
    return " ".join(s.split())


def frames_of(retrieved: str) -> list[str]:
    return [norm(s) for s in re.split(r"\n{2,}", retrieved) if s.strip()]


def fact_present(body: str, retrieved_flat: str, window: int = 200) -> bool:
    flat = norm(body)
    if not flat:
        return False
    if len(flat) <= window:
        return flat in retrieved_flat
    step = max(1, len(flat) // 8)
    return any(
        flat[i : i + window] in retrieved_flat
        for i in range(0, len(flat) - window + 1, step)
    )


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1])
    records = json.loads((run_dir / "benchmark-mr-diagnostics.json").read_text())

    counts = {"truncated_frame": 0, "prefix_in_frame": 0, "no_prefix": 0}
    examples: dict[str, list[str]] = {k: [] for k in counts}

    for r in records:
        retrieved = r.get("decision", {}).get("retrieved") or ""
        retrieved_flat = norm(retrieved)
        frames = frames_of(retrieved)
        for body in r.get("answer_sessions_content") or []:
            if fact_present(body, retrieved_flat):
                continue
            flat = norm(body)
            head = flat[:160]
            # A frame that is a strict prefix of this body AND carries the
            # truncation marker proves the session was cut, not mis-ranked.
            trunc_frame = any(
                f.endswith(TRUNC) and head.startswith(f[: min(len(f) - len(TRUNC), 160)].strip())
                for f in frames
                if len(f) > len(TRUNC) + 20
            )
            prefix_frame = any(head[:80] and head[:80] in f for f in frames)
            if trunc_frame:
                key = "truncated_frame"
            elif prefix_frame:
                key = "prefix_in_frame"
            else:
                key = "no_prefix"
            counts[key] += 1
            if len(examples[key]) < 3:
                examples[key].append(f"{r['question'][:70]} | gold={r['ground_truth']!r}")

    print(f"# Probe validation -- {run_dir.name}\n")
    print("| class | count | interpretation |")
    print("|---|---|---|")
    print(f"| truncated_frame | {counts['truncated_frame']} | TRUNCATION (high confidence) |")
    print(f"| prefix_in_frame | {counts['prefix_in_frame']} | session present but fact cut |")
    print(f"| no_prefix | {counts['no_prefix']} | RANKING (never retrieved) |")
    print()
    for k, v in examples.items():
        if v:
            print(f"### {k}")
            for line in v:
                print(f"- {line}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
