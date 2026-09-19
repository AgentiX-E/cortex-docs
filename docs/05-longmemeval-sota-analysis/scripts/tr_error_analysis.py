"""Attribute the TR (temporal-reasoning) errors to a mechanism.

TR is now the weakest and largest error pool on LongMemEval-S: 127 questions at
71.1%, i.e. ~37 wrong answers versus ~31 for MR. It also never abstains, so
every error is a confidently wrong answer — which is exactly the situation where
a deterministic engine should be able to help.

This reads the census emitted by tr_census.mjs (which classifies with the SHIPPED
classifyTemporalQuestion) and splits the errors by:
  - temporal kind, so the engine's coverage gap is visible;
  - ERROR SHAPE, which separates an arithmetic/extraction miss (off by a little)
    from a question the engine never even attempted (way off).

A way-off answer on a question the engine claims to handle is a bug; an off-by-N
answer is an arithmetic or a boundary convention (inclusive vs exclusive day
counting), and those two need completely different fixes.

Usage: python3 tr_error_analysis.py [root] [arm]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/analysis/ab_turn")
ARM = sys.argv[2] if len(sys.argv) > 2 else "treatment"

LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
DATE = re.compile(r"\d{4}/\d{2}/\d{2}")


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


def gold_nums(text: str) -> list[float]:
    """Every number the ground truth accepts (it often allows an inclusive count)."""
    out = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)", str(text)):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def correct(q, answer, gold) -> bool | None:
    """True / False, or None when only an LLM judge could decide it."""
    if answer is None:
        return False
    if norm(answer) == norm(gold):
        return True
    nums = gold_nums(gold)
    p = lead(answer)
    # The dataset routinely accepts an inclusive and an exclusive day count, so
    # matching ANY number the gold mentions is the intended reading.
    if p is not None and nums and any(abs(p - g) < 1e-9 for g in nums):
        return True
    if p is not None and nums:
        return False
    return None


def main() -> None:
    data = json.loads((ROOT / f"tr_census_{ARM}.json").read_text())
    qs = data["questions"]
    runs = len(data["runs"])
    print(f"=== {ARM}: {len(qs)} TR questions x {runs} runs\n")

    rows = []
    for q in qs:
        verdicts = [correct(q["question"], a, q["gold"]) for a in q["answers"]]
        modal = Counter(str(a) for a in q["answers"]).most_common(1)[0]
        rows.append(
            {
                **q,
                "n_ok": sum(1 for v in verdicts if v is True),
                "n_bad": sum(1 for v in verdicts if v is False),
                "undecided": any(v is None for v in verdicts),
                "modal_answer": None if modal[0] == "None" else modal[0],
                "modal_votes": modal[1],
            }
        )

    def acc(rs):
        return sum(1 for r in rs if r["n_bad"] == 0) / len(rs) if rs else 0.0

    print(f"{'kind':<14}{'n':>5}{'acc(all runs)':>15}{'stable wrong':>14}{'flaky':>8}")
    for kind in ("relative", "interval", "ordering", "eventLookup", "other"):
        sub = [r for r in rows if r["kind"] == kind]
        if not sub:
            continue
        stable = sum(1 for r in sub if r["n_ok"] == 0 and r["n_bad"] == runs)
        flaky = sum(1 for r in sub if 0 < r["n_bad"] < runs)
        print(
            f"{kind:<14}{len(sub):>5}{acc(sub):>15.1%}{stable:>14}{flaky:>8}"
        )

    # The engine only computes for relative / interval / ordering. `other` and
    # `eventLookup` are handled by prompts, so their errors are NOT engine bugs.
    handled = [r for r in rows if r["kind"] in ("relative", "interval", "ordering")]
    unhandled = [r for r in rows if r["kind"] in ("other", "eventLookup")]
    print(f"\nengine-handled (relative/interval/ordering): n={len(handled)} acc={acc(handled):.1%}")
    print(f"prompt-handled (other/eventLookup)         : n={len(unhandled)} acc={acc(unhandled):.1%}")
    print(
        f"  -> error pool: {sum(1 for r in handled if r['n_bad'])} of "
        f"{len(handled)} vs {sum(1 for r in unhandled if r['n_bad'])} of {len(unhandled)}"
    )

    print("\n--- error shape on NUMERIC engine-handled questions ---")
    numeric = [
        r
        for r in handled
        if r["n_bad"] > 0 and gold_nums(r["gold"]) and lead(r["modal_answer"]) is not None
    ]
    near, far = [], []
    for r in numeric:
        p = lead(r["modal_answer"])
        g = min(gold_nums(r["gold"]), key=lambda x: abs(x - p))
        d = abs(p - g)
        (near if d <= 3 else far).append((r, g, p, d))
    print(f"  within 3 of an accepted gold number (boundary/arithmetic): {len(near)}")
    print(f"  way off (the engine never got the right operands)         : {len(far)}")
    for r, g, p, d in sorted(near, key=lambda t: -t[3]):
        print(f"     gold={str(r['gold'])[:26]:<26} got={p:<8g} d={d:<4g} {r['question'][:62]}")


if __name__ == "__main__":
    main()
