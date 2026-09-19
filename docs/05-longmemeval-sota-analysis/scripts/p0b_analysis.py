"""P0-b same-instant A/B: control = 8d87341 (regressed), treatment = f096338 (fix).

Primary endpoint: abstention on the 29 single-session-preference questions.
Guards: format collapse stays 0.00%, IE/overall not below control -1.0pp.
"""
import json, re, math
from pathlib import Path
from collections import Counter

ROOT = Path("ab_p0b")
CTRL = sorted([d for d in (ROOT / "control").iterdir() if d.is_dir()])
TREAT = sorted([d for d in (ROOT / "treatment").iterdir() if d.is_dir()])

ANSWER_LINE = re.compile(r"(?im)^\s*\*{0,2}(?:final\s+)?answer\s*\*{0,2}\s*:")
NOTE_SCAFFOLD = re.compile(r"(?im)^\s*(?:\*{0,2}step\s*\d|#{1,6}\s|[-*•]\s|\d+[.)]\s)")
COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
GENERATIVE = re.compile(r"^\s*the user would prefer", re.I)


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
        p = d / name
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
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


def load_report(d):
    return json.loads((d / "benchmark-report.json").read_text())


DATA = {d.name: load(d) for d in CTRL + TREAT}
REPORTS = {d.name: load_report(d) for d in CTRL + TREAT}
CNAMES = [d.name for d in CTRL]
TNAMES = [d.name for d in TREAT]

qids = sorted(set.intersection(*[set(v) for v in DATA.values()]))
print(f"questions present in all {len(DATA)} runs: {len(qids)}")
print(f"control runs: {CNAMES}")
print(f"treatment runs: {TNAMES}")
print()


def feat_metrics(r):
    return r["ablation"]["featureMetrics"]


print("== run-level aggregate (feature system) ==")
def row(names, label):
    rows = []
    for n in names:
        m = feat_metrics(REPORTS[n])
        rows.append(m)
    ov = [r["accuracy"] * 100 for r in rows]
    ab = [r["abstentionRate"] * 100 for r in rows]
    print(f"  {label}: overall {[f'{x:.2f}' for x in ov]}  abst {[f'{x:.2f}' for x in ab]}")
    return rows

crows = row(CNAMES, "control ")
trows = row(TNAMES, "treatment")
print()


def mean(xs): return sum(xs) / len(xs)


def rate(names, qid, field):
    return mean([DATA[n][qid][field] for n in names])


IE = [q for q in qids if DATA[CNAMES[0]][q]["capability"] == "IE"]
gen = [q for q in IE if GENERATIVE.match(str(DATA[CNAMES[0]][q]["expected"]))]
ext = [q for q in IE if q not in set(gen)]
print(f"IE {len(IE)}  generative {len(gen)}  extractive {len(ext)}")
print()


def group_rate(names, qs, field):
    return mean([DATA[n][q][field] for n in names for q in qs]) * 100


print("== PRIMARY ENDPOINT: preference-question abstention ==")
for label, qs in (("IE generative (preference)", gen), ("IE extractive", ext), ("IE all", IE)):
    c = group_rate(CNAMES, qs, "abstained")
    t = group_rate(TNAMES, qs, "abstained")
    print(f"  {label:<28} control {c:6.2f}%   treatment {t:6.2f}%   delta {t-c:+7.2f}pp")
print()


# question-level McNemar on abstention (unit = question)
def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    def binom(k, n, p=0.5):
        def comb(n, k):
            return math.comb(n, k)
        obs = comb(n, k) * (p ** k) * ((1 - p) ** (n - k))
        return min(1.0, sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
                            for i in range(n + 1)
                            if comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) <= obs * 1.000001))
    return binom(min(b, c), n)


print("== question-level McNemar (unit = question, paired over runs) ==")
for label, qs in (("preference abstention", gen),
                  ("format collapse", qids),
                  ("abstention (all)", qids)):
    b = c = 0
    for q in qs:
        ce = sum(DATA[n][q]["abstained"] if label != "format collapse" else DATA[n][q]["collapsed"]
                 for n in CNAMES)
        te = sum(DATA[n][q]["abstained"] if label != "format collapse" else DATA[n][q]["collapsed"]
                 for n in TNAMES)
        if ce > te:
            b += 1
        elif te > ce:
            c += 1
    print(f"  {label:<22} control-worse {b:3d}   treatment-worse {c:3d}   exact p = {mcnemar_exact(b, c):.3e}")
print()


print("== guard: format collapse rate ==")
for label, qs in (("ALL", qids), ("IE", IE)):
    cc = mean([DATA[n][q]["collapsed"] for n in CNAMES for q in qs]) * 100
    tt = mean([DATA[n][q]["collapsed"] for n in TNAMES for q in qs]) * 100
    print(f"  {label:<4} control {cc:6.2f}%   treatment {tt:6.2f}%")
print()


print("== deterministic accuracy (exact-match + numeric verdict) ==")
for cap in ("IE", "TR", "MR", "KU", "ALL"):
    qs = [q for q in qids if cap == "ALL" or DATA[CNAMES[0]][q]["capability"] == cap]
    pairs = []
    for q in qs:
        s = DATA[CNAMES[0]][q]
        vc = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in CNAMES]
        vt = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in TNAMES]
        if all(v is not None for v in vc + vt):
            pairs.append((mean([1.0 * v for v in vc]), mean([1.0 * v for v in vt])))
    if not pairs:
        continue
    c = mean([p[0] for p in pairs]) * 100
    t = mean([p[1] for p in pairs]) * 100
    print(f"  {cap:<4} n={len(pairs):3d}  control {c:6.2f}%   treatment {t:6.2f}%   delta {t-c:+6.2f}pp")
print()


print("== answer-length tail ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    lens = sorted(DATA[n][q]["ans_len"] for n in names for q in qids)
    n = len(lens)
    print(f"  {label:<10} n={n}  p95={lens[int(n*.95)]:5d}  p99={lens[int(n*.99)]:5d}  max={lens[-1]:6d}  >200:{sum(1 for x in lens if x>200)}")
print()


print("== per-capability run-level accuracy ==")
for cap in ("IE", "TR", "MR", "KU", "ABS"):
    c = [feat_metrics(REPORTS[n])["perCapability"][cap]["accuracy"] * 100 for n in CNAMES]
    t = [feat_metrics(REPORTS[n])["perCapability"][cap]["accuracy"] * 100 for n in TNAMES]
    print(f"  {cap:<4} control {[f'{x:.2f}' for x in c]}  treatment {[f'{x:.2f}' for x in t]}")
