"""Re-check the "Step 2 drops items that Step 1 already listed" hypothesis.

The first version of this diagnosis (mr_filter_vs_enumeration.py) searched the
completion for the first `Answer: <n>` anywhere in the text. That is NOT what
the production parser reads: `parseAggregationAnswer` only accepts an `Answer:`
that starts a LINE (`/(?:^|\\n)\\s*(?:answer|final answer)\\s*:\\s*(.+?)\\s*$/im`),
so an inline "Answer: 2" mid-reasoning is invisible to it and the final
line-anchored "Answer: 5" is what actually counts.

That difference is not cosmetic. On "How many online courses have I completed in
total?" the loose regex read 2 in two of four runs while the shipped answer was 5
in all four. This script re-runs the diagnosis with the production-equivalent
parser to find out how many questions are genuinely lost between Step 1 and the
final answer.

Usage: python3 mr_filter_recheck.py [root]   (default: ab_turn)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")

# `parseAggregationAnswer`: a line-anchored label, last non-empty line otherwise.
LABELLED = re.compile(r"(?:^|\n)\s*(?:final answer|answer)\s*:\s*(.+?)\s*$", re.I | re.M)
ABSTAIN = re.compile(r"^\s*UNANSWERABLE\s*$", re.I)
STEP1 = re.compile(r"step\s*1", re.I)
STEP2 = re.compile(r"step\s*2", re.I)
BULLET = re.compile(r"^\s*[-*\u2022]\s+\S", re.M)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
COUNTING_Q = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)


def parse_answer(raw: str) -> str | None:
    """Exactly what parseAggregationAnswer returns, minus quote stripping."""
    trimmed = (raw or "").strip()
    if trimmed == "" or ABSTAIN.match(trimmed):
        return None
    m = LABELLED.search(trimmed)
    candidate = m.group(1).strip() if m else trimmed.splitlines()[-1].strip()
    if candidate == "" or ABSTAIN.match(candidate):
        return None
    return candidate


def loose_answer(raw: str) -> str | None:
    """The old, incorrect reading: first `Answer: <n>` anywhere in the text."""
    m = re.search(r"answer\s*[:：]\s*\$?\s*(-?\d[\d,]*(?:\.\d+)?)", raw or "", re.I)
    return m.group(1) if m else None


def bullets_in_step1(raw: str) -> int | None:
    m1, m2 = STEP1.search(raw or ""), STEP2.search(raw or "")
    if not m1:
        return None
    segment = raw[m1.end() : m2.start() if m2 else len(raw)]
    return len(BULLET.findall(segment))


def lead(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def is_correct(q: str, answer, gold) -> bool | None:
    """True / False, or None when only the LLM judge can decide it."""
    if answer is None:
        return False
    if re.sub(r"\s+", "", str(answer).strip().lower()) == re.sub(
        r"\s+", "", str(gold).strip().lower()
    ):
        return True
    if COUNTING_Q.search(q):
        p, e = lead(answer), lead(gold)
        if p is not None and e is not None:
            return p == e
    return None


def main() -> None:
    for arm in ("control", "treatment"):
        per: dict[str, list[dict]] = {}
        for d in sorted((ROOT / arm).iterdir()):
            p = d / "benchmark-mr-diagnostics.json"
            if not p.exists():
                continue
            for x in json.loads(p.read_text()):
                dec = x.get("decision") or {}
                per.setdefault(x["question_id"], []).append(
                    {
                        "q": x["question"],
                        "gold": x["ground_truth"],
                        "shipped": dec.get("answer"),
                        "reparsed": parse_answer(dec.get("llmRaw", "") or ""),
                        "loose": loose_answer(dec.get("llmRaw", "") or ""),
                        "bullets": bullets_in_step1(dec.get("llmRaw", "") or ""),
                    }
                )

        # Parser agreement: does the offline re-read reproduce the shipped answer?
        disagree = sum(
            1
            for rs in per.values()
            for r in rs
            if (r["reparsed"] or "") != (r["shipped"] or "")
        )
        total = sum(len(rs) for rs in per.values())
        runs = len(next(iter(per.values())))
        print(f"=== {arm}: {len(per)} MR questions x {runs} runs = {total} records")
        print(
            f"    offline parser reproduces the shipped answer on "
            f"{total - disagree}/{total} ({100 * (total - disagree) / total:.1f}%)"
        )
        loose_diff = sum(
            1
            for rs in per.values()
            for r in rs
            if r["loose"] is not None and r["loose"] != r["shipped"]
        )
        print(
            f"    the OLD loose regex disagreed with the shipped answer on "
            f"{loose_diff}/{total} ({100 * loose_diff / total:.1f}%)   <-- the bug"
        )

        # Collapse runs by the modal shipped answer.
        agg = []
        for qid, rs in per.items():
            c = Counter(str(r["shipped"]) for r in rs).most_common(1)[0]
            gold = lead(rs[0]["gold"])
            bullets = [r["bullets"] for r in rs if r["bullets"] is not None]
            agg.append(
                {
                    "qid": qid,
                    "q": rs[0]["q"],
                    "gold": gold,
                    "shipped": lead(rs[0]["shipped"]) if rs[0]["shipped"] else None,
                    "modal_ship": lead(c[0]) if c[0] != "None" else None,
                    "votes": c[1],
                    "bullets": max(bullets, key=bullets.count) if bullets else None,
                    "ok": is_correct(rs[0]["q"], rs[0]["shipped"], rs[0]["gold"]),
                }
            )

        numeric = [a for a in agg if a["gold"] is not None and a["modal_ship"] is not None]
        wrong = [a for a in numeric if not (a["ok"] is True)]
        decided = [a for a in wrong if a["ok"] is False]
        print(
            f"    {len(numeric)} numeric answered MR questions; "
            f"{len(decided)} offline-decided wrong (+{len(wrong) - len(decided)} judge-only)"
        )

        lost = [
            a
            for a in decided
            if a["bullets"] is not None and a["bullets"] >= a["gold"] and a["modal_ship"] != a["gold"]
        ]
        print(
            f"    Step 1 listed >= gold but the shipped answer is lower: "
            f"{len(lost)}/{len(decided)}"
        )
        for a in sorted(lost, key=lambda a: a["q"]):
            print(
                f"       gold={a['gold']:<6g} step1={a['bullets']}  answer={a['modal_ship']:<6g} "
                f"votes={a['votes']}/4  {a['q'][:70]}"
            )
        print()


if __name__ == "__main__":
    main()
