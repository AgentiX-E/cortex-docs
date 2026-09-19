#!/usr/bin/env python3
"""Replay the lexical-variant widening over the frozen MR case, offline.

The unit test proves the mechanism on synthetic geometry. This proves it on the
real `8e91e7d9` case: it re-implements `expandLexicalVariants`'s table and checks
whether the evidence sessions become reachable by the query vocabulary the engine
actually issues.

This is an offline proxy for the retrieval assertion, not a substitute for it.
Without an embedding key it cannot rank sessions, so it measures the necessary
precondition — that the query set now contains a word the evidence contains.
A retrieval change that fails this cannot work regardless of its geometry.

Usage:
  replay_lexical_variants.py [--data PATH]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DEFAULT = Path("/tmp/lme-data/lme.json")

# Mirror of LEXICAL_VARIANTS in natural-language-memory.ts.
LEXICAL_VARIANTS: list[tuple[str, list[str]]] = [
    (r"\bsiblings?\b|\bsisters?\b|\bbrothers?\b", ["sister", "brother"]),
    (r"\bparents?\b|\bmothers?\b|\bfathers?\b|\bmoms?\b|\bdads?\b", ["mother", "father", "mom", "dad"]),
    (
        r"\bgrandparents?\b|\bgrandmothers?\b|\bgrandfathers?\b|\bgrandmas?\b|\bgrandpas?\b",
        ["grandmother", "grandfather", "grandma", "grandpa"],
    ),
    (r"\bspouses?\b|\bhusbands?\b|\bwives\b|\bwife\b", ["husband", "wife"]),
    (r"\bchildren\b|\bkids?\b|\bsons?\b|\bdaughters?\b", ["son", "daughter"]),
]


def expand_lexical_variants(question: str) -> list[str]:
    """Port of the TypeScript implementation, including the de-duplication rule."""
    variants: list[str] = []
    seen: set[str] = set()
    for pattern, terms in LEXICAL_VARIANTS:
        if not re.search(pattern, question, re.I):
            continue
        for term in terms:
            already_present = re.search(rf"\b{term}(?:s|es)?\b", question, re.I)
            if already_present or term in seen:
                continue
            seen.add(term)
            variants.append(term)
    return variants


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DATA_DEFAULT)
    ap.add_argument("--runs-glob", default="ab_rrf/run_*/longmemeval-s-report")
    args = ap.parse_args()

    if not args.data.exists() or args.data.stat().st_size == 0:
        print(f"dataset unavailable: {args.data}")
        return 2

    instances = {i["question_id"]: i for i in json.loads(args.data.read_text())}
    records = sorted(Path(".").glob(args.runs_glob))
    if not records:
        print(f"no runs matched {args.runs_glob}")
        return 2

    first = json.loads((records[0] / "benchmark-mr-diagnostics.json").read_text())
    by_id = {r["question_id"]: r for r in first}
    r = by_id["8e91e7d9"]
    question = r["question"]
    inst = instances["8e91e7d9"]

    print("# query vocabulary audit -- 8e91e7d9\n")
    print(f"Q: {question}")

    pre_fix = r["decision"].get("expansionQueries") or []
    variants = expand_lexical_variants(question)
    post_fix = list(pre_fix) + variants

    gold_ids = set(inst.get("answer_session_ids", []))
    ids = inst["haystack_session_ids"]
    gold_bodies: list[str] = []
    for aid in gold_ids:
        idx = ids.index(aid)
        gold_bodies.append(
            "\n".join(t["content"] for t in inst["haystack_sessions"][idx]).lower()
        )

    print(f"\nLLM expansion queries (pre-fix): {pre_fix}")
    print(f"lexical variants added:          {variants}")
    print(f"query set (post-fix):            {post_fix}\n")

    print("| gold session | distinguishing word | reachable pre-fix | reachable post-fix |")
    print("|---|---|---|---|")
    # The proxy must test the CLAIM, not mere token overlap. Generic content words
    # ("list", "count") appear in almost any session, so matching on them would
    # report "reachable" for a query the retriever already had — which is exactly
    # the false positive this analysis exists to rule out. Instead each gold
    # session is probed for the word that identifies it: the relative noun.
    DISTINCTIVE = {
        "answer_477ae455_1": "sister",
        "answer_477ae455_2": "brother",
    }
    for aid in sorted(gold_ids):
        idx = ids.index(aid)
        body = "\n".join(t["content"] for t in inst["haystack_sessions"][idx]).lower()
        word = DISTINCTIVE.get(aid, "")

        def reachable(queries: list[str], needle: str) -> str:
            if not needle:
                return "n/a"
            # Reachability = some issued query CONTAINS the distinguishing word.
            # This is the lexical precondition for the session to score on it.
            return "YES" if any(needle in q.lower() for q in queries) else "**NO**"

        present = "yes" if word and word in body else (f"**ABSENT**" if word else "n/a")
        print(
            f"| {aid} | `{word}` ({present}) | {reachable(pre_fix, word)} | "
            f"{reachable(post_fix, word)} |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
