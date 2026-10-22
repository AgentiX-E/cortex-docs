"""
MR operand-expansion A/B analysis.

The fix (a45b32a) makes derivation questions expand into their OPERANDS
("my age", "my birthday") instead of activities. The mechanism endpoint is
therefore, for the two age-at-event questions whose "32" operand was never
recalled ("Alex born" = 32-21=11, "Rachel married" = 32+1=33), whether the real
age "32" now reaches the retrieved window, and whether the questions stop
abstaining.

"Real 32" is matched with age phrasings only; the raw substring "32" is rejected
because it matches the "12:32" timestamp noise that appears throughout every
retrieved context.

Guards: IE / KU / TR / ABS must be unchanged. The change is only reachable
through `answerSessions` (the MR path).
"""
import json
import glob
import os
import re
import itertools

ROOT = "/workspace/analysis/ab_mr_operand"
ARMS = ["control", "treatment"]
REQUIRED = [
    "benchmark-report.json",
    "benchmark-single-session-diagnostics.json",
    "benchmark-mr-diagnostics.json",
]

TARGETS = {
    "How old was I when Alex was born?": "11",
    "How many years will I be when my friend Rachel gets married?": "33",
}

# Real age-32 phrasings, deliberately excluding "12:32" timestamp noise.
REAL32 = re.compile(
    r"(?i)turned 32|i am 32|i'm 32|age 32|32 years old|32 last month|32 on february|"
    r"32 is (?:a|considered|young)|my 32nd|, 32,|at 32\b"
)


def load():
    data = {arm: [] for arm in ARMS}
    for arm in ARMS:
        for d in sorted(glob.glob(f"{ROOT}/{arm}/run_*")):
            if not os.path.isdir(d):
                continue
            if any(not os.path.exists(os.path.join(d, f)) for f in REQUIRED):
                continue
            report = json.load(open(os.path.join(d, "benchmark-report.json")))
            if report.get("questionCount") != 500:
                continue
            single = json.load(open(os.path.join(d, "benchmark-single-session-diagnostics.json")))
            mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
            for r in mr:
                r["capability"] = "MR"
            data[arm].append({"run": os.path.basename(d), "report": report,
                              "records": single + mr})
    return data


def norm(s):
    return re.sub(r"\s+", " ", str(s).lower().strip().rstrip("."))


def is_correct(ans, gold):
    if ans is None:
        return False
    a, g = norm(ans), norm(gold)
    if a == g:
        return True
    na = re.findall(r"[\d,]+(?:\.\d+)?", a)
    ng = re.findall(r"[\d,]+(?:\.\d+)?", g)
    return bool(na and ng and float(na[0].replace(",", "")) == float(ng[0].replace(",", "")))


data = load()
print(f"control: {len(data['control'])} runs   treatment: {len(data['treatment'])} runs")
assert len(data["control"]) == 4 and len(data["treatment"]) == 4, "expected 4v4"


# ---- mechanism endpoint: real "32" in retrieved + abstention per target ----
def target_stats(run):
    out = {}
    for r in run["records"]:
        if (r.get("capability") or "?") != "MR" or r["question"] not in TARGETS:
            continue
        ctx = str(r.get("decision", {}).get("retrieved") or "")
        dec = r.get("decision", {})
        out[r["question"]] = {
            "real32_retr": len(REAL32.findall(ctx)) > 0,
            "abstained": dec.get("abstained") is True,
            "correct": is_correct(dec.get("answer"), r["ground_truth"]),
            "answer": dec.get("answer"),
        }
    return out


print("\n=== PRIMARY: real \"32\" reached the retrieved window (per target, per run) ===")
per_run_reach = {arm: [] for arm in ARMS}
per_run_abst = {arm: [] for arm in ARMS}
per_run_correct = {arm: [] for arm in ARMS}
for arm in ARMS:
    for run in data[arm]:
        st = target_stats(run)
        reached = sum(1 for v in st.values() if v["real32_retr"])
        abst = sum(1 for v in st.values() if v["abstained"])
        correct = sum(1 for v in st.values() if v["correct"])
        per_run_reach[arm].append(reached)
        per_run_abst[arm].append(abst)
        per_run_correct[arm].append(correct)
        detail = "; ".join(
            f"{q[:30]}={'hit' if v['real32_retr'] else 'MISS'}/{'abst' if v['abstained'] else 'ans'}"
            for q, v in st.items()
        )
        print(f"  {arm:9} {run['run']}: reach {reached}/2  abst {abst}/2  correct {correct}/2   [{detail}]")

print("\n  === reach (of 2 targets) ===")
print(f"  control   {per_run_reach['control']}  mean {sum(per_run_reach['control'])/4:.2f}")
print(f"  treatment {per_run_reach['treatment']}  mean {sum(per_run_reach['treatment'])/4:.2f}")
print("\n  === abstained (of 2 targets) ===")
print(f"  control   {per_run_abst['control']}  mean {sum(per_run_abst['control'])/4:.2f}")
print(f"  treatment {per_run_abst['treatment']}  mean {sum(per_run_abst['treatment'])/4:.2f}")
print("\n  === correct (of 2 targets) ===")
print(f"  control   {per_run_correct['control']}  mean {sum(per_run_correct['control'])/4:.2f}")
print(f"  treatment {per_run_correct['treatment']}  mean {sum(per_run_correct['treatment'])/4:.2f}")

# exact permutation on "reach" and "correct" per-run
for label, c, t, direction in [
    ("reach", per_run_reach["control"], per_run_reach["treatment"], "increase"),
    ("abstained", per_run_abst["control"], per_run_abst["treatment"], "decrease"),
    ("correct", per_run_correct["control"], per_run_correct["treatment"], "increase"),
]:
    obs = (sum(t) - sum(c)) / 4 if direction == "increase" else (sum(c) - sum(t)) / 4
    pool = c + t
    cnt = 0
    for combo in itertools.combinations(range(8), 4):
        a = [pool[i] for i in combo]
        b = [pool[i] for i in range(8) if i not in combo]
        stat = (sum(b) - sum(a)) / 4 if direction == "increase" else (sum(a) - sum(b)) / 4
        if stat >= obs:
            cnt += 1
    print(f"\n  [{label}] exact permutation ({direction}): {cnt}/70 = {cnt/70:.4f}")

# ---- guards: IE/KU/TR/ABS accuracy and abstention (pooled) ----------------
print("\n=== GUARDS: per-capability accuracy (pooled 4 runs) ===")
for cap in ["IE", "KU", "TR", "ABS"]:
    row = {}
    for arm in ARMS:
        tot = ab = cor = 0
        for run in data[arm]:
            m = run["report"]["feature"]["metrics"]["perCapability"].get(cap, {})
            tot += m.get("total", 0)
            ab += m.get("abstained", 0)
            cor += m.get("correct", 0)
        row[arm] = (cor, tot, ab)
    c, t = row["control"], row["treatment"]
    print(f"  {cap}: control {c[0]}/{c[1]}={100*c[0]/c[1]:.2f}%  "
          f"treatment {t[0]}/{t[1]}={100*t[0]/t[1]:.2f}%  delta {100*(t[0]/t[1]-c[0]/c[1]):+.2f}pp")

# MR accuracy (co-primary descriptive)
print("\n=== MR accuracy (descriptive) ===")
for arm in ARMS:
    vals = [run["report"]["feature"]["metrics"]["perCapability"]["MR"]["correct"] for run in data[arm]]
    print(f"  {arm:9} {vals}  mean {sum(vals)/4:.2f}/121 = {100*sum(vals)/4/121:.2f}%")
