"""MR derivation-prompt A/B: control 03d0465 vs treatment 183a3cc."""
import json, re, math, itertools
from pathlib import Path
from collections import Counter

ROOT = Path("ab_deriv")
CTRL = sorted([d for d in (ROOT / "control").iterdir() if d.is_dir()])
TREAT = sorted([d for d in (ROOT / "treatment").iterdir() if d.is_dir()])
CNAMES = [d.name for d in CTRL]
TNAMES = [d.name for d in TREAT]

COUNTING = re.compile(r"\b(how many|how much|number of|count|total)\b", re.I)
LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
DERIV = re.compile(
    r"\b(percentage|percent|average|mean|older than|how much (more|less|faster|earlier|save)|"
    r"difference in|increase in|discount|cashback|minimum|maximum|page count|how old was|how long have)\b",
    re.I,
)

def norm(a):
    return re.sub(r"\s+", " ", str(a).strip().lower())

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
                "raw": dec.get("llmRaw", "") or "",
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

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

# --- run-level ---
print("== run-level (feature system) ==")
for cap in ("IE", "TR", "MR", "KU", "ABS"):
    c = [fm(REPORTS[n])["perCapability"][cap]["accuracy"] * 100 for n in CNAMES]
    t = [fm(REPORTS[n])["perCapability"][cap]["accuracy"] * 100 for n in TNAMES]
    print(f"  {cap:<4} control {mean(c):6.2f}%  treatment {mean(t):6.2f}%  delta {mean(t)-mean(c):+6.2f}pp")
    print(f"       ctrl {[f'{x:.1f}' for x in c]}  treat {[f'{x:.1f}' for x in t]}")
c = [fm(REPORTS[n])["accuracy"] * 100 for n in CNAMES]
t = [fm(REPORTS[n])["accuracy"] * 100 for n in TNAMES]
print(f"  OV   control {mean(c):6.2f}%  treatment {mean(t):6.2f}%  delta {mean(t)-mean(c):+6.2f}pp")
print(f"       ctrl {[f'{x:.2f}' for x in c]}  treat {[f'{x:.2f}' for x in t]}")
c = [fm(REPORTS[n])["abstentionRate"] * 100 for n in CNAMES]
t = [fm(REPORTS[n])["abstentionRate"] * 100 for n in TNAMES]
print(f"  ABST control {mean(c):6.2f}%  treatment {mean(t):6.2f}%  delta {mean(t)-mean(c):+6.2f}pp")
print()

# --- exact permutation tests ---
def perm_p(dc, dt):
    allv = dc + dt
    k = len(dt)
    obs = mean(dt) - mean(dc)
    cnt = 0
    for combo in itertools.combinations(range(len(allv)), k):
        tv = [allv[i] for i in combo]
        cv = [allv[i] for i in range(len(allv)) if i not in combo]
        if abs(mean(tv) - mean(cv)) >= abs(obs) - 1e-9:
            cnt += 1
    return obs, cnt / math.comb(len(allv), k)

print("== exact permutation tests (C(8,4)=70 splits) ==")
for cap in ("MR", "IE", "TR", "KU", "ABS", "overall", "abst"):
    if cap == "overall":
        dc = [fm(REPORTS[n])["accuracy"] * 100 for n in CNAMES]
        dt = [fm(REPORTS[n])["accuracy"] * 100 for n in TNAMES]
    elif cap == "abst":
        dc = [fm(REPORTS[n])["abstentionRate"] * 100 for n in CNAMES]
        dt = [fm(REPORTS[n])["abstentionRate"] * 100 for n in TNAMES]
    else:
        dc = [fm(REPORTS[n])["perCapability"][cap]["accuracy"] * 100 for n in CNAMES]
        dt = [fm(REPORTS[n])["perCapability"][cap]["accuracy"] * 100 for n in TNAMES]
    obs, p = perm_p(dc, dt)
    print(f"  {cap:<8} delta {obs:+.2f}pp  p={p:.4f}")
print()

MR = [q for q in qids if DATA[CNAMES[0]][q]["capability"] == "MR"]
DERIV_MR = [q for q in MR if DERIV.search(DATA[CNAMES[0]][q]["question"])]
NONDERIV_MR = [q for q in MR if q not in set(DERIV_MR)]
print(f"MR {len(MR)}  derivable {len(DERIV_MR)}  non-derivable {len(NONDERIV_MR)}\n")

# --- question-level paired deterministic accuracy ---
def paired(qs, label):
    diffs = []
    wins = losses = ties = 0
    for q in qs:
        s = DATA[CNAMES[0]][q]
        vc = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in CNAMES]
        vt = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in TNAMES]
        if all(v is not None for v in vc + vt):
            d = sum(1.0 * v for v in vt) / 4 - sum(1.0 * v for v in vc) / 4
            diffs.append(d)
            if d > 1e-9:
                wins += 1
            elif d < -1e-9:
                losses += 1
            else:
                ties += 1
    if len(diffs) < 3:
        print(f"  {label}: too few deterministic questions (n={len(diffs)})")
        return
    n = len(diffs)
    m = sum(diffs) / n
    sd = (sum((x - m) ** 2 for x in diffs) / (n - 1)) ** 0.5
    se = sd / math.sqrt(n)
    t = m / se if se else 0.0
    def ncdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    p_t = 2 * (1 - ncdf(abs(t)))
    nd = wins + losses
    p_sign = 2 * sum(math.comb(nd, i) for i in range(min(wins, losses) + 1)) / (2 ** nd) if nd else 1.0
    print(f"  {label:<28} n={n:3d}  delta {m*100:+6.2f}pp  SE {se*100:.2f}pp  t={t:+.2f}  p={p_t:.4f}"
          f"   sign {wins}W/{losses}L/{ties}T p={p_sign:.4f}")

print("== question-level paired deterministic accuracy ==")
paired(MR, "MR all")
paired(DERIV_MR, "MR derivable (target)")
paired(NONDERIV_MR, "MR non-derivable (control)")
for cap in ("IE", "TR", "KU"):
    paired([q for q in qids if DATA[CNAMES[0]][q]["capability"] == cap], f"{cap} (guard)")
paired(qids, "ALL")
print()

# --- abstention ---
def abst_rate(names, qs):
    return sum(DATA[n][q]["abstained"] for n in names for q in qs) / (len(names) * len(qs)) * 100

print("== abstention rate ==")
for label, qs in (("MR all", MR), ("MR derivable", DERIV_MR), ("MR non-deriv", NONDERIV_MR),
                  ("ALL", qids)):
    c = abst_rate(CNAMES, qs)
    t = abst_rate(TNAMES, qs)
    print(f"  {label:<16} control {c:6.2f}%  treatment {t:6.2f}%  delta {t-c:+6.2f}pp")
print()

# --- McNemar on MR abstention ---
def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    obs = math.comb(n, min(b, c)) * (0.5 ** n)
    return min(1.0, sum(math.comb(n, i) * (0.5 ** n) for i in range(n + 1)
                        if math.comb(n, i) * (0.5 ** n) <= obs * 1.000001))

for label, qs in (("MR all", MR), ("MR derivable", DERIV_MR), ("ALL", qids)):
    b = c = 0
    for q in qs:
        ce = sum(DATA[n][q]["abstained"] for n in CNAMES)
        te = sum(DATA[n][q]["abstained"] for n in TNAMES)
        if ce > te:
            b += 1
        elif te > ce:
            c += 1
    print(f"  McNemar {label:<16} control-worse {b:3d}  treatment-worse {c:3d}  p={mcnemar_exact(b,c):.3e}")
print()

# --- per-question movement on derivable MR ---
print("== derivable MR: per-question movement ==")
moved_gain = [q for q in DERIV_MR
              if sum(1 for n in TNAMES if not DATA[n][q]["abstained"]) >
                 sum(1 for n in CNAMES if not DATA[n][q]["abstained"])]
moved_loss = [q for q in DERIV_MR
              if sum(1 for n in TNAMES if not DATA[n][q]["abstained"]) <
                 sum(1 for n in CNAMES if not DATA[n][q]["abstained"])]
print(f"  answered more under treatment: {len(moved_gain)}   less: {len(moved_loss)}")
net = 0.0
for q in DERIV_MR:
    s = DATA[CNAMES[0]][q]
    vc = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in CNAMES]
    vt = [verdict(s["question"], DATA[n][q]["answer"], DATA[n][q]["expected"]) for n in TNAMES]
    if all(v is not None for v in vc + vt):
        d = sum(1.0 * v for v in vt) / 4 - sum(1.0 * v for v in vc) / 4
        if abs(d) > 1e-9:
            net += d
            print(f"    {d*100:+6.1f}pp  {s['question'][:70]}  gt={str(s['expected'])[:22]}"
                  f"  ctrl_ans={str(DATA[CNAMES[0]][q]['answer'])[:18]}"
                  f"  treat_ans={str(DATA[TNAMES[0]][q]['answer'])[:18]}")
print(f"  net deterministic change on derivable MR: {net*100:+.2f}pp-of-questions"
      f"  ({net:+.2f} questions/run)")
print()

# --- guard: negative control (non-derivable MR should be untouched) ---
print("== negative control: non-derivable MR prompt must be byte-identical ==")
nb = nc = 0
for q in NONDERIV_MR:
    ce = sum(DATA[n][q]["abstained"] for n in CNAMES)
    te = sum(DATA[n][q]["abstained"] for n in TNAMES)
    if ce > te:
        nb += 1
    elif te > ce:
        nc += 1
print(f"  abstention McNemar on non-derivable MR: control-worse {nb}  treatment-worse {nc}"
      f"  p={mcnemar_exact(nb,nc):.3f}  (should be null)")
