"""Is MR accuracy limited by how much of the aggregation context is noise?

The turn-recall A/B proved retrieval is nearly solved: 97.2% of evidence sessions
reach the context, and 21 of the 22 wrong numeric answers have COMPLETE evidence.
So the remaining errors happen with the evidence already in hand, which points at
the context the model has to read it from: 13-16 sessions, ~16k characters, of
which only 2-5 sessions are evidence.

If accuracy falls as the DISTRACTOR load rises (at equal evidence recall), the
bottleneck is context composition, and the next fix is to construct the
aggregation context from the most relevant TURNS instead of whole sessions.
If it does not, context composition is already good enough and the leak is in
the aggregation reasoning itself.

Usage: python3 mr_distractor_load.py [root] [arm]
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")
ARM = sys.argv[2] if len(sys.argv) > 2 else "treatment"

TURN_PREFIX = re.compile(r"^\[\d{4}/\d{2}/\d{2}")
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
COUNTING_Q = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)


def fp(t: str, n: int = 80) -> str:
    return re.sub(r"\W+", "", str(t).lower())[:n]


def norm(v) -> str:
    return re.sub(r"\s+", "", str(v).strip().lower())


def lead(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def correct(q, answer, gold) -> bool | None:
    if answer is None:
        return False
    if norm(answer) == norm(gold):
        return True
    if COUNTING_Q.search(q):
        p, e = lead(answer), lead(gold)
        if p is not None and e is not None:
            return p == e
    return None


def main() -> None:
    per: dict[str, list[dict]] = {}
    for d in sorted((ROOT / ARM).iterdir()):
        p = d / "benchmark-mr-diagnostics.json"
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x.get("decision") or {}
            retrieved = dec.get("retrieved", "") or ""
            ev = x.get("answer_sessions_content") or []
            fpr = fp(retrieved, 10**9)
            found = sum(1 for c in ev if fp(c) and fp(c) in fpr)
            sessions = sum(
                1 for b in retrieved.split("\n\n") if b.strip() and TURN_PREFIX.match(b.strip())
            )
            ev_chars = sum(min(len(c or ""), 2000) for c in ev if fp(c) and fp(c) in fpr)
            per.setdefault(x["question_id"], []).append(
                {
                    "q": x["question"],
                    "gold": x["ground_truth"],
                    "answer": dec.get("answer"),
                    "abstained": bool(dec.get("abstained")),
                    "chars": len(retrieved),
                    "sessions": sessions,
                    "ev_total": len(ev),
                    "ev_found": found,
                    # Distractors = sessions present minus the evidence among them.
                    "distractors": max(0, sessions - found),
                    # Evidence share is bounded by the per-session 2000-char cap
                    # that `truncateSession` applies, so it stays within [0, 1].
                    "ev_share": min(1.0, ev_chars / len(retrieved)) if retrieved else 0.0,
                }
            )

    rows = []
    for qid, rs in per.items():
        r = rs[0]
        modal = Counter(str(x["answer"]) for x in rs).most_common(1)[0][0]
        verdicts = [correct(r["q"], x["answer"], r["gold"]) for x in rs]
        ok = True if all(v is True for v in verdicts) else (
            False if all(v is False for v in verdicts) else None
        )
        rows.append({**r, "modal_ok": ok, "answer": modal})

    # Restrict to questions where retrieval succeeded: only there can context
    # composition be the reason the answer is still wrong.
    complete = [r for r in rows if r["ev_found"] == r["ev_total"] and r["ev_total"] > 0]
    decided = [r for r in complete if r["modal_ok"] is not None]
    ok_rows = [r for r in decided if r["modal_ok"]]
    bad_rows = [r for r in decided if not r["modal_ok"]]

    print(f"=== {ARM}: {len(rows)} MR questions, "
          f"{len(complete)} with complete evidence, {len(decided)} offline-decidable\n")
    print(f"{'group':<26}{'n':>5}{'chars':>9}{'sessions':>10}{'distract':>10}{'ev_share':>10}")
    for name, grp in (("correct (all 4 runs)", ok_rows), ("wrong (all 4 runs)", bad_rows)):
        med = lambda k: statistics.median([r[k] for r in grp]) if grp else 0
        print(f"{name:<26}{len(grp):>5}{med('chars'):>9.0f}{med('sessions'):>10}"
              f"{med('distractors'):>10}{med('ev_share'):>10.1%}")

    for key, label in (("distractors", "distractor sessions"), ("ev_share", "evidence share")):
        vals = sorted(r[key] for r in decided)
        cut = statistics.median(vals)
        lo = [r for r in decided if r[key] <= cut]
        hi = [r for r in decided if r[key] > cut]
        print(f"\n--- accuracy vs {label} (split at median {cut:.2f}) ---")
        for name, grp in ((f"<= {cut:.2f}", lo), (f">  {cut:.2f}", hi)):
            if not grp:
                continue
            acc = sum(1 for r in grp if r["modal_ok"]) / len(grp)
            print(f"  {label} {name:<12} n={len(grp):>3}  accuracy={acc:.1%}")

    print("\n--- abstentions among complete-evidence questions, by distractor load ---")
    ab = [r for r in complete if r["abstained"]]
    an = [r for r in complete if not r["abstained"]]
    med = lambda g, k: statistics.median([r[k] for r in g]) if g else 0
    print(f"  abstained n={len(ab):>3}  distractors={med(ab,'distractors'):.0f}  "
          f"chars={med(ab,'chars'):.0f}  ev_share={med(ab,'ev_share'):.1%}")
    print(f"  answered  n={len(an):>3}  distractors={med(an,'distractors'):.0f}  "
          f"chars={med(an,'chars'):.0f}  ev_share={med(an,'ev_share'):.1%}")


if __name__ == "__main__":
    main()
