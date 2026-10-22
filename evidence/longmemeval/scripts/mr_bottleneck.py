"""Where does MR accuracy still leak? Cross-tabulate evidence completeness
against correctness so the next iteration targets the actual bottleneck.

The turn-recall channel lifted evidence recall from 94.0% to 97.2%. The question
this answers is whether retrieval is still what limits MR accuracy: among the
questions still answered WRONG, how many already had all their evidence in the
context? If most did, the leak is aggregation/extraction, and more retrieval work
has low ROI.

Usage: python3 mr_bottleneck.py [root]   (default: ab_turn)
"""
import json, re, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "ab_turn")
FP_LEN = 80
COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")


def fp(t, n=FP_LEN):
    return re.sub(r"\W+", "", str(t).lower())[:n]


def norm(a):
    return re.sub(r"\s+", "", str(a).strip().lower())


def lead(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def verdict(question, answer, expected):
    if expected is None:
        return answer is None
    if answer is None:
        return False
    if norm(answer) == norm(expected):
        return True
    if COUNTING.search(question):
        p, e = lead(answer), lead(expected)
        if p is not None and e is not None:
            return p == e
    return None


def load(d):
    out = {}
    for name in ("benchmark-mr-diagnostics.json", "benchmark-single-session-diagnostics.json"):
        p = d / name
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x["decision"] or {}
            ev = x.get("answer_sessions_content") or []
            retrieved = dec.get("retrieved", "") or ""
            fpr = fp(retrieved, 10 ** 7)
            found = sum(1 for c in ev if fp(c) and fp(c) in fpr)
            out[x["question_id"]] = {
                "cap": x.get("capability", "MR"),
                "complete": len(ev) > 0 and found == len(ev),
                "v": verdict(x["question"], dec.get("answer"), x["ground_truth"]),
                "abstained": bool(dec.get("abstained")),
                "question": x["question"],
            }
    return out


def runs(arm):
    """Load every run directory of one arm."""
    return [load(d) for d in sorted((ROOT / arm).iterdir()) if d.is_dir()]


def buckets(D):
    """Split MR questions into the four buckets the bottleneck question needs."""
    mr = [q for q in D[0] if D[0][q]["cap"] == "MR"]

    def maj(q, key):
        return sum(1 for d in D if d[q][key]) / len(D) > 0.5

    det = [q for q in mr if all(d[q]["v"] is not None for d in D)]
    correct = {q for q in det if sum(1 for d in D if d[q]["v"]) / len(D) > 0.5}
    wrong = [q for q in det if q not in correct]
    return {
        "mr": mr,
        "complete": [q for q in mr if maj(q, "complete")],
        "wrong": wrong,
        "wrong_complete": [q for q in wrong if maj(q, "complete")],
        "wrong_missing": [q for q in wrong if not maj(q, "complete")],
        "wrong_abstained": [q for q in wrong if maj(q, "abstained")],
        "maj": maj,
    }


if __name__ == "__main__":
    for arm in ("control", "treatment"):
        D = runs(arm)
        b = buckets(D)
        mr, wrong, wc, wa = b["mr"], b["wrong"], b["wrong_complete"], b["wrong_abstained"]
        det = [q for q in mr if all(d[q]["v"] is not None for d in D)]
        correct = {q for q in det if sum(1 for d in D if d[q]["v"]) / len(D) > 0.5}
        print(f"=== {arm} ({len(D)} runs) ===")
        print(f"  MR questions                 : {len(mr)}")
        print(f"  evidence complete (majority) : {len(b['complete'])}")
        print(f"  determinate verdicts         : {len(det)}   correct (majority): {len(correct)}")
        print(f"  WRONG                        : {len(wrong)}")
        print(f"    evidence COMPLETE   : {len(wc):3d}  ({len(wc)/len(wrong)*100:4.1f}%)  <- aggregation/extraction")
        print(f"    evidence INCOMPLETE : {len(wrong)-len(wc):3d}  ({(len(wrong)-len(wc))/len(wrong)*100:4.1f}%)  <- retrieval")
        print(f"    abstained           : {len(wa):3d}  ({len(wa)/len(wrong)*100:4.1f}%)")
        print()
