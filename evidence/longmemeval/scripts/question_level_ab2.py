"""Question-level significance testing for the same-instant A/B.

The unit of analysis here is the QUESTION (n=470), not the run (n=3). Run-level
tests cannot resolve a +0.73pp shift; question-level tests on the *mechanism*
can, because the patch's effect is concentrated and deterministic.
"""

import json
import re
import math
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
NOTE_SCAFFOLD = re.compile(r"(?im)^\s*(?:\*{0,2}step\s*\d|#{1,6}\s|[-*•]\s|\d+[.)]\s)")
COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")


def norm(a):
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


def verdict(question, answer, expected):
    if expected is None:
        return answer is None
    if answer is None:
        return False
    if norm(answer) == norm(expected):
        return True
    if COUNTING.search(question):
        p, e = leading_number(answer), leading_number(expected)
        if p is not None and e is not None:
            return p == e
    return None


def collapsed(raw):
    if not raw:
        return False
    return (not ANSWER_LINE.search(raw)) and bool(NOTE_SCAFFOLD.search(raw))


def load(d):
    out = {}
    for name in ("benchmark-single-session-diagnostics.json", "benchmark-mr-diagnostics.json"):
        for x in json.loads((d / name).read_text()):
            dec = x["decision"]
            raw = dec.get("llmRaw") or ""
            out[x["question_id"]] = {
                "capability": x.get("capability", "MR"),
                "question": x["question"],
                "expected": x["ground_truth"],
                "answer": dec.get("answer"),
                "abstained": bool(dec.get("abstained")),
                "collapsed": collapsed(raw),
                "ans_len": len(dec["answer"]) if isinstance(dec.get("answer"), str) else 0,
            }
    return out


DATA = {r[1]: load(r[2]) for r in RUNS}
CTRL = [r[1] for r in RUNS if r[0] == "control"]
TREAT = [r[1] for r in RUNS if r[0] == "treatment"]
QIDS = sorted(set.intersection(*[set(v) for v in DATA.values()]))


def binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial p-value."""
    if n == 0:
        return 1.0
    def c(i):
        return math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    obs = c(k)
    return min(1.0, sum(c(i) for i in range(n + 1) if c(i) <= obs * (1 + 1e-9)))


def mcnemar_exact(b, c):
    """Exact McNemar: b = control-only events, c = treatment-only events."""
    n = b + c
    if n == 0:
        return 1.0
    return binom_two_sided(min(b, c), n)


def question_level(field, label):
    """Pair each question: does the event occur more in control or treatment?"""
    b = c = both = neither = 0
    for q in QIDS:
        ce = sum(DATA[r][q][field] for r in CTRL)
        te = sum(DATA[r][q][field] for r in TREAT)
        if ce > te:
            b += 1
        elif te > ce:
            c += 1
        elif ce > 0:
            both += 1
        else:
            neither += 1
    p = mcnemar_exact(b, c)
    print(f"  {label}")
    print(f"    questions worse under control: {b}   worse under treatment: {c}   "
          f"tied: {both + neither}")
    print(f"    exact McNemar p = {p:.3e}")
    return b, c, p


print("== A. question-level significance (unit = question, n=470) ==")
print()
question_level("collapsed", "format collapse")
print()
question_level("abstained", "abstention")
print()

print("== B. the collapsed questions: what did the fix do to them? ==")
touched = [q for q in QIDS if any(DATA[r][q]["collapsed"] for r in CTRL)]
print(f"  questions that collapsed in >=1 control run: {len(touched)} / {len(QIDS)}")
print(f"  questions that collapsed in >=1 treatment run: "
      f"{sum(1 for q in QIDS if any(DATA[r][q]['collapsed'] for r in TREAT))}")
rows = []
for q in touched:
    s = DATA[CTRL[0]][q]
    cap = s["capability"]
    det = []
    for r in CTRL + TREAT:
        det.append(verdict(s["question"], DATA[r][q]["answer"], DATA[r][q]["expected"]))
    cd, td = det[:3], det[3:]
    rows.append((cap, cd, td))
resolvable = [r for r in rows if all(v is not None for v in r[1] + r[2])]
print(f"  of those, {len(resolvable)} are graded deterministically in all 6 runs")
if resolvable:
    ca = sum(sum(r[1] for r in resolvable)) / (len(resolvable) * 3)
    ta = sum(sum(r[2] for r in resolvable)) / (len(resolvable) * 3)
    print(f"  deterministic accuracy on them: control {ca*100:.2f}%  treatment {ta*100:.2f}%"
          f"  ({(ta-ca)*100:+.2f}pp)")
# substring proxy for the judge-graded remainder
sub_c = sub_t = n_sub = 0
for q in touched:
    s = DATA[CTRL[0]][q]
    exp = norm(s["expected"]) if s["expected"] is not None else None
    if not exp:
        continue
    n_sub += 1
    sub_c += sum(1 for r in CTRL if norm(DATA[r][q]["answer"]).find(exp) >= 0) / 3
    sub_t += sum(1 for r in TREAT if norm(DATA[r][q]["answer"]).find(exp) >= 0) / 3
print(f"  answer contains the gold string:  control {sub_c/n_sub*100:.2f}%  "
      f"treatment {sub_t/n_sub*100:.2f}%   (n={n_sub}, proxy only)")
print()

print("== C. run-to-run instability, by whether the question ever collapsed ==")
for arm, rs in (("control", CTRL), ("treatment", TREAT)):
    cf = ct = sf = sother = 0
    for q in QIDS:
        strings = {str(DATA[r][q]["answer"]) for r in rs}
        flipped = len(strings) > 1
        ever = any(DATA[r][q]["collapsed"] for r in rs)
        if ever:
            ct += 1
            cf += flipped
        else:
            sother += 1
            sf += flipped
    cf_pct = f"{cf/ct*100:5.1f}%" if ct else "   n/a"
    print(f"  {arm:<10} ever-collapsed {cf:3d}/{ct:3d} flip ({cf_pct})   "
          f"never-collapsed {sf:3d}/{sother:3d} flip ({sf/sother*100:5.1f}%)")
print()

print("== D. answer-length tail ==")
for arm, rs in (("control", CTRL), ("treatment", TREAT)):
    lens = sorted(DATA[r][q]["ans_len"] for r in rs for q in QIDS)
    n = len(lens)
    print(f"  {arm:<10} n={n}  median={lens[n//2]:4d}  p95={lens[int(n*.95)]:5d}  "
          f"p99={lens[int(n*.99)]:5d}  max={lens[-1]:6d}  "
          f">200 chars: {sum(1 for x in lens if x > 200)}")
print()

print("== E. per-run-pair consistency of the mechanism ==")
for field in ("collapsed", "abstained"):
    vals = []
    for rc, rt in zip(CTRL, TREAT):
        c = sum(DATA[rc][q][field] for q in QIDS) / len(QIDS)
        t = sum(DATA[rt][q][field] for q in QIDS) / len(QIDS)
        vals.append((t - c) * 100)
    same = all(v > 0 for v in vals) or all(v < 0 for v in vals)
    print(f"  {field:<10} " + ", ".join(f"{v:+.2f}pp" for v in vals) +
          f"   consistent sign: {same}")
print()

print("== F. TR deep dive: -7.87pp abstention but only +0.52pp accuracy ==")
tr = [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == "TR"]
moved = [q for q in tr if sum(DATA[r][q]["abstained"] for r in CTRL) >
         sum(DATA[r][q]["abstained"] for r in TREAT)]
print(f"  TR questions that stopped abstaining: {len(moved)}")
gained = 0
resolved = 0
for q in moved:
    s = DATA[CTRL[0]][q]
    vc = [verdict(s["question"], DATA[r][q]["answer"], DATA[r][q]["expected"]) for r in CTRL]
    vt = [verdict(s["question"], DATA[r][q]["answer"], DATA[r][q]["expected"]) for r in TREAT]
    if all(v is not None for v in vc + vt):
        resolved += 1
        gained += sum(vt) / 3 - sum(vc) / 3
print(f"  deterministically graded among them: {resolved}")
print(f"  net questions won per run: {gained:+.2f}  "
      f"(abstention fell by {sum(sum(DATA[r][q]['abstained'] for r in CTRL) - sum(DATA[r][q]['abstained'] for r in TREAT) for q in moved)/3:.2f}/run)")
