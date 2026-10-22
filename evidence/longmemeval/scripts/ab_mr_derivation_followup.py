"""
MR derivation-routing A/B — follow-up numbers.

The first pass computed the primary endpoint (moved-set abstention) but read
correctness from `decision.correct`, which the MR diagnostics dump does not
populate — correctness lives only in the report's per-capability aggregate.
This pass re-derives the co-primary from the authoritative report metric and
computes the exact permutation test, plus a per-question moved-set verdict using
an exact/numeric match against gold.
"""
import json
import glob
import os
import itertools
import re
from collections import defaultdict

ROOT = "/workspace/analysis/ab_mr_derivation"

# --- 1. MR accuracy + abstention per-run (authoritative report metric) ------
mr_correct = {"control": [], "treatment": []}
mr_abst = {"control": [], "treatment": []}
for arm in ("control", "treatment"):
    for d in sorted(glob.glob(f"{ROOT}/{arm}/run_*")):
        rep = json.load(open(os.path.join(d, "benchmark-report.json")))
        m = rep["feature"]["metrics"]["perCapability"]["MR"]
        mr_correct[arm].append(m["correct"])
        mr_abst[arm].append(m["abstained"])

c, t = mr_correct["control"], mr_correct["treatment"]
print("=== CO-PRIMARY: MR accuracy (per run, out of 121) ===")
print(f"  control   {c}  mean {sum(c)/4:.2f}")
print(f"  treatment {t}  mean {sum(t)/4:.2f}  delta +{sum(t)/4 - sum(c)/4:.2f}/run")
obs = sum(t) / 4 - sum(c) / 4
pool = c + t
cnt = 0
for combo in itertools.combinations(range(8), 4):
    a = [pool[i] for i in combo]
    b = [pool[i] for i in range(8) if i not in combo]
    if (sum(b) - sum(a)) / 4 >= obs:
        cnt += 1
print(f"  exact permutation (one-sided, increase): {cnt}/70 = {cnt/70:.4f}")
print(f"  separation: min(treatment)={min(t)} vs max(control)={max(c)}", end="  -> ")
print("COMPLETE" if min(t) > max(c) else "overlap at boundary (min treat == max control)")

print("\n=== MR abstention (per run) ===")
print(f"  control   {mr_abst['control']}  mean {sum(mr_abst['control'])/4:.2f}")
print(f"  treatment {mr_abst['treatment']}  mean {sum(mr_abst['treatment'])/4:.2f}")
recovered = sum(mr_abst["control"]) - sum(mr_abst["treatment"])
gained = sum(t) - sum(c)
print(f"  abstentions removed: {recovered} over 4 runs = {recovered/4:.2f}/run")
print(f"  correct gained    : {gained} over 4 runs = {gained/4:.2f}/run")
print(f"  recovery efficiency: {gained}/{recovered} = {100*gained/recovered:.1f}%")

# --- 2. moved-set per-question verdict (treatment) --------------------------
moved = {
    "How long have I been working in my current role?",
    "How many minutes did I exceed my target time by in the marathon?",
    "How many years older am I than when I graduated from college?",
    "How many years older is my grandma than me?",
    "How many years will I be when my friend Rachel gets married?",
}


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


print("\n=== moved-set per-question (treatment, 4 runs each) ===")
golds = {}
perq = defaultdict(lambda: {"correct": 0, "abst": 0, "answered": 0})
for d in sorted(glob.glob(f"{ROOT}/treatment/run_*")):
    mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
    for r in mr:
        if r["question"] in moved:
            golds[r["question"]] = r["ground_truth"]
            dec = r.get("decision", {})
            if dec.get("abstained"):
                perq[r["question"]]["abst"] += 1
            else:
                perq[r["question"]]["answered"] += 1
                if is_correct(dec.get("answer"), r["ground_truth"]):
                    perq[r["question"]]["correct"] += 1

for q in sorted(perq, key=lambda k: -perq[k]["correct"]):
    st = perq[q]
    print(f"  [{st['correct']}/4 correct, {st['abst']}/4 abstained, {st['answered']}/4 answered] "
          f"{q!r}  GOLD={golds[q]!r}")

# --- 3. control moved-set for contrast -------------------------------------
print("\n=== moved-set per-question (control, 4 runs each, for contrast) ===")
cperq = defaultdict(lambda: {"correct": 0, "abst": 0, "answered": 0})
for d in sorted(glob.glob(f"{ROOT}/control/run_*")):
    mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
    for r in mr:
        if r["question"] in moved:
            dec = r.get("decision", {})
            if dec.get("abstained"):
                cperq[r["question"]]["abst"] += 1
            else:
                cperq[r["question"]]["answered"] += 1
                if is_correct(dec.get("answer"), r["ground_truth"]):
                    cperq[r["question"]]["correct"] += 1
for q in sorted(cperq):
    st = cperq[q]
    print(f"  [{st['correct']}/4 correct, {st['abst']}/4 abstained, {st['answered']}/4 answered] {q!r}")
