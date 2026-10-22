"""
MR derivation-routing A/B analysis.

The fix (a104ea0) re-routes four computation phrasings from the enumeration
prompt to the derivation prompt. The mechanism endpoint is therefore the MR
abstention rate on the MOVED questions — the MR questions whose classification
changed from 'enumeration' (under 4640c86) to 'derivation' (under a104ea0) —
compared between the control and treatment arms under the same-instant 4v4
protocol.

Why the moved set and not all MR: the fix is surgical; it cannot affect a
question whose classification did not change. Measuring only the moved set is
the attribution-clean endpoint, and a residual-0 attribution check verifies
that no non-moved question moved.

Guards: IE / KU / TR abstention and accuracy must be unchanged (the change is
only reachable through `answerSessions`, the MR path). Overall accuracy is
reported but is noise-floored and not the decision.
"""
import json
import glob
import os
import re
import subprocess
import itertools
import math

ROOT = "/workspace/analysis/ab_mr_derivation"
ARMS = ["control", "treatment"]
REQUIRED = [
    "benchmark-report.json",
    "benchmark-single-session-diagnostics.json",
    "benchmark-mr-diagnostics.json",
]

# The derivation regex as it existed at 4640c86 (control), copied verbatim.
OLD_DERIVATION = re.compile(
    r"\b(percentage|percent|average|mean|difference (?:in|between)|"
    r"how much (?:more|less|faster|earlier|older)|increase in|decrease in|"
    r"discount|cashback|minimum|maximum|how old was)\b",
    re.I,
)
# The four patterns ADDED by a104ea0.
NEW_ADDITIONS = re.compile(
    r"\b(how long (?:have|has) [a-z]+ been|how many (?:years|months|weeks|days) older|"
    r"how many (?:years|months) (?:old )?will [a-z]+ be when|exceed [\w ]+? by)\b",
    re.I,
)


def old_kind(q):
    return "derivation" if OLD_DERIVATION.search(q) else "enumeration"


def new_kind(q):
    if OLD_DERIVATION.search(q) or NEW_ADDITIONS.search(q):
        return "derivation"
    return "enumeration"


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


data = load()
print(f"control: {len(data['control'])} runs   treatment: {len(data['treatment'])} runs")
assert len(data["control"]) == 4 and len(data["treatment"]) == 4, "expected 4v4"

# ---- moved questions: classification changed under the new regex -----------
moved = []
all_mr_q = sorted({r["question"] for arm in ARMS for run in data[arm]
                   for r in run["records"] if (r.get("capability") or "?") == "MR"})
for q in all_mr_q:
    if old_kind(q) == "enumeration" and new_kind(q) == "derivation":
        moved.append(q)
print(f"\nMOVED questions (enumeration -> derivation): {len(moved)}")
for q in moved:
    print(f"  - {q}")

# ---- per-run abstention and correctness on the moved set -------------------
def moved_stats(run):
    tot = ab = correct = 0
    for r in run["records"]:
        if (r.get("capability") or "?") != "MR":
            continue
        if r["question"] not in moved:
            continue
        tot += 1
        if r.get("decision", {}).get("abstained") is True:
            ab += 1
        elif r.get("decision", {}).get("correct") is True:
            correct += 1
    return tot, ab, correct


print("\n=== PRIMARY: MR abstention on the moved set ===")
per_run_ab = {arm: [] for arm in ARMS}
per_run_correct = {arm: [] for arm in ARMS}
for arm in ARMS:
    for run in data[arm]:
        tot, ab, correct = moved_stats(run)
        per_run_ab[arm].append(ab)
        per_run_correct[arm].append(correct)
        print(f"  {arm:9} {run['run']}: {ab}/{tot} abstained, {correct}/{tot} correct")

c_ab, t_ab = per_run_ab["control"], per_run_ab["treatment"]
c_tot = t_tot = sum(moved_stats(r)[0] for r in data["control"]) // 4
print(f"\n  control   abst/run {c_ab}  (total moved = {c_tot} questions)")
print(f"  treatment abst/run {t_ab}")
print(f"  control   correct/run {per_run_correct['control']}")
print(f"  treatment correct/run {per_run_correct['treatment']}")

c_mean = sum(c_ab) / 4
t_mean = sum(t_ab) / 4
print(f"  abstention rate: control {c_mean:.2f}/run -> treatment {t_mean:.2f}/run  "
      f"delta {t_mean - c_mean:+.2f}/run")
print(f"  separation: min(control)={min(c_ab)} vs max(treatment)={max(t_ab)}", end="  -> ")
print("COMPLETE" if min(c_ab) > max(t_ab) else "OVERLAP")

# exact permutation test on per-run abstention counts
pool = c_ab + t_ab
obs = c_mean - t_mean  # decrease = positive
count = 0
for combo in itertools.combinations(range(8), 4):
    a = [pool[i] for i in combo]
    b = [pool[i] for i in range(8) if i not in combo]
    if (sum(a) - sum(b)) / 4 >= obs:
        count += 1
print(f"  exact permutation (one-sided, decrease): {count}/70 = {count/70:.4f}")

# co-primary: correctness on moved set
cc, tc = per_run_correct["control"], per_run_correct["treatment"]
print(f"\n=== CO-PRIMARY: MR correctness on the moved set ===")
print(f"  control   correct/run {cc}  mean {sum(cc)/4:.2f}")
print(f"  treatment correct/run {tc}  mean {sum(tc)/4:.2f}  delta {sum(tc)/4 - sum(cc)/4:+.2f}/run")

# ---- guards: IE / KU / TR abstention and accuracy --------------------------
print("\n=== GUARDS: per-capability abstention (pooled across 4 runs) ===")
def pooled_abstain(arm, cap):
    tot = ab = 0
    for run in data[arm]:
        for r in run["records"]:
            if (r.get("capability") or "?") != cap:
                continue
            tot += 1
            if r.get("decision", {}).get("abstained") is True:
                ab += 1
    return ab, tot


for cap in ["IE", "KU", "TR"]:
    ca, ct = pooled_abstain("control", cap)
    ta, tt = pooled_abstain("treatment", cap)
    print(f"  {cap}: control {ca}/{ct}={100*ca/ct:.2f}%  treatment {ta}/{tt}={100*ta/tt:.2f}%  "
          f"delta {100*(ta/tt - ca/ct):+.2f}pp")

# overall accuracy (descriptive)
print("\n=== OVERALL (descriptive, noise-floored) ===")
for arm in ARMS:
    reps = [run["report"]["feature"]["metrics"] for run in data[arm]]
    tot = sum(r["correct"] for r in reps)
    n = sum(r["total"] for r in reps)
    per_run = [r["correct"] for r in reps]
    print(f"  {arm:9}: {tot}/{n} = {100*tot/n:.2f}%   per-run {per_run}")
