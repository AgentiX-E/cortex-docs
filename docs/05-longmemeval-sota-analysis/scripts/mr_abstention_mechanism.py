"""Is the bare `UNANSWERABLE` signature a context-composition failure?

Nine MR questions emit a BARE abstention: the whole completion is the abstain
token, with no Step 1 and no Step 2. Those questions skip the prompt's contract
entirely, which is a different failure from "enumerated, then got it wrong".

Two candidate causes, both checkable on the artifacts:
  (a) the prompt's contract is unsatisfiable (a difference of years has no items
      to enumerate), which is the classifyAggregationKind leak; or
  (b) the answerable evidence is a small fraction of a large, noisy context, so
      the model never finds it and gives up.

This measures context size, session count, and evidence DENSITY against the
bare-abstention signature so the two can be told apart.

Usage: python3 mr_abstention_mechanism.py [root] [arm]
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")
ARM = sys.argv[2] if len(sys.argv) > 2 else "treatment"

TURN_PREFIX = re.compile(r"^\[\d{4}/\d{2}/\d{2}")
ABSTAIN = re.compile(r"^\s*(?:UNANSWERABLE|unanswerable)\s*[.\s]*$")


def fp(t: str, n: int = 80) -> str:
    return re.sub(r"\W+", "", str(t).lower())[:n]


def main() -> None:
    rows = []
    for d in sorted((ROOT / ARM).iterdir()):
        p = d / "benchmark-mr-diagnostics.json"
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x.get("decision") or {}
            retrieved = dec.get("retrieved", "") or ""
            raw = (dec.get("llmRaw", "") or "").strip()
            ev = x.get("answer_sessions_content") or []
            fpr = fp(retrieved, 10**9)
            found = sum(1 for c in ev if fp(c) and fp(c) in fpr)
            # A block only counts as a session when its first line carries a turn
            # prefix; blank lines inside a session must not split it.
            sessions = sum(
                1 for b in retrieved.split("\n\n") if b.strip() and TURN_PREFIX.match(b.strip())
            )
            ev_chars = sum(len(c or "") for c in ev if fp(c) and fp(c) in fpr)
            rows.append(
                {
                    "q": x["question"],
                    "gold": x["ground_truth"],
                    "abstained": bool(dec.get("abstained")),
                    "bare": bool(ABSTAIN.match(raw)),
                    "chars": len(retrieved),
                    "sessions": sessions,
                    "ev_total": len(ev),
                    "ev_found": found,
                    "ev_complete": len(ev) > 0 and found == len(ev),
                    # Share of the context that is evidence. Low density means the
                    # model has to find a few needles in a big haystack of sessions.
                    "ev_char_share": (ev_chars / len(retrieved)) if retrieved else 0.0,
                }
            )

    n = len(rows)
    bare = [r for r in rows if r["bare"]]
    reasoned = [r for r in rows if r["abstained"] and not r["bare"]]
    answered = [r for r in rows if not r["abstained"]]

    def med(rs, k):
        return statistics.median([r[k] for r in rs]) if rs else 0

    print(f"=== {ARM}: {n} MR question-runs ({n // 4} questions x 4 runs)\n")
    print(f"{'group':<28}{'n':>5}{'chars':>9}{'sessions':>10}{'ev_found':>10}{'ev_share':>10}")
    for name, grp in (
        ("bare UNANSWERABLE", bare),
        ("reasoned abstention", reasoned),
        ("answered", answered),
    ):
        print(
            f"{name:<28}{len(grp):>5}{med(grp, 'chars'):>9.0f}{med(grp, 'sessions'):>10}"
            f"{med(grp, 'ev_found'):>10}{med(grp, 'ev_char_share'):>10.1%}"
        )

    print("\n--- bare abstentions, per question (runs out of 4) ---")
    byq: dict[str, list[dict]] = {}
    for r in rows:
        byq.setdefault(r["q"], []).append(r)
    for q, rs in sorted(byq.items(), key=lambda kv: -sum(r["bare"] for r in kv[1])):
        nb = sum(r["bare"] for r in rs)
        if nb == 0:
            continue
        r = rs[0]
        print(
            f"  {nb}/4  chars={r['chars']:>6}  sess={r['sessions']:>3}  "
            f"ev={r['ev_found']}/{r['ev_total']}  share={r['ev_char_share']:>5.1%}  {q[:62]}"
        )

    print("\n--- is bare abstention explained by context size? ---")
    # Split at the median context length: if bare abstention concentrates in the
    # long half, context composition is implicated; if not, the prompt contract is.
    med_chars = med(rows, "chars")
    for label, sel in (
        (f"chars <= {med_chars:.0f}", [r for r in rows if r["chars"] <= med_chars]),
        (f"chars >  {med_chars:.0f}", [r for r in rows if r["chars"] > med_chars]),
    ):
        b = sum(1 for r in sel if r["bare"])
        print(f"  {label}: {b}/{len(sel)} bare ({b / len(sel):.1%})")

    med_share = med(rows, "ev_char_share")
    for label, sel in (
        (f"evidence share >= {med_share:.1%}", [r for r in rows if r["ev_char_share"] >= med_share]),
        (f"evidence share <  {med_share:.1%}", [r for r in rows if r["ev_char_share"] < med_share]),
    ):
        b = sum(1 for r in sel if r["bare"])
        print(f"  {label}: {b}/{len(sel)} bare ({b / len(sel):.1%})")


if __name__ == "__main__":
    main()
