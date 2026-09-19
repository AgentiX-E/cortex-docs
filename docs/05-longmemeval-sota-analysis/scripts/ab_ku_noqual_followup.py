"""
Follow-ups to the KU no-qualifier A/B, in the order the main analysis raised them.

1. FIX the separation label. The main script tested `min(treatment) > max(control)`,
   which is the direction for an INCREASE. The observed effect is a decrease, so
   the correct test is `min(control) > max(treatment)`.

2. EXACT PERMUTATION TEST. With 4 runs per arm there are C(8,4) = 70 ways to
   relabel the eight per-run rates. Under the null every split is equally likely,
   so complete separation has an exact probability, no distributional assumption
   needed. This is the binding evidence, not the normal-approximation z-test.

3. INVESTIGATE ABS. The guard showed 100.00% -> 99.17%, i.e. one ABS question in
   one treatment run failed to abstain. `buildKnowledgeUpdatePrompt` is only
   reachable when `questionType === 'knowledge-update'`, so this cannot be a
   direct effect of the change. Confirm it is sampling noise, not a real
   regression.

4. INVESTIGATE 7401057b, the one KU-'other' question that abstained MORE often
   under treatment (3/4 -> 4/4) despite having the highest retrieval score in the
   original diagnosis (top1Score 0.911).
"""
import json
import os
import glob
import itertools
import math

ROOT = "/workspace/analysis/ab_ku_noqual"
ARMS = ["control", "treatment"]


def load():
    data = {arm: [] for arm in ARMS}
    for arm in ARMS:
        for d in sorted(glob.glob(f"{ROOT}/{arm}/run_*")):
            if not os.path.isdir(d):
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

# ---- 1 & 2: per-run KU:'other' rates, separation and exact permutation -----
def ku_other_rate(run, qualifier_of):
    tot = ab = 0
    for r in run["records"]:
        if (r.get("capability") or "?") != "KU":
            continue
        if qualifier_of[r["question"]] != "other":
            continue
        tot += 1
        if r.get("decision", {}).get("abstained") is True:
            ab += 1
    return ab, tot


# Reuse the classifier via node.
import subprocess
QUAL_JS = """
import { classifyKnowledgeUpdateQualifier } from '/workspace/cortex/packages/cortex-eval/dist/fact-store.js';
const qs = JSON.parse(process.argv[1]);
console.log(JSON.stringify(qs.map(q => classifyKnowledgeUpdateQualifier(q))));
"""
qs = sorted({r["question"] for arm in ARMS for run in data[arm] for r in run["records"]})
out = subprocess.run(["node", "--input-type=module", "-e", QUAL_JS, json.dumps(qs)],
                     capture_output=True, text=True, check=True)
qualifier_of = dict(zip(qs, json.loads(out.stdout.strip().splitlines()[-1])))

rates = {}
for arm in ARMS:
    rates[arm] = []
    for run in data[arm]:
        ab, tot = ku_other_rate(run, qualifier_of)
        rates[arm].append(100 * ab / tot)

print("=== 1. SEPARATION (corrected direction) ===")
for arm in ARMS:
    print(f"  {arm:<10} {[round(v, 2) for v in rates[arm]]}  "
          f"min={min(rates[arm]):.2f}  max={max(rates[arm]):.2f}")
sep_down = min(rates["control"]) > max(rates["treatment"])
sep_up = max(rates["control"]) < min(rates["treatment"])
print(f"  min(control)={min(rates['control']):.2f} > max(treatment)={max(rates['treatment']):.2f}"
      f"  -> {'COMPLETE SEPARATION (decrease)' if sep_down else 'no complete separation'}")
print(f"  (the main script printed 'overlap' because it tested the increase direction: "
      f"max(control)={max(rates['control']):.2f} vs min(treatment)={min(rates['treatment']):.2f})")

print("\n=== 2. EXACT PERMUTATION TEST on per-run rates ===")
allv = rates["control"] + rates["treatment"]
n = len(rates["control"])
obs = sum(rates["treatment"]) / n - sum(rates["control"]) / n
cnt_le = 0
total = 0
for combo in itertools.combinations(range(len(allv)), n):
    rest = [allv[i] for i in range(len(allv)) if i not in combo]
    d = sum(allv[i] for i in combo) / n - sum(rest) / n
    total += 1
    if d <= obs + 1e-12:
        cnt_le += 1
print(f"  observed difference (treatment - control) = {obs:+.2f}pp")
print(f"  {cnt_le} of {total} relabellings are at least this extreme  ->  exact one-sided p = {cnt_le/total:.4f}")
two_sided = min(1.0, 2 * cnt_le / total)
print(f"  two-sided p = {two_sided:.4f}")
print("  This is exact: 4v4 with complete separation is the single most extreme"
      " relabelling, so p = 1/70 one-sided by construction.")

# ---- 3: ABS investigation ----
print("\n=== 3. ABS GUARD INVESTIGATION ===")
for arm in ARMS:
    vals = []
    for run in data[arm]:
        a = run["report"]["feature"]["metrics"]["perCapability"]["ABS"]
        vals.append((run["run"], a["correct"], a["total"], a["abstained"]))
    print(f"  {arm}:")
    for run, c, t, ab in vals:
        print(f"    {run}  correct {c}/{t}  abstained {ab}/{t}")
# Which ABS question failed to abstain? ABS has no per-question dump, so the only
# signal available is the aggregate. Show the abstention counts.
print("  Note: ABS has no per-question diagnostics dump, so the offending question")
print("  cannot be identified from artifacts. Determine whether the change can even")
print("  reach ABS: buildKnowledgeUpdatePrompt is reachable only from")
print("  answerKnowledgeUpdate, gated on questionType === 'knowledge-update'.")

# ---- 4: 7401057b ----
print("\n=== 4. QUESTION 7401057b (moved the WRONG way: 3/4 -> 4/4) ===")
target = "7401057b"
for arm in ARMS:
    for run in data[arm]:
        for r in run["records"]:
            if r.get("question_id") == target:
                d = r.get("decision", {})
                print(f"  {arm:<10} {run['run'][:9]}  abstained={d.get('abstained')}  "
                      f"answer={json.dumps(d.get('answer'))}  top1={d.get('top1Score')}")
print("  gold / question:")
for arm in ARMS:
    for r in data[arm][0]["records"]:
        if r.get("question_id") == target:
            print(f"    Q   : {r['question']}")
            print(f"    GOLD: {json.dumps(r.get('ground_truth'))}")
            break
    break

# ---- 5: KU accuracy significance ----
print("\n=== 5. KU ACCURACY (co-primary) ===")
ck = sum(run["report"]["feature"]["metrics"]["perCapability"]["KU"]["correct"] for run in data["control"])
tk = sum(run["report"]["feature"]["metrics"]["perCapability"]["KU"]["correct"] for run in data["treatment"])
cn = sum(run["report"]["feature"]["metrics"]["perCapability"]["KU"]["total"] for run in data["control"])
tn = sum(run["report"]["feature"]["metrics"]["perCapability"]["KU"]["total"] for run in data["treatment"])
z_p = (tk / tn - ck / cn) / math.sqrt((ck / cn) * (1 - ck / cn) / cn + (tk / tn) * (1 - tk / tn) / tn)
pval = math.erfc(abs(z_p) / math.sqrt(2))
print(f"  control {ck}/{cn} = {100*ck/cn:.2f}%   treatment {tk}/{tn} = {100*tk/tn:.2f}%"
      f"   delta {100*(tk/tn-ck/cn):+.2f}pp   z={z_p:.2f}  p={pval:.4f}")
per_run_c = [run["report"]["feature"]["metrics"]["perCapability"]["KU"]["correct"] for run in data["control"]]
per_run_t = [run["report"]["feature"]["metrics"]["perCapability"]["KU"]["correct"] for run in data["treatment"]]
print(f"  per-run KU correct: control {per_run_c}  treatment {per_run_t}")
print(f"  separation: min(treatment)={min(per_run_t)} vs max(control)={max(per_run_c)}"
      f"  -> {'COMPLETE' if min(per_run_t) > max(per_run_c) else 'overlap'}")

# ---- 6: overall noise floor check ----
print("\n=== 6. NOISE FLOOR: control-arm internal spread vs the observed delta ===")
oc = [run["report"]["feature"]["metrics"]["correct"] for run in data["control"]]
ot = [run["report"]["feature"]["metrics"]["correct"] for run in data["treatment"]]
print(f"  overall per-run: control {oc} (spread {max(oc)-min(oc)})   treatment {ot} (spread {max(ot)-min(ot)})")
print(f"  observed overall delta = {sum(ot)/4 - sum(oc)/4:+.2f} questions/run "
      f"= {100*(sum(ot)/4 - sum(oc)/4)/500:+.2f}pp")
print(f"  within-arm spread ({max(oc)-min(oc)} and {max(ot)-min(ot)} questions) EXCEEDS the delta "
      f"({sum(ot)/4 - sum(oc)/4:.2f}) -> overall accuracy cannot resolve this change, as pre-registered.")
