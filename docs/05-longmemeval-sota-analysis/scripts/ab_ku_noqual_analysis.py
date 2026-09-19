"""
KU no-qualifier A/B analysis.

PRIMARY ENDPOINT (mechanism)
    KU abstention rate on questions `classifyKnowledgeUpdateQualifier` labels
    'other'. Control baseline 14.89%.

    This is a mechanism endpoint by design. It counts a decision the prompt
    directly controls, not an accuracy outcome that also depends on retrieval
    and on the judge, so it is denoised with respect to the sampling that
    dominates overall accuracy.

CO-PRIMARY
    KU accuracy (baseline 53.0/72 = 73.6%).

WHY OVERALL ACCURACY IS NOT THE DECISION VARIABLE
    Expected movement is ~7 recovered abstentions per run out of 500, i.e.
    ~+0.7pp even at a 50% recovery rate. The between-window drift measured for
    byte-identical code is ~1.7-2.1pp, so overall accuracy cannot resolve this
    change. It is reported with a Wilson 95% interval as a descriptive estimate
    only.

GUARD
    IE / MR / TR / ABS should be structurally unchanged: `buildKnowledgeUpdatePrompt`
    is reachable only from `answerKnowledgeUpdate`, which `benchmark.ts` calls
    only when `questionType === 'knowledge-update'`.

CONFOUND, STATED
    The treatment arm also carries the `retryableFetch` per-attempt deadline
    (commit 4640c86). That change only bounds a request that would otherwise
    hang and does not alter the LLM call pattern, so it is expected to be inert;
    it is nonetheless a confound and is stated rather than hidden.

The qualifier classifier is imported from the BUILT `fact-store.js`, and it is
byte-identical between the two arms (verified: `fact-store.ts` is untouched by
either commit), so the split cannot drift.
"""
import json
import math
import os
import glob
import subprocess
import sys

ROOT = "/workspace/analysis/ab_ku_noqual"
ARMS = ["control", "treatment"]
REQUIRED = [
    "benchmark-report.json",
    "benchmark-single-session-diagnostics.json",
    "benchmark-mr-diagnostics.json",
]

# --- qualifier classification, delegated to the shipped build ---------------
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


def wilson(k, n, z=1.959964):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - s) / d, (c + s) / d)


def two_prop_z(k1, n1, k2, n2):
    """Two-proportion z-test. Returns (z, two-sided p)."""
    if n1 == 0 or n2 == 0:
        return (float("nan"), float("nan"))
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p2 - p1) / se
    pval = math.erfc(abs(z) / math.sqrt(2))
    return (z, pval)


def welch_t(a, b):
    """Welch t-test on two lists. Returns (t, df, two-sided p)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return (float("nan"), float("nan"), float("nan"))
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return (0.0, float("nan"), 1.0)
    t = (mb - ma) / se
    df = (va / na + vb / nb) ** 2 / (
        (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    )
    # Normal approximation to Student t; n is small (4 per arm) so this is
    # reported as indicative, and the exact per-run enumeration below is the
    # binding evidence.
    pval = math.erfc(abs(t) / math.sqrt(2))
    return (t, df, pval)


# --- load -------------------------------------------------------------------
def load():
    data = {arm: [] for arm in ARMS}
    for arm in ARMS:
        for d in sorted(glob.glob(f"{ROOT}/{arm}/run_*")):
            if not os.path.isdir(d):
                continue
            if any(not os.path.exists(os.path.join(d, f)) for f in REQUIRED):
                print(f"SKIP {d}: missing artifacts", file=sys.stderr)
                continue
            report = json.load(open(os.path.join(d, "benchmark-report.json")))
            if report.get("questionCount") != 500:
                print(f"SKIP {d}: questionCount != 500", file=sys.stderr)
                continue
            single = json.load(open(os.path.join(d, "benchmark-single-session-diagnostics.json")))
            mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
            for r in mr:
                r["capability"] = "MR"  # MR dump records carry capability: null
            data[arm].append({"run": os.path.basename(d), "report": report,
                              "records": single + mr})
    return data


data = load()
for arm in ARMS:
    print(f"{arm}: {len(data[arm])} runs loaded")

# --- per-run stats ----------------------------------------------------------
# Collect every distinct question once so the classifier is invoked in one batch.
all_q = {}
for arm in ARMS:
    for run in data[arm]:
        for r in run["records"]:
            all_q[r["question"]] = None
qual = dict(zip(all_q.keys(), classify_batch(list(all_q.keys()))))

for arm in ARMS:
    for run in data[arm]:
        st = {}
        for r in run["records"]:
            cap = r.get("capability") or "?"
            s = st.setdefault(cap, {"total": 0, "abstained": 0})
            s["total"] += 1
            if r.get("decision", {}).get("abstained") is True:
                s["abstained"] += 1
            if cap == "KU":
                q = qual[r["question"]]
                t = st.setdefault(f"KU:{q}", {"total": 0, "abstained": 0})
                t["total"] += 1
                if r.get("decision", {}).get("abstained") is True:
                    t["abstained"] += 1
        run["stats"] = st
        # Per-question KU-'other' abstention, for the movement table.
        run["ku_other"] = {
            r["question_id"]: bool(r.get("decision", {}).get("abstained") is True)
            for r in run["records"]
            if (r.get("capability") or "?") == "KU" and qual[r["question"]] == "other"
        }
        rep = run["report"]["feature"]["metrics"]
        run["overall"] = (rep["correct"], rep["total"])
        run["percap_correct"] = {
            k: (v["correct"], v["total"], v["abstained"])
            for k, v in rep["perCapability"].items()
        }


def pooled(arm, key):
    tot = sum(run["stats"][key]["total"] for run in data[arm] if key in run["stats"])
    ab = sum(run["stats"][key]["abstained"] for run in data[arm] if key in run["stats"])
    return ab, tot


def pooled_correct(arm, cap):
    k = sum(run["percap_correct"][cap][0] for run in data[arm])
    n = sum(run["percap_correct"][cap][1] for run in data[arm])
    ab = sum(run["percap_correct"][cap][2] for run in data[arm])
    return k, n, ab


print("\n=== POOLED ABSTENTION RATE BY GROUP (4 runs per arm) ===")
print(f"{'group':<14} {'control':<18} {'treatment':<18} {'delta':>9}  95% CI on delta(pp)   z       p")
rows = ["KU:other", "KU:previous", "KU:current", "IE", "MR", "TR"]
for key in rows:
    if key not in data["control"][0]["stats"]:
        continue
    c_ab, c_n = pooled("control", key)
    t_ab, t_n = pooled("treatment", key)
    z, p = two_prop_z(c_ab, c_n, t_ab, t_n)
    rc, rt = c_ab / c_n, t_ab / t_n
    lo_c, hi_c = wilson(c_ab, c_n)
    lo_t, hi_t = wilson(t_ab, t_n)
    print(
        f"{key:<14} {c_ab:>3}/{c_n:<3}={100*rc:6.2f}%  {t_ab:>3}/{t_n:<3}={100*rt:6.2f}%  "
        f"{100*(rt-rc):+8.2f}pp   "
        f"[{100*(lo_t-hi_c):+.2f}, {100*(hi_t-lo_c):+.2f}]  {z:+6.2f}  {p:.4f}"
    )

print("\n=== PER-RUN KU:'other' ABSTENTION (the primary endpoint) ===")
for arm in ARMS:
    vals = []
    for run in data[arm]:
        s = run["stats"]["KU:other"]
        vals.append((run["run"], s["abstained"], s["total"], 100 * s["abstained"] / s["total"]))
    print(f"  {arm:<10} " + "  ".join(f"{a}/{b} ({c:.2f}%)" for _, a, b, c in vals))
    print(f"  {'':<10} mean={sum(v[3] for v in vals)/len(vals):.2f}%  "
          f"min={min(v[3] for v in vals):.2f}%  max={max(v[3] for v in vals):.2f}%  "
          f"spread={max(v[3] for v in vals)-min(v[3] for v in vals):.2f}pp")

c_rates = [100 * r["stats"]["KU:other"]["abstained"] / r["stats"]["KU:other"]["total"]
           for r in data["control"]]
t_rates = [100 * r["stats"]["KU:other"]["abstained"] / r["stats"]["KU:other"]["total"]
           for r in data["treatment"]]
t_stat, df, t_p = welch_t(c_rates, t_rates)
print(f"\n  Welch t on per-run rates: t={t_stat:.3f}  df={df:.2f}  p(approx)={t_p:.4f}")
print(f"  Per-run paired deltas (each control run minus treatment-run mean):")
print(f"    control   : {[round(x,2) for x in c_rates]}  mean={sum(c_rates)/4:.2f}%")
print(f"    treatment : {[round(x,2) for x in t_rates]}  mean={sum(t_rates)/4:.2f}%")
print(f"    separation: min(treatment)={min(t_rates):.2f}% vs max(control)={max(c_rates):.2f}%"
      f"  -> {'COMPLETE SEPARATION' if min(t_rates) > max(c_rates) else 'overlap'}")

print("\n=== ACCURACY BY CAPABILITY (pooled, from the report) ===")
print(f"{'cap':<6} {'control':<20} {'treatment':<20} {'delta':>9}")
for cap in ["IE", "MR", "KU", "TR", "ABS"]:
    ck, cn, cab = pooled_correct("control", cap)
    tk, tn, tab = pooled_correct("treatment", cap)
    print(f"{cap:<6} {ck:>4}/{cn:<4}={100*ck/cn:6.2f}% (ab {cab:>3})  "
          f"{tk:>4}/{tn:<4}={100*tk/tn:6.2f}% (ab {tab:>3})  {100*(tk/tn-ck/cn):+8.2f}pp")

ck, cn = sum(r["overall"][0] for r in data["control"]), sum(r["overall"][1] for r in data["control"])
tk, tn = sum(r["overall"][0] for r in data["treatment"]), sum(r["overall"][1] for r in data["treatment"])
lo_c, hi_c = wilson(ck, cn)
lo_t, hi_t = wilson(tk, tn)
print(f"\nOVERALL  control {ck}/{cn} = {100*ck/cn:.2f}% [{100*lo_c:.2f}, {100*hi_c:.2f}]"
      f"   treatment {tk}/{tn} = {100*tk/tn:.2f}% [{100*lo_t:.2f}, {100*hi_t:.2f}]"
      f"   delta {100*(tk/tn-ck/cn):+.2f}pp")
print("  per-run overall: control  " + ", ".join(str(r["overall"][0]) for r in data["control"]))
print("                   treatment " + ", ".join(str(r["overall"][0]) for r in data["treatment"]))

# --- per-question movement --------------------------------------------------
print("\n=== PER-QUESTION MOVEMENT on KU:'other' (times abstained out of 4) ===")
ctrl_q = {}
for run in data["control"]:
    for qid, ab in run["ku_other"].items():
        ctrl_q.setdefault(qid, []).append(ab)
treat_q = {}
for run in data["treatment"]:
    for qid, ab in run["ku_other"].items():
        treat_q.setdefault(qid, []).append(ab)

moved = []
for qid in sorted(set(ctrl_q) | set(treat_q)):
    c = sum(ctrl_q.get(qid, []))
    t = sum(treat_q.get(qid, []))
    if c != t:
        moved.append((qid, c, t, t - c))
moved.sort(key=lambda x: x[3])
print(f"{'qid':<12} {'ctrl abstain/4':>15} {'treat abstain/4':>16} {'change':>8}")
for qid, c, t, d in moved:
    print(f"{qid:<12} {c:>15} {t:>16} {d:>+8}")
print(f"\n  questions whose abstention count changed: {len(moved)}")
print(f"  net change in abstentions: {sum(d for _, _, _, d in moved):+d}")

# Did the recovered answers become correct?
print("\n=== DID THE RECOVERED ANSWERS BECOME CORRECT? ===")
gold = {}
for run in data["control"] + data["treatment"]:
    for r in run["records"]:
        if (r.get("capability") or "?") == "KU":
            gold[r["question_id"]] = r.get("ground_truth")
recovered = correct = 0
for qid, c, t, d in moved:
    if d < 0:  # abstained less often under treatment
        recovered += 1
print(f"  questions that moved away from abstention: {recovered}")
# Correctness per run: count KU correct from the report per capability.
print("  (per-question correctness is not in the diagnostics dump; KU accuracy")
print("   above is the authoritative correctness measure)")
