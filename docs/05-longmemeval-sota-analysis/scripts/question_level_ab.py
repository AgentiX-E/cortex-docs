"""Question-level analysis of the same-instant A/B.

The run-level comparison has n=3 per arm, which is far too little power to say
anything about a +0.73pp mean shift. But the artifacts carry the raw LLM output
for 470 of the 500 questions in every run, so the *mechanism* can be measured at
n = 470 x 3 = 1410 observations per arm. This script measures:

  1. format collapse      -- the exact failure mode the patch targets
  2. abstention           -- the downstream behaviour the collapse drives
  3. deterministic accuracy -- exact-match + numeric verdict, paired on the
                              subset graded identically in both arms

and then asks whether the control arm's run-to-run instability lives inside the
collapsed questions.
"""

import json
import re
import statistics as st
from pathlib import Path

RUNS = [
    ("control",   287180, Path("ab_pjson/run_33734287180")),
    ("control",   290087, Path("ab_pjson/run_33734290087")),
    ("control",   293014, Path("ab_pjson/run_33734293014")),
    ("treatment", 298345, Path("ab_fix/run_33734298345")),
    ("treatment", 302150, Path("ab_fix/run_33734302150")),
    ("treatment", 307358, Path("ab_fix/run_33734307358")),
]

ANSWER_LINE = re.compile(r"(?im)^\s*\*{0,2}(?:final\s+)?answer\s*\*{0,2}\s*:")
NOTE_SCAFFOLD = re.compile(
    r"(?im)^\s*(?:\*{0,2}step\s*\d|#{1,6}\s|[-*•]\s|\d+[.)]\s)"
)
COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")


def normalize(a):
    return str(a).strip().lower().replace("\s+", " ")


def normalize_answer(a):
    return re.sub(r"\s+", " ", str(a).strip().lower())


def leading_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    m = LEADING_NUM.match(v.strip())
    return float(m.group(1).replace(",", "")) if m else None


def deterministic_verdict(question, answer, expected):
    """Reimplementation of the eval's deterministic grading path.

    Returns True/False when exact-match or the numeric verdict decides the
    question, and None when the benchmark would have to call the LLM judge.
    """
    if expected is None:
        return answer is None
    if answer is None:
        return False
    if normalize_answer(answer) == normalize_answer(expected):
        return True
    if COUNTING.search(question):
        p, e = leading_number(answer), leading_number(expected)
        if p is not None and e is not None:
            return p == e
    return None


def collapsed(raw):
    """True when the model wrote Step-1 scaffolding and never reached Step 2."""
    if not raw:
        return False
    if ANSWER_LINE.search(raw):
        return False
    return bool(NOTE_SCAFFOLD.search(raw))


def load(run_dir):
    out = {}
    for name in ("benchmark-single-session-diagnostics.json", "benchmark-mr-diagnostics.json"):
        for x in json.loads((run_dir / name).read_text()):
            d = x["decision"]
            raw = d.get("llmRaw") or ""
            out[x["question_id"]] = {
                "capability": x.get("capability", "MR"),
                "question": x["question"],
                "expected": x["ground_truth"],
                "answer": d.get("answer"),
                "abstained": bool(d.get("abstained")),
                "raw": raw,
                "collapsed": collapsed(raw),
                "raw_len": len(raw),
                "ans_len": len(d["answer"]) if isinstance(d.get("answer"), str) else 0,
            }
    return out


data = {r[1]: load(r[2]) for r in RUNS}
qids = sorted(set.intersection(*[set(v) for v in data.values()]))
print(f"questions present in all 6 runs: {len(qids)}")

# ground truth must agree across runs or pairing is meaningless
for q in qids[:0]:
    pass
mismatched = [q for q in qids if len({str(data[r][q]["expected"]) for r in data}) > 1]
print(f"ground-truth mismatches across runs: {len(mismatched)}")

CAPS = ["IE", "TR", "MR", "KU"]


def group(arm):
    return [r for r in RUNS if r[0] == arm]


def rate(arm, qid, field):
    runs = group(arm)
    return sum(data[r[1]][qid][field] for r in runs) / len(runs)


print()
print("== 1. format collapse (the failure mode the patch targets) ==")
for cap in CAPS + ["ALL"]:
    qs = [q for q in qids if cap == "ALL" or data[RUNS[0][1]][q]["capability"] == cap]
    c = sum(rate("control", q, "collapsed") for q in qs) / len(qs)
    t = sum(rate("treatment", q, "collapsed") for q in qs) / len(qs)
    nc = sum(data[r[1]][q]["collapsed"] for r in group("control") for q in qs)
    nt = sum(data[r[1]][q]["collapsed"] for r in group("treatment") for q in qs)
    print(f"  {cap:<4} n={len(qs):3d}  control {c*100:5.2f}% ({nc:4d}/{len(qs)*3})  "
          f"treatment {t*100:5.2f}% ({nt:4d}/{len(qs)*3})  delta {(t-c)*100:+6.2f}pp")

print()
print("== 2. abstention ==")
for cap in CAPS + ["ALL"]:
    qs = [q for q in qids if cap == "ALL" or data[RUNS[0][1]][q]["capability"] == cap]
    c = sum(rate("control", q, "abstained") for q in qs) / len(qs)
    t = sum(rate("treatment", q, "abstained") for q in qs) / len(qs)
    print(f"  {cap:<4} n={len(qs):3d}  control {c*100:5.2f}%  treatment {t*100:5.2f}%  "
          f"delta {(t-c)*100:+6.2f}pp")

print()
print("== 3. deterministic accuracy (exact-match + numeric verdict only) ==")
print("   paired on questions where BOTH arms resolve deterministically in ALL 3 runs")
for cap in CAPS + ["ALL"]:
    qs = [q for q in qids if cap == "ALL" or data[RUNS[0][1]][q]["capability"] == cap]
    pairs = []
    for q in qs:
        sample = data[RUNS[0][1]][q]
        vc = [deterministic_verdict(sample["question"], data[r[1]][q]["answer"],
                                    data[r[1]][q]["expected"]) for r in group("control")]
        vt = [deterministic_verdict(sample["question"], data[r[1]][q]["answer"],
                                    data[r[1]][q]["expected"]) for r in group("treatment")]
        if all(v is not None for v in vc + vt):
            pairs.append((sum(vc) / 3, sum(vt) / 3))
    if not pairs:
        continue
    c = sum(p[0] for p in pairs) / len(pairs)
    t = sum(p[1] for p in pairs) / len(pairs)
    print(f"  {cap:<4} n={len(pairs):3d}  control {c*100:5.2f}%  treatment {t*100:5.2f}%  "
          f"delta {(t-c)*100:+6.2f}pp")

print()
print("== 4. where does the control arm's run-to-run instability live? ==")
print("   flip = a question answered differently by at least one of the 3 runs")
for arm in ("control", "treatment"):
    runs = group(arm)
    collapsed_flip = tot_c = stable_flip = tot_s = 0
    for q in qids:
        sample = data[runs[0][1]][q]
        verdicts = []
        for r in runs:
            v = deterministic_verdict(sample["question"], data[r[1]][q]["answer"],
                                      data[r[1]][q]["expected"])
            verdicts.append(v)
        # use the graded answer string when the verdict needs a judge
        strings = {str(data[r[1]][q]["answer"]) for r in runs}
        flipped = len(strings) > 1
        any_collapsed = any(data[r[1]][q]["collapsed"] for r in runs)
        if any_collapsed:
            tot_c += 1
            collapsed_flip += flipped
        else:
            tot_s += 1
            stable_flip += flipped
    print(f"  {arm:<10} collapsed-in-some-run: {collapsed_flip}/{tot_c} flip"
          f" ({collapsed_flip/tot_c*100:.1f}%)   never-collapsed: "
          f"{stable_flip}/{tot_s} flip ({stable_flip/tot_s*100:.1f}%)")

print()
print("== 5. answer-length tail (the visible symptom) ==")
for arm in ("control", "treatment"):
    lens = sorted(data[r[1]][q]["ans_len"] for r in group(arm) for q in qids)
    n = len(lens)
    print(f"  {arm:<10} n={n}  median={lens[n//2]:4d}  p95={lens[int(n*0.95)]:5d}  "
          f"p99={lens[int(n*0.99)]:6d}  max={lens[-1]:6d}  "
          f"over-200-chars={sum(1 for x in lens if x > 200)}")

print()
print("== 6. per-run-pair consistency (guards against run-level noise) ==")
pairs = list(zip([r for r in RUNS if r[0] == "control"],
                 [r for r in RUNS if r[0] == "treatment"]))
for metric in ("collapsed", "abstained"):
    vals = []
    for (_, rc, _), (_, rt, _) in pairs:
        c = sum(data[rc][q][metric] for q in qids) / len(qids)
        t = sum(data[rt][q][metric] for q in qids) / len(qids)
        vals.append((t - c) * 100)
    print(f"  {metric:<10} per-pair delta: " +
          ", ".join(f"{v:+.2f}pp" for v in vals) +
          f"   (all same sign: {all(v > 0 for v in vals) or all(v < 0 for v in vals)})")
