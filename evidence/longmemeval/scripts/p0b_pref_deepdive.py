"""P0-b: per-question preference deep dive + negative-control drift estimate."""
import re, json
from pathlib import Path

ROOT = Path("ab_p0b")
CTRL = sorted([d for d in (ROOT / "control").iterdir() if d.is_dir()])
TREAT = sorted([d for d in (ROOT / "treatment").iterdir() if d.is_dir()])
GENERATIVE = re.compile(r"^\s*the user would prefer", re.I)
STOP = set("""a an the and or of to in for on with my me i you your it is are was were be been
this that these those as at from by have has had do does did can could would should
any some more most other others than then there their they them he she his her
about into over under also very just not no yes""".split())
TOKEN = re.compile(r"[a-z0-9']+")

def toks(s):
    return {t for t in TOKEN.findall(str(s).lower()) if t not in STOP and len(t) > 2}

def f1(a, b):
    A, B = toks(a), toks(b)
    if not A or not B:
        return 0.0
    return 2*len(A & B)/(len(A)+len(B))

def mean(xs): return sum(xs)/len(xs) if xs else 0.0

def load(d):
    out = {}
    for name in ("benchmark-single-session-diagnostics.json", "benchmark-mr-diagnostics.json"):
        p = d / name
        if not p.exists():
            continue
        for x in json.loads(p.read_text()):
            dec = x["decision"]
            out[x["question_id"]] = {
                "capability": x.get("capability", "MR"),
                "question": x["question"],
                "expected": x["ground_truth"],
                "answer": dec.get("answer"),
                "abstained": bool(dec.get("abstained")),
            }
    return out

DATA = {d.name: load(d) for d in CTRL + TREAT}
REPORTS = {d.name: json.loads((d / "benchmark-report.json").read_text()) for d in CTRL + TREAT}
CNAMES = [d.name for d in CTRL]
TNAMES = [d.name for d in TREAT]

IE = [q for q in DATA[CNAMES[0]] if DATA[CNAMES[0]][q]["capability"] == "IE"]
gen = [q for q in IE if GENERATIVE.match(str(DATA[CNAMES[0]][q]["expected"]))]
print(f"preference (generative) questions: {len(gen)}")
print()

flips = sum(1 for q in gen if sum(DATA[n][q]["abstained"] for n in CNAMES) > sum(DATA[n][q]["abstained"] for n in TNAMES))
always_c = sum(1 for q in gen if sum(DATA[n][q]["abstained"] for n in CNAMES) == len(CNAMES))
always_t = sum(1 for q in gen if sum(DATA[n][q]["abstained"] for n in TNAMES) == len(TNAMES))
print(f"questions abstaining under control but not treatment: {flips}/{len(gen)}")
print(f"abstained in ALL control runs: {always_c}   ALL treatment runs: {always_t}")
print()

print("== token-F1 vs gold (proxy, calibrated within IE) ==")
for label, names in (("control", CNAMES), ("treatment", TNAMES)):
    fs = [f1(DATA[n][q]["answer"], DATA[CNAMES[0]][q]["expected"]) for q in gen for n in names]
    print(f"  {label:<10} mean F1 = {mean(fs):.4f}  (n={len(fs)})")
print()

print("== samples: what each arm answers ==")
for q in sorted(gen)[:6]:
    s = DATA[CNAMES[0]][q]
    print(f"  Q: {s['question'][:78]}")
    print(f"    gold : {str(s['expected'])[:88]}")
    print(f"    ctrl : abst={[DATA[n][q]['abstained'] for n in CNAMES]}  {str(DATA[CNAMES[0]][q]['answer'])[:62]!r}")
    print(f"    treat: abst={[DATA[n][q]['abstained'] for n in TNAMES]}  {str(DATA[TNAMES[0]][q]['answer'])[:78]!r}")
print()

print("== negative-control drift (untouched MR/KU/TR) ==")
for cap in ("MR", "KU", "TR"):
    c = [REPORTS[n]["ablation"]["featureMetrics"]["perCapability"][cap]["accuracy"]*100 for n in CNAMES]
    t = [REPORTS[n]["ablation"]["featureMetrics"]["perCapability"][cap]["accuracy"]*100 for n in TNAMES]
    print(f"  {cap}: control {mean(c):.2f}%  treatment {mean(t):.2f}%  delta {mean(t)-mean(c):+.2f}pp")
