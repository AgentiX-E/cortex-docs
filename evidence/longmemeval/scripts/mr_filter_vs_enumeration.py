"""Do MR counting failures happen in ENUMERATION or in FILTERING?

The aggregation prompt is a two-step CoT: Step 1 enumerates every matching item,
Step 2 applies the question's qualifiers and counts. If Step 1 already lists the
gold number of items but the final answer is lower, retrieval and enumeration are
both fine and the leak is the qualifier filter -- a different fix (and a much
cheaper one) than anything retrieval-side.

This parses `llmRaw` to count the bullets the model wrote under Step 1 and
compares that with its own final answer and with the gold.

Usage: python3 mr_filter_vs_enumeration.py [root]   (default: ab_turn)
"""
import json, re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")
STEP1 = re.compile(r"step\s*1", re.I)
STEP2 = re.compile(r"step\s*2", re.I)
BULLET = re.compile(r"^\s*[-*\u2022]\s+\S", re.M)
ANSWER = re.compile(r"answer\s*[:：]\s*\$?\s*(-?\d[\d,]*(?:\.\d+)?)", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def parse_steps(raw):
    """Return (bullets_in_step1, final_numeric_answer) from a CoT completion."""
    m1, m2 = STEP1.search(raw or ""), STEP2.search(raw or "")
    bullets = None
    if m1:
        segment = raw[m1.end(): m2.start() if m2 else len(raw)]
        # A one-item-per-line enumeration; nested sub-bullets are indented, so
        # requiring a non-space right after the marker keeps the count honest.
        bullets = len([b for b in BULLET.findall(segment)])
    a = ANSWER.search(raw or "")
    return bullets, (float(a.group(1).replace(",", "")) if a else None)


if __name__ == "__main__":
    for arm in ("control", "treatment"):
        rows = []
        for d in sorted((ROOT / arm).iterdir()):
            if not d.is_dir():
                continue
            p = d / "benchmark-mr-diagnostics.json"
            if not p.exists():
                continue
            for x in json.loads(p.read_text()):
                dec = x["decision"] or {}
                g = num(x["ground_truth"])
                if g is None or dec.get("abstained"):
                    continue
                bullets, ans = parse_steps(dec.get("llmRaw", "") or "")
                if ans is None or bullets is None:
                    continue
                rows.append({
                    "qid": x["question_id"], "q": x["question"][:64], "gold": g,
                    "enumerated": bullets, "answered": ans,
                })
        if not rows:
            continue

        # Collapse the 4 runs per question by taking the modal triple.
        per = {}
        for r in rows:
            per.setdefault(r["qid"], []).append(r)
        agg = []
        for qid, rs in per.items():
            c = Counter((r["enumerated"], r["answered"]) for r in rs).most_common(1)[0][0]
            agg.append({"qid": qid, "q": rs[0]["q"], "gold": rs[0]["gold"],
                        "enumerated": c[0], "answered": c[1]})

        wrong = [r for r in agg if abs(r["answered"] - r["gold"]) > 1e-9]
        print(f"=== {arm}: {len(agg)} numeric, non-abstained MR questions; {len(wrong)} answered wrong ===")
        enum_ok = [r for r in wrong if r["enumerated"] >= r["gold"]]
        enum_short = [r for r in wrong if r["enumerated"] < r["gold"]]
        print(f"  Step-1 enumeration already had >= gold items : {len(enum_ok)}/{len(wrong)}"
              f"  ({len(enum_ok)/len(wrong)*100:.0f}%)  <- lost in FILTERING")
        print(f"  Step-1 enumeration itself was short          : {len(enum_short)}/{len(wrong)}"
              f"  ({len(enum_short)/len(wrong)*100:.0f}%)  <- lost in ENUMERATION")
        print()
        # Derivation questions (difference / percentage / average / rate) list
        # OPERANDS in Step 1, not items, so `enumerated >= gold` is meaningless
        # for them. Split the two populations before drawing any conclusion.
        COUNT_ONLY = re.compile(r"\b(how many|number of|count|total number|how much (money|total))\b", re.I)
        DERIVED = re.compile(
            r"\b(average|mean|percentage|ratio|how much (more|less|older|faster|earlier)|"
            r"how many (years|hours|minutes) (older|more|less))\b", re.I)

        def qtype(q):
            if DERIVED.search(q):
                return "derivation"
            if COUNT_ONLY.search(q):
                return "counting"
            return "other"

        for want in ("counting", "derivation"):
            sub = [r for r in wrong if qtype(r["q"]) == want]
            if not sub:
                continue
            ok = [r for r in sub if r["enumerated"] >= r["gold"]]
            print(f"--- {want}: {len(sub)} wrong ---")
            print(f"    Step 1 already had >= gold : {len(ok)}/{len(sub)}  <- lost in FILTERING")
            print(f"    Step 1 itself short        : {len(sub)-len(ok)}/{len(sub)}  <- lost in ENUMERATION")
        print()

        for r in sorted(wrong, key=lambda r: (qtype(r["q"]), r["gold"])):
            where = "FILTER " if r["enumerated"] >= r["gold"] else "ENUM   "
            print(f"   {where} gold={r['gold']:<6g} enumerated={r['enumerated']:<3d} "
                  f"answered={r['answered']:<6g}  {r['q']}")
        print()
