"""Drill into the MR failures that have COMPLETE evidence in context.

Once retrieval is fixed, the remaining question is what kind of aggregation
failure is left. Counting questions are diagnosed numerically: if the model
returns a number a little below the gold, it found the right set but dropped an
item (an enumeration/attention failure inside the context); if it returns a
number unrelated to the gold, it counted the wrong set.

Usage: python3 mr_failure_drilldown.py [root]   (default: ab_turn)
"""
import json, re, sys
from pathlib import Path
from collections import Counter

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")
COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
DERIVATION = re.compile(r"\b(average|mean|percentage|ratio|how many years older|how much older|difference)\b", re.I)
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


def kind(q):
    if DERIVATION.search(q):
        return "derivation"
    if COUNTING.search(q):
        return "counting"
    return "lookup"


def load_raw(d):
    """Question text, gold, and model answer — `mb.load` does not keep them."""
    out = {}
    p = d / "benchmark-mr-diagnostics.json"
    if not p.exists():
        return out
    for x in json.loads(p.read_text()):
        dec = x["decision"] or {}
        out[x["question_id"]] = {
            "q": x["question"],
            "gold": x["ground_truth"],
            "ans": dec.get("answer"),
            "raw": (dec.get("llmRaw", "") or "")[:400],
        }
    return out


if __name__ == "__main__":
    import importlib.util

    spec = importlib.util.spec_from_file_location("mb", "mr_bottleneck.py")
    mb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mb)
    for arm in ("control", "treatment"):
        D = [mb.load(d) for d in sorted((ROOT / arm).iterdir()) if d.is_dir()]
        RAW = [load_raw(d) for d in sorted((ROOT / arm).iterdir()) if d.is_dir()]
        b = mb.buckets(D)
        wc = b["wrong_complete"]

        print(f"=== {arm}: {len(wc)} wrong WITH complete evidence ===")
        print(f"  by question kind: {dict(Counter(kind(RAW[0][q]['q']) for q in wc))}")
        abst = [q for q in wc if b["maj"](q, "abstained")]
        print(f"  abstained: {len(abst)}   answered-but-wrong: {len(wc) - len(abst)}")

        print("\n  --- numeric error on answered counting/derivation questions ---")
        rows = []
        for q in wc:
            if b["maj"](q, "abstained"):
                continue
            # The bucket uses a majority vote over runs, so the displayed answer
            # must too -- otherwise a question the vote calls wrong can show a
            # run-0 answer that happens to equal the gold (d = 0, "way off").
            answers = [r[q]["ans"] for r in RAW if q in r]
            modal = Counter(str(a) for a in answers).most_common(1)[0][0]
            g, a = num(RAW[0][q]["gold"]), num(modal)
            if g is None or a is None:
                continue
            rows.append((abs(a - g), a - g, q, kind(RAW[0][q]["q"]), RAW[0][q]["q"][:70], g, a))
        rows.sort()
        for _, d, q, k, qq, g, a in rows:
            tag = "OFF-BY" if 0 < abs(d) <= max(2.0, 0.34 * abs(g)) else "WAY-OFF"
            print(f"   {tag:7s} {k:10s} gold={g:<8g} pred={a:<8g} d={d:+g}  {qq}")
        n_off = sum(1 for r in rows if 0 < abs(r[1]) <= max(2.0, 0.34 * abs(r[5])))
        print(f"\n  off-by-a-few: {n_off}/{len(rows)}   way-off: {len(rows)-n_off}/{len(rows)}")
        print()
