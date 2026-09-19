"""
MR DCG session-scoring A/B analysis.

Control = bc687b9 (max-turn session scoring), treatment = 51b573f (rank-discounted
DCG). The change only affects the MR turn-recall channel, so the mechanism
endpoint is MR accuracy + MR abstention; IE/KU/TR/ABS must be unchanged.

Per-run MR accuracy is compared with the exact permutation test (4v4 -> 70
relabellings). Overall accuracy is reported descriptively and is noise-floored.
"""
import json
import glob
import os
import itertools

ROOT = "/workspace/analysis/ab_mr_dcg"
ARMS = ["control", "treatment"]
REQUIRED = [
    "benchmark-report.json",
    "benchmark-single-session-diagnostics.json",
    "benchmark-mr-diagnostics.json",
]


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
            data[arm].append({"run": os.path.basename(d), "report": report})
    return data


def perm_test(c, t, direction="increase"):
    obs = (sum(t) - sum(c)) / 4 if direction == "increase" else (sum(c) - sum(t)) / 4
    pool = c + t
    cnt = 0
    for combo in itertools.combinations(range(8), 4):
        a = [pool[i] for i in combo]
        b = [pool[i] for i in range(8) if i not in combo]
        stat = (sum(b) - sum(a)) / 4 if direction == "increase" else (sum(a) - sum(b)) / 4
        if stat >= obs:
            cnt += 1
    return obs, cnt


data = load()
print(f"control: {len(data['control'])} runs   treatment: {len(data['treatment'])} runs")
assert len(data["control"]) == 4 and len(data["treatment"]) == 4

for cap in ["MR"]:
    c = [r["report"]["feature"]["metrics"]["perCapability"][cap]["correct"] for r in data["control"]]
    t = [r["report"]["feature"]["metrics"]["perCapability"][cap]["correct"] for r in data["treatment"]]
    ca = [r["report"]["feature"]["metrics"]["perCapability"][cap]["abstained"] for r in data["control"]]
    ta = [r["report"]["feature"]["metrics"]["perCapability"][cap]["abstained"] for r in data["treatment"]]
    print(f"\n=== {cap} accuracy (per run, /121) ===")
    print(f"  control   {c}  mean {sum(c)/4:.2f}")
    print(f"  treatment {t}  mean {sum(t)/4:.2f}  delta {sum(t)/4 - sum(c)/4:+.2f}/run")
    obs, cnt = perm_test(c, t, "increase")
    print(f"  exact permutation (increase): {cnt}/70 = {cnt/70:.4f}")
    print(f"=== {cap} abstained (per run) ===")
    print(f"  control   {ca}  mean {sum(ca)/4:.2f}")
    print(f"  treatment {ta}  mean {sum(ta)/4:.2f}  delta {sum(ta)/4 - sum(ca)/4:+.2f}/run")

print("\n=== GUARDS: per-capability accuracy (pooled) ===")
for cap in ["IE", "KU", "TR", "ABS"]:
    row = {}
    for arm in ARMS:
        tot = ab = cor = 0
        for r in data[arm]:
            m = r["report"]["feature"]["metrics"]["perCapability"].get(cap, {})
            tot += m.get("total", 0)
            ab += m.get("abstained", 0)
            cor += m.get("correct", 0)
        row[arm] = (cor, tot)
    c, t = row["control"], row["treatment"]
    print(f"  {cap}: control {c[0]}/{c[1]}={100*c[0]/c[1]:.2f}%  "
          f"treatment {t[0]}/{t[1]}={100*t[0]/t[1]:.2f}%  delta {100*(t[0]/t[1]-c[0]/c[1]):+.2f}pp")

print("\n=== OVERALL (descriptive) ===")
for arm in ARMS:
    reps = [r["report"]["feature"]["metrics"] for r in data[arm]]
    tot = sum(r["correct"] for r in reps)
    n = sum(r["total"] for r in reps)
    per = [r["correct"] for r in reps]
    print(f"  {arm:9}: {tot}/{n} = {100*tot/n:.2f}%  per-run {per}")
