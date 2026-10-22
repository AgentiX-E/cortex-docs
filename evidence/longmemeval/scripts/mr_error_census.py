"""Where do the wrong MR answers actually come from?

Built after the deterministic-counting hypothesis was refuted: the five questions
whose Step-1 enumeration already had the gold number of items turn out to lose
them in QUALIFIER FILTERING, not in counting — the model writes its exclusion
verdict into the Step 1 bullets themselves ("Forbes | canceled | (not current)",
"(same event as above, counted once)"), so a per-item `included` verdict would
carry exactly the same verdict and return exactly the same wrong number.

So before designing another fix, measure the population: abstention, retrieval,
enumeration, filtering, and judge-only.

Usage: python3 mr_error_census.py [root]   (default: ab_turn)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")

LABELLED = re.compile(r"(?:^|\n)\s*(?:final answer|answer)\s*:\s*(.+?)\s*$", re.I | re.M)
ABSTAIN = re.compile(r"^\s*UNANSWERABLE\s*$", re.I)
STEP1 = re.compile(r"step\s*1", re.I)
STEP2 = re.compile(r"step\s*2", re.I)
BULLET = re.compile(r"^\s*[-*\u2022]\s+\S", re.M)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
COUNTING_Q = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
TURN_PREFIX = re.compile(r"^\[\d{4}/\d{2}/\d{2}")


def norm(v) -> str:
    return re.sub(r"\s+", "", str(v).strip().lower())


def lead(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def is_correct(q, answer, gold) -> bool | None:
    if answer is None:
        return False
    if norm(answer) == norm(gold):
        return True
    if COUNTING_Q.search(q):
        p, e = lead(answer), lead(gold)
        if p is not None and e is not None:
            return p == e
    return None


def fp(t: str, n: int = 80) -> str:
    return re.sub(r"\W+", "", str(t).lower())[:n]


def bullets(raw: str) -> int | None:
    m1, m2 = STEP1.search(raw or ""), STEP2.search(raw or "")
    if not m1:
        return None
    return len(BULLET.findall(raw[m1.end() : m2.start() if m2 else len(raw)]))


def load(arm: str) -> dict[str, list[dict]]:
    per: dict[str, list[dict]] = {}
    for d in sorted((ROOT / arm).iterdir()):
        p = d / "benchmark-mr-diagnostics.json"
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x.get("decision") or {}
            retrieved = dec.get("retrieved", "") or ""
            ev = x.get("answer_sessions_content") or []
            # The FULL retrieved text: the fingerprint has to cover everything,
            # otherwise a session only matches when it happens to sit in the
            # first 80 characters and every question looks retrieval-limited.
            fpr = fp(retrieved, 10**7)
            found = sum(1 for c in ev if fp(c) and fp(c) in fpr)
            per.setdefault(x["question_id"], []).append(
                {
                    "q": x["question"],
                    "gold": x["ground_truth"],
                    "answer": dec.get("answer"),
                    "abstained": bool(dec.get("abstained")),
                    "reason": dec.get("reason"),
                    "raw": dec.get("llmRaw", "") or "",
                    "bullets": bullets(dec.get("llmRaw", "") or ""),
                    "ev_total": len(ev),
                    "ev_found": found,
                    "ev_complete": len(ev) > 0 and found == len(ev),
                }
            )
    return per


def main() -> None:
    arm = sys.argv[2] if len(sys.argv) > 2 else "treatment"
    per = load(arm)
    runs = len(next(iter(per.values())))
    print(f"=== {arm}: {len(per)} MR questions x {runs} runs\n")

    rows = []
    for qid, rs in per.items():
        modal_ans = Counter(str(r["answer"]) for r in rs).most_common(1)[0]
        shots = [r for r in rs if str(r["answer"]) == modal_ans[0]]
        r = shots[0]
        verdicts = [is_correct(r["q"], x["answer"], r["gold"]) for x in rs]
        # Two readings, and the difference between them is itself a finding: a
        # question wrong in all 4 runs is a systematic error, while one wrong in
        # the modal vote alone is flaky and no mechanism claim can rest on it.
        modal_ok = is_correct(r["q"], None if modal_ans[0] == "None" else modal_ans[0], r["gold"])
        rows.append(
            {
                "q": r["q"],
                "gold": r["gold"],
                "answer": None if modal_ans[0] == "None" else modal_ans[0],
                "votes": modal_ans[1],
                "stable_wrong": all(v is False for v in verdicts),
                "abstained": r["abstained"],
                "ev_complete": r["ev_complete"],
                "ev_total": r["ev_total"],
                "ev_found": r["ev_found"],
                "bullets": r["bullets"],
                "ok": True if all(v is True for v in verdicts) else (
                    False if any(v is False for v in verdicts) else None
                ),
                "modal_ok": modal_ok,
            }
        )

    n = len(rows)
    abst = [r for r in rows if r["abstained"]]
    answered = [r for r in rows if not r["abstained"]]
    ok = [r for r in rows if r["ok"] is True]
    bad = [r for r in rows if r["ok"] is False]
    judge = [r for r in rows if r["ok"] is None]

    print(f"{'bucket':<44}{'n':>4}{'of':>6}")
    print(f"{'abstained (no answer)':<44}{len(abst):>4}{n:>6}   {len(abst)/n:.1%}")
    print(f"{'  ... of those with COMPLETE evidence':<44}"
          f"{sum(1 for r in abst if r['ev_complete']):>4}{len(abst):>6}")
    print(f"{'answered':<44}{len(answered):>4}{n:>6}")
    print(f"{'  offline-decided correct (all runs)':<44}{len(ok):>4}{n:>6}   {len(ok)/n:.1%}")
    print(f"{'  offline-decided WRONG (>=1 run)':<44}{len(bad):>4}{n:>6}   {len(bad)/n:.1%}")
    print(f"{'  ... of those wrong in ALL runs':<44}"
          f"{sum(1 for r in bad if r['stable_wrong']):>4}{len(bad):>6}")
    print(f"{'  ... modal answer wrong':<44}"
          f"{sum(1 for r in bad if r['modal_ok'] is False):>4}{len(bad):>6}")
    print(f"{'  judge-only (undecidable offline)':<44}{len(judge):>4}{n:>6}")

    print("\n--- offline-decided WRONG, split by mechanism ---")
    num_bad = [r for r in bad if lead(r["gold"]) is not None and lead(r["answer"]) is not None]
    inc = [r for r in num_bad if not r["ev_complete"]]
    done = [r for r in num_bad if r["ev_complete"]]
    print(f"  evidence incomplete (retrieval-limited)   : {len(inc)}")
    print(f"  evidence complete, still wrong            : {len(done)}")
    short = [r for r in done if r["bullets"] is not None and r["bullets"] < lead(r["gold"])]
    lost = [
        r
        for r in done
        if r["bullets"] is not None
        and r["bullets"] >= lead(r["gold"])
        and lead(r["answer"]) != lead(r["gold"])
    ]
    print(f"     Step 1 short (enumeration)             : {len(short)}")
    print(f"     Step 1 >= gold, answer lower/different : {len(lost)}")
    for r in sorted(lost, key=lambda r: r["q"]):
        print(f"        gold={lead(r['gold']):<6g} step1={r['bullets']} ans={lead(r['answer']):<6g} "
              f"votes={r['votes']}/{runs}  {r['q'][:66]}")

    print("\n--- abstained WITH complete evidence (pure abstention leak) ---")
    for r in sorted(abst, key=lambda r: r["q"]):
        if r["ev_complete"]:
            print(f"    gold={str(r['gold'])[:24]:<24} ev={r['ev_found']}/{r['ev_total']}  {r['q'][:70]}")


if __name__ == "__main__":
    main()
