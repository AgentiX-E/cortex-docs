#!/usr/bin/env python3
"""TR time-range A/B analysis: TR accuracy + eventLookup accuracy + guards."""
import json, glob, os, itertools
from collections import defaultdict

ROOT = "/workspace/analysis/ab_tr_timerange"
RUN_IDS = "/workspace/analysis/run-ids/ab_tr_timerange_run_ids.tsv"
CAPS = ["IE", "MR", "KU", "TR", "ABS"]

ids = {}
for line in open(RUN_IDS):
    p = line.rstrip().split("\t")
    if p[0] == "arm":
        continue
    ids[p[1]] = p[0]

def report_json(run_id):
    fs = glob.glob(f"{ROOT}/run_{run_id}/*/benchmark-report.json")
    return json.load(open(fs[0]))

def per_cap(run_id):
    rep = report_json(run_id)
    feat = rep["feature"]["metrics"]
    return feat, feat.get("perCapability", {})

# 1. TR accuracy per run (mechanism endpoint)
tr_correct = {"control": [], "treatment": []}
ov_correct = {"control": [], "treatment": []}
cap_abst = {c: {"control": [], "treatment": []} for c in CAPS}
cap_correct = {c: {"control": [], "treatment": []} for c in CAPS}

for run_id, arm in ids.items():
    feat, pc = per_cap(run_id)
    ov_correct[arm].append(feat.get("correct", 0))
    for c in CAPS:
        m = pc.get(c, {})
        cap_correct[c][arm].append(m.get("correct", 0))
        cap_abst[c][arm].append(m.get("abstained", 0))

def perm_p(ctrl, trt, direction="increase"):
    obs = sum(trt) / len(trt) - sum(ctrl) / len(ctrl)
    pool = ctrl + trt
    n = len(ctrl)
    cnt = 0
    total = 0
    for combo in itertools.combinations(range(len(pool)), n):
        a = [pool[i] for i in combo]
        b = [pool[i] for i in range(len(pool)) if i not in combo]
        total += 1
        delta = sum(b) / len(b) - sum(a) / len(a)
        if direction == "increase" and delta >= obs:
            cnt += 1
        elif direction == "decrease" and delta <= obs:
            cnt += 1
    return cnt, total

print("=== TR accuracy (mechanism endpoint) ===")
c, t = cap_correct["TR"]["control"], cap_correct["TR"]["treatment"]
print(f"  control   {c}  mean {sum(c)/4:.2f}")
print(f"  treatment {t}  mean {sum(t)/4:.2f}")
cnt, total = perm_p(c, t, "increase")
print(f"  delta +{(sum(t)-sum(c))/4:.2f}/run; exact permutation (increase): {cnt}/{total} = {cnt/total:.4f}")

print()
print("=== OVERALL accuracy ===")
c, t = ov_correct["control"], ov_correct["treatment"]
print(f"  control   {c}  mean {sum(c)/4:.2f} ({100*sum(c)/2000:.2f}%)")
print(f"  treatment {t}  mean {sum(t)/4:.2f} ({100*sum(t)/2000:.2f}%)")

print()
print("=== per-capability guard (control vs treatment, 4-run pooled) ===")
for cap in CAPS:
    cc = sum(cap_correct[cap]["control"])
    tc = sum(cap_correct[cap]["treatment"])
    ca = sum(cap_abst[cap]["control"])
    ta = sum(cap_abst[cap]["treatment"])
    tt = 4 * ({  # totals per run
        "IE": 150, "MR": 121, "KU": 72, "TR": 127, "ABS": 30
    }[cap])
    delta = (tc - cc) / 4
    print(f"  {cap:4}: correct {cc}/{tt}->{tc}/{tt} ({100*cc/tt:.2f}%->{100*tc/tt:.2f}%)  "
          f"abst {ca}->{ta}  delta {delta:+.2f}/run")

# 2. eventLookup accuracy (per-question, from diagnostics)
print()
print("=== eventLookup questions (per-question correctness) ===")

def load_single(run_id):
    fs = glob.glob(f"{ROOT}/run_{run_id}/*/benchmark-single-session-diagnostics.json")
    return json.load(open(fs[0]))

# classify eventLookup via a lightweight import of classifyTemporalQuestion from dist
import subprocess
JS = """import { classifyTemporalQuestion } from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';
const qs = JSON.parse(process.argv[1]);
console.log(JSON.stringify(qs.map(q => classifyTemporalQuestion(q))));"""

all_tr_q = set()
for run_id in ids:
    for r in load_single(run_id):
        if r.get("capability") == "TR":
            all_tr_q.add(r["question"])

qlist = sorted(all_tr_q)
out = subprocess.run(["node", "--input-type=module", "-e", JS, json.dumps(qlist)],
                     capture_output=True, text=True, check=True)
kind = dict(zip(qlist, json.loads(out.stdout.strip().splitlines()[-1])))
event_lookup_q = {q for q in qlist if kind[q] == "eventLookup"}
print(f"  eventLookup TR questions: {len(event_lookup_q)}")

el_correct = {q: {"control": 0, "treatment": 0} for q in event_lookup_q}
for run_id, arm in ids.items():
    for r in load_single(run_id):
        if r["question"] in event_lookup_q:
            if r.get("correct"):
                el_correct[r["question"]][arm] += 1

# per-question movement
moved_up = moved_down = same = 0
for q in event_lookup_q:
    c = el_correct[q]["control"]
    t = el_correct[q]["treatment"]
    if t > c:
        moved_up += 1
        print(f"  [UP   c{c}/4 -> t{t}/4] {q[:70]}")
    elif t < c:
        moved_down += 1
        print(f"  [DOWN c{c}/4 -> t{t}/4] {q[:70]}")
    else:
        same += 1

print(f"  eventLookup: {moved_up} up, {moved_down} down, {same} unchanged")
ctrl_tot = sum(el_correct[q]["control"] for q in event_lookup_q)
trt_tot = sum(el_correct[q]["treatment"] for q in event_lookup_q)
n_el = len(event_lookup_q) * 4
print(f"  eventLookup pooled: control {ctrl_tot}/{n_el} vs treatment {trt_tot}/{n_el}")
