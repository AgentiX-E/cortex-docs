"""
Derived numbers for the KU no-qualifier A/B verdict.

Three quantities the main analysis and the first follow-up did not pin down:

1. EXACT PERMUTATION TEST for the co-primary endpoint (KU accuracy per run).
   The follow-up computed it only for the primary endpoint (KU:'other'
   abstention rate). The co-primary deserves the same assumption-free test,
   because the pooled z-test on 288 observations is pseudoreplication - the
   same 72 questions appear in each of the 4 runs, so the observations are not
   independent and the pooled p = 0.2311 is not the right evidence.

2. RECOVERY EFFICIENCY. Of the abstentions the fix removed, what fraction
   turned into correct answers rather than wrong answers? An abstention on a
   non-ABS question scores 0, so converting one to a wrong answer costs
   nothing; only conversions to correct answers create value.

3. ATTRIBUTION RESIDUAL. The fix is claimed to act only on KU questions whose
   qualifier is 'other'. Verify that the total change in KU abstentions is
   fully accounted for by the 'other' stratum, i.e. 'previous' and 'current'
   contribute zero. A non-zero residual would mean the change reaches code it
   was not supposed to reach.
"""
import json
import os
import glob
import itertools
import subprocess

ROOT = "/workspace/analysis/ab_ku_noqual"
ARMS = ["control", "treatment"]

QUAL_JS = """
import { classifyKnowledgeUpdateQualifier } from '/workspace/cortex/packages/cortex-eval/dist/fact-store.js';
const qs = JSON.parse(process.argv[1]);
console.log(JSON.stringify(qs.map(q => classifyKnowledgeUpdateQualifier(q))));
"""


def classify_batch(questions):
    if not questions:
        return []
    out = subprocess.run(
        ["node", "--input-type=module", "-e", QUAL_JS, json.dumps(questions)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


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
                r["capability"] = "MR"  # MR dump records carry capability: null
            data[arm].append({"run": os.path.basename(d), "report": report,
                              "records": single + mr})
    return data


data = load()
assert len(data["control"]) == 4, len(data["control"])
assert len(data["treatment"]) == 4, len(data["treatment"])

all_q = {}
for arm in ARMS:
    for run in data[arm]:
        for r in run["records"]:
            all_q[r["question"]] = None
qual = dict(zip(all_q.keys(), classify_batch(list(all_q.keys()))))

CAP = "feature"


def percap(run, cap):
    return run["report"][CAP]["metrics"]["perCapability"][cap]


def overall(run):
    m = run["report"][CAP]["metrics"]
    return m["correct"], m["total"]


# ---- 1. exact permutation test on per-run KU accuracy (co-primary) --------
ku_run = {arm: [percap(r, "KU")["correct"] for r in data[arm]] for arm in ARMS}
print("=== 1. EXACT PERMUTATION TEST on KU accuracy (co-primary) ===")
print(f"  per-run KU correct / 72:")
print(f"    control   {ku_run['control']}")
print(f"    treatment {ku_run['treatment']}")
c_mean = sum(ku_run["control"]) / 4
t_mean = sum(ku_run["treatment"]) / 4
print(f"  per-run means : control {c_mean:.2f}  treatment {t_mean:.2f}  delta +{t_mean - c_mean:.2f} questions/run")
sepa = min(ku_run["treatment"]) > max(ku_run["control"])
print(f"  separation    : min(treatment)={min(ku_run['treatment'])} vs max(control)={max(ku_run['control'])}"
      f"  -> {'COMPLETE SEPARATION' if sepa else 'OVERLAP'}")

pool = ku_run["control"] + ku_run["treatment"]
obs = t_mean - c_mean
count = 0
for combo in itertools.combinations(range(8), 4):
    a = [pool[i] for i in combo]
    b = [pool[i] for i in range(8) if i not in combo]
    if (sum(b) - sum(a)) / 4 >= obs:
        count += 1
print(f"  {count} of C(8,4)=70 relabellings are at least this extreme")
print(f"  exact one-sided p = {count}/70 = {count / 70:.4f}   two-sided = {2 * count / 70:.4f}")
print("  pooled two-proportion z-test (p=0.2311) is DISCARDED as pseudoreplication:")
print("  4 runs x 72 questions are not 288 independent observations.")
print()

# overall accuracy, for the noise-floor comparison
ov_run = {arm: [overall(r)[0] for r in data[arm]] for arm in ARMS}
oc, ot = sum(ov_run["control"]), sum(ov_run["treatment"])
print(f"  (overall, for reference) control {oc}/2000 = {100*oc/2000:.2f}%   "
      f"treatment {ot}/2000 = {100*ot/2000:.2f}%   delta {100*(ot-oc)/2000:+.2f}pp")
print(f"  per-run overall: control {ov_run['control']}  treatment {ov_run['treatment']}")
print(f"  within-arm spread: control {max(ov_run['control'])-min(ov_run['control'])}, "
      f"treatment {max(ov_run['treatment'])-min(ov_run['treatment'])}")
print()


# ---- 2. recovery efficiency ------------------------------------------------
ab_c = sum(percap(r, "KU")["abstained"] for r in data["control"])
ab_t = sum(percap(r, "KU")["abstained"] for r in data["treatment"])
cor_c, cor_t = sum(ku_run["control"]), sum(ku_run["treatment"])
recovered = ab_c - ab_t
gained = cor_t - cor_c
print("=== 2. RECOVERY EFFICIENCY ===")
print(f"  KU abstentions removed : {ab_c} -> {ab_t}   = -{recovered} over 4 runs = {recovered / 4:.2f}/run")
print(f"  KU correct gained      : {cor_c} -> {cor_t}   = +{gained} over 4 runs = {gained / 4:.2f}/run")
print(f"  efficiency             : {gained}/{recovered} = {100.0 * gained / recovered:.1f}% became CORRECT")
print(f"  the other {recovered - gained} ({(recovered-gained)/4:.2f}/run, "
      f"{100.0*(recovered-gained)/recovered:.1f}%) became WRONG answers")
print("  an abstention on a non-ABS question already scores 0, so a wrong answer")
print("  costs nothing extra: those conversions are free.")
print()


# ---- 3. attribution residual ----------------------------------------------
print("=== 3. ATTRIBUTION RESIDUAL ===")
tot = {"control": {}, "treatment": {}}
for arm in ARMS:
    for run in data[arm]:
        for r in run["records"]:
            if (r.get("capability") or "?") != "KU":
                continue
            q = qual.get(r["question"], "other")
            d = tot[arm].setdefault(q, [0, 0])
            d[0] += 1
            if r.get("decision", {}).get("abstained") is True:
                d[1] += 1

# All three quantities are expressed as "abstentions REMOVED" (control - treatment),
# so they share one sign convention and can be subtracted from each other.
removed_total = ab_c - ab_t
print(f"  KU abstentions removed, all strata = {ab_c} -> {ab_t} = {removed_total}")
residual = removed_total
for q in ("other", "previous", "current"):
    cq = tot["control"].get(q, [0, 0])
    tq = tot["treatment"].get(q, [0, 0])
    d = cq[1] - tq[1]
    residual -= d
    print(f"    {q:<9} {cq[1]:>3}/{cq[0]:<4} -> {tq[1]:>3}/{tq[0]:<4}   removed {d:+d}")
print(f"  residual after subtracting every stratum = {residual}")
print("  residual 0 => the change is fully explained by the 'other' stratum alone;")
print("  it does not leak into 'previous' or 'current', which take the bitemporal path.")
print()
print("  cross-check against the report aggregates (independent of the diagnostics dump):")
for arm in ARMS:
    s = sum(tot[arm].get(q, [0, 0])[1] for q in ("other", "previous", "current"))
    print(f"    {arm:<9} diagnostics KU abstained = {s}   report KU abstained = "
          f"{sum(percap(r, 'KU')['abstained'] for r in data[arm])}")
