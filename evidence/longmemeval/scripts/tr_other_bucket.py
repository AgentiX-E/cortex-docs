"""Print the TR questions the deterministic engine does not handle.

`other` and `eventLookup` are the two kinds the engine deliberately hands back to
a prompt, and together they hold 10 of the 22 TR errors while covering only 36 of
127 questions. This lists them with their gold answers so the taxonomy can be
checked by hand: a question sitting in `other` that actually needs date
arithmetic is a classifier leak, not a hard question.

Usage: python3 tr_other_bucket.py [root] [arm] [kind...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/analysis/ab_turn")
ARM = sys.argv[2] if len(sys.argv) > 2 else "treatment"
KINDS = sys.argv[3:] or ["other", "eventLookup"]

d = json.loads((ROOT / f"tr_census_{ARM}.json").read_text())
qs = [q for q in d["questions"] if q["kind"] in KINDS]
print(f"=== {ARM}: {len(qs)} TR questions of kind {', '.join(KINDS)}\n")
for q in qs:
    print("-" * 100)
    print(f"[{q['kind']}] {q['question']}")
    print(f"    qdate   = {q['questionDate']}")
    print(f"    gold    = {str(q['gold'])[:90]}")
    print(f"    answers = {q['answers']}")
