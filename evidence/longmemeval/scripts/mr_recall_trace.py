#!/usr/bin/env python3
"""Trace the retrieval stage that loses the gold evidence session.

`mr_instrument_audit.py` established that for the 13 deterministic MR failures
the logged prompt contains the gold session only `PARTIAL`ly, and in one case
(`8e91e7d9`) not at all — the engine retrieved two unrelated sessions and the
full mixed-session prompt never mentions the needle. That reframes the failure
from "the model abstained despite good evidence" to "the evidence was never
retrieved", which is a recall problem the abstention gate cannot fix.

This script checks the recall hypothesis directly: for each deterministic
failure, is the gold session's date present among the dates the engine actually
retrieved? A missing gold date means `retrieveSessionsForQuestion` (centroid +
expansion + turn recall) failed to surface the evidence, and the fix belongs in
retrieval, not in the prompt or the abstention gate.

Usage:
  mr_recall_trace.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# The deterministically-wrong questions this script was pointed at, copied from
# `p10-mr-stability.md`. Verified against `/tmp/lme-data/lme.json`: every id here
# is `question_type: multi-session`, which is what puts it in the MR diagnostics
# file at all. An earlier revision of this list carried TR/KU ids that never
# belonged to the set.
DETERMINISTIC = [
    "0a995998",
    "10d9b85a",
    "129d1232",
    "1a8a66a6",
    "37f165cf",
    "3fdac837",
    "73d42213",
    "8cf4d046",
    "8e91e7d9",
    "9ee3ecd6",
    "bf659f65",
    "gpt4_372c3eed",
    "gpt4_731e37d7",
]

DATE_RE = re.compile(r"\[(\d{4}/\d{2}/\d{2})")
DAY_RE = re.compile(r"\[(\d{4}/\d{2}/\d{2} \([A-Za-z]{3}\))")
SESSION_RE = re.compile(r"(?=\[\d{4}/\d{2}/\d{2}[^\]]*\] )")


def main(argv: list[str]) -> int:
    run_dirs = [Path(a) for a in argv[1:]]
    if not run_dirs:
        print(__doc__)
        return 2

    per_q: dict[str, dict[str, list[str]]] = {}

    for run_dir in run_dirs:
        path = run_dir / "benchmark-mr-diagnostics.json"
        if not path.exists():
            continue
        records = json.loads(path.read_text())
        by_id = {r["question_id"]: r for r in records}
        run = run_dir.parent.name

        for qid in DETERMINISTIC:
            r = by_id.get(qid)
            if r is None:
                continue
            d = r.get("decision") or {}
            prompt = d.get("retrieved") or ""
            retrieved_days = set(DAY_RE.findall(prompt))

            # Gold session day(s), derived from the gold session content.
            gold_days: set[str] = set()
            for body in r.get("answer_sessions_content") or []:
                for m in DAY_RE.findall(body):
                    gold_days.add(m)

            hit = bool(gold_days & retrieved_days)
            key = "recalled" if hit else "missed"
            cov = (
                len(gold_days & retrieved_days) / len(gold_days) if gold_days else 0.0
            )
            per_q.setdefault(qid, {}).setdefault(key, []).append(run)
            per_q[qid].setdefault("_cov", []).append(cov)

    print("# Gold-session recall among deterministic MR failures\n")
    print("| question | runs | runs recalling gold | runs missing gold | mean day coverage |")
    print("|---|---|---|---|---|")
    stable_missed = 0
    for qid in DETERMINISTIC:
        if qid not in per_q:
            continue
        st = per_q[qid]
        rec = len(st.get("recalled", []))
        mis = len(st.get("missed", []))
        covs = st.get("_cov", [])
        mean_cov = sum(covs) / len(covs) if covs else 0.0
        n = rec + mis
        # A stable miss is the only shape that licenses a retrieval fix: a
        # question that recalls its gold session in SOME runs fails for a
        # different reason in the others, and averaging the two hides that.
        flag = " **STABLE MISS**" if mis == n else (" (flaky)" if mis else "")
        if mis == n:
            stable_missed += 1
        print(
            f"| {qid} | {n} | {rec} | {mis} | {100 * mean_cov:.0f}% |{flag}"
        )
    print()
    print(f"Questions that NEVER recalled their gold session: {stable_missed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
