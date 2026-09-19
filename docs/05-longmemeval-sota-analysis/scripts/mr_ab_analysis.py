"""MR over-abstention A/B: control f096338 vs treatment 03d0465 (10de393 fix)."""
import json, re, math
from pathlib import Path

ROOT = Path("ab_mr")
CTRL = sorted([d for d in (ROOT / "control").iterdir() if d.is_dir()])
TREAT = sorted([d for d in (ROOT / "treatment").iterdir() if d.is_dir()])
CNAMES = [d.name for d in CTRL]
TNAMES = [d.name for d in TREAT]

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

def load(d):
    out = {}
    for name in ("benchmark-single-session-diagnostics.json", "benchmark-mr-diagnostics.json"):
        p = d / name
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x["decision"] or {}
            out[x["question_id"]] = {
                "capability": x.get("capability", "MR"),
                "question": x["question"],
                "expected": x["ground_truth"],
                "answer": dec.get("answer"),
                "abstained": bool(dec.get("abstained")),
                "reason": dec.get("reason"),
                "retrieved": dec.get("retrieved", "") or "",
            }
    return out

def load_report(d):
    return json.loads((d / "benchmark-report.json").read_text())

DATA = {d.name: load(d) for d in CTRL + TREAT}
REPORTS = {d.name: load_report(d) for d in CTRL + TREAT}
qids = sorted(set.intersection(*[set(v) for v in DATA.values()]))
print(f"questions in all {len(DATA)} runs: {len(qids)}")
print(f"control:   {CNAMES}")
print(f"treatment: {TNAMES}\n")

def fm(r):
    return r["ablation"]["featureMetrics"]

def mean(xs): return sum(xs)/len(xs) if xs else 0.0

# run-level aggregate
print("== run-level aggregate (feature system) ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    ov = [fm(REPORTS[n])["accuracy"]*100 for n in names]
    ab = [fm(REPORTS[n])["abstentionRate"]*100 for n in names]
    mr = [fm(REPORTS[n])["perCapability"]["MR"]["accuracy"]*100 for n in names]
    print(f"  {label:<10} overall={[f'{x:.2f}' for x in ov]}  abst={[f'{x:.2f}' for x in ab]}  MR={[f'{x:.2f}' for x in mr]}")
print()

# per-capability delta
print("== per-capability (run-level) ==")
for cap in ("IE", "TR", "MR", "KU", "ABS"):
    c = [fm(REPORTS[n])["perCapability"][cap]["accuracy"]*100 for n in CNAMES]
    t = [fm(REPORTS[n])["perCapability"][cap]["accuracy"]*100 for n in TNAMES]
    print(f"  {cap:<4} control {mean(c):6.2f}%   treatment {mean(t):6.2f}%   delta {mean(t)-mean(c):+6.2f}pp   "
          f"[{[f'{x:.1f}' for x in c]} vs {[f'{x:.1f}' for x in t]}]")
print()

# PRIMARY: MR abstention (question-level)
MR = [q for q in qids if DATA[CNAMES[0]][q]["capability"] == "MR"]
print(f"== PRIMARY: MR abstention (n={len(MR)} questions) ==")
c_abst = sum(DATA[n][q]["abstained"] for n in CNAMES for q in MR)
t_abst = sum(DATA[n][q]["abstained"] for n in TNAMES for q in MR)
c_rate = c_abst/(4*len(MR)); t_rate = t_abst/(4*len(MR))
print(f"  control   {c_abst}/{4*len(MR)} = {c_rate*100:.2f}%")
print(f"  treatment {t_abst}/{4*len(MR)} = {t_rate*100:.2f}%")
print(f"  delta {t_rate*100-c_rate*100:+.2f}pp")

# per-run MR abstention
print("  per-run MR abstention:")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    per = [sum(DATA[n][q]["abstained"] for q in MR)/len(MR)*100 for n in names]
    print(f"    {label:<10} {[f'{x:.1f}%' for x in per]}")

# question-level McNemar on MR abstention
def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    import math
    def binom(k, n, p=0.5):
        obs = math.comb(n, k) * (p**k) * ((1-p)**(n-k))
        return min(1.0, sum(math.comb(n,i)*(p**i)*((1-p)**(n-i))
                            for i in range(n+1)
                            if math.comb(n,i)*(p**i)*((1-p)**(n-i)) <= obs*1.000001))
    return binom(min(b,c), n)

b = c = 0
for q in MR:
    ce = sum(DATA[n][q]["abstained"] for n in CNAMES)
    te = sum(DATA[n][q]["abstained"] for n in TNAMES)
    if ce > te: b += 1
    elif te > ce: c += 1
print(f"  question-level McNemar: control-worse {b}, treatment-worse {c}, exact p = {mcnemar_exact(b,c):.3e}")
print()

# MR abstention reason breakdown
print("== MR abstention reason (all MR decisions) ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    from collections import Counter
    reasons = Counter(DATA[n][q]["reason"] for n in names for q in MR)
    print(f"  {label:<10} {dict(reasons)}")
print()

# deterministic MR accuracy (question-level paired)
print("== deterministic MR accuracy (exact + numeric, paired where both arms resolved) ==")
pairs = []
for q in MR:
    s = DATA[CNAMES[0]][q]
    vc = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in CNAMES]
    vt = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in TNAMES]
    if all(v is not None for v in vc + vt):
        pairs.append((mean([1.0*v for v in vc]), mean([1.0*v for v in vt])))
if pairs:
    ca = mean([p[0] for p in pairs])*100
    ta = mean([p[1] for p in pairs])*100
    print(f"  n={len(pairs)}  control {ca:.2f}%   treatment {ta:.2f}%   delta {ta-ca:+.2f}pp")
print()

# guard: do the newly-answered MR questions have their evidence retrieved?
print("== guard: evidence recall on MR questions answered by treatment but abstained by control ==")
moved = [q for q in MR if sum(DATA[n][q]["abstained"] for n in CNAMES) > sum(DATA[n][q]["abstained"] for n in TNAMES)]
print(f"  MR questions that stopped abstaining: {len(moved)}")
# of those, how many have non-empty retrieved context in treatment?
with_ev = sum(1 for q in moved if any(DATA[n][q]["retrieved"] for n in TNAMES))
print(f"  treatment retrieved non-empty context for: {with_ev}/{len(moved)}")
