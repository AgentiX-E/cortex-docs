#!/usr/bin/env python3
"""TR turnDate-anchor A/B analysis: TR accuracy (deterministic path) + sub-kind + guards."""
import json, glob, os, itertools, subprocess
from collections import defaultdict

ROOT = "/workspace/analysis/ab_tr_turnanchor"
RUN_IDS = "/workspace/analysis/run-ids/ab_tr_turnanchor_v2_run_ids.tsv"
CAPS = ["IE", "MR", "KU", "TR", "ABS"]
CAP_TOTALS = {"IE": 150, "MR": 121, "KU": 72, "TR": 127, "ABS": 30}

ids = {}
for line in open(RUN_IDS):
    p = line.rstrip().split("\t")
    if p[0] == "arm":
        continue
    ids[p[1]] = p[0]

def report_json(run_id):
    fs = glob.glob(f"{ROOT}/run_{run_id}/*/benchmark-report.json")
    return json.load(open(fs[0]))

def load_single(run_id):
    fs = glob.glob(f"{ROOT}/run_{run_id}/*/benchmark-single-session-diagnostics.json")
    return json.load(open(fs[0]))

# per-run capability metrics
cap_correct = {c: {"control": [], "treatment": []} for c in CAPS}
cap_abst = {c: {"control": [], "treatment": []} for c in CAPS}
ov_correct = {"control": [], "treatment": []}
for run_id, arm in ids.items():
    feat = report_json(run_id)["feature"]["metrics"]
    ov_correct[arm].append(feat.get("correct", 0))
    pc = feat.get("perCapability", {})
    for c in CAPS:
        m = pc.get(c, {})
        cap_correct[c][arm].append(m.get("correct", 0))
        cap_abst[c][arm].append(m.get("abstained", 0))

def perm_p(ctrl, trt, direction="increase"):
    obs = sum(trt) / len(trt) - sum(ctrl) / len(ctrl)
    pool = ctrl + trt
    n = len(ctrl)
    cnt = total = 0
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

print("=== TR accuracy (primary mechanism endpoint) ===")
c, t = cap_correct["TR"]["control"], cap_correct["TR"]["treatment"]
print(f"  control   {c}  mean {sum(c)/4:.2f}  ({100*sum(c)/508:.2f}%)")
print(f"  treatment {t}  mean {sum(t)/4:.2f}  ({100*sum(t)/508:.2f}%)")
obs = sum(t)/4 - sum(c)/4
cnt, total = perm_p(c, t, "increase")
print(f"  delta {obs:+.2f}/run; exact permutation (increase): {cnt}/{total} = {cnt/total:.4f}")
sep = "COMPLETE" if min(t) > max(c) else ("overlap at boundary" if min(t) == max(c) else "overlap")
print(f"  separation: min(treatment {min(t)}) vs max(control {max(c)}) -> {sep}")

print()
print("=== OVERALL accuracy ===")
c, t = ov_correct["control"], ov_correct["treatment"]
print(f"  control   {c}  mean {sum(c)/4:.2f} ({100*sum(c)/2000:.2f}%)")
print(f"  treatment {t}  mean {sum(t)/4:.2f} ({100*sum(t)/2000:.2f}%)")

print()
print("=== per-capability guard (4-run pooled) ===")
for cap in CAPS:
    cc = sum(cap_correct[cap]["control"])
    tc = sum(cap_correct[cap]["treatment"])
    ca = sum(cap_abst[cap]["control"])
    ta = sum(cap_abst[cap]["treatment"])
    tt = 4 * CAP_TOTALS[cap]
    delta = (tc - cc) / 4
    print(f"  {cap:4}: correct {cc}/{tt}->{tc}/{tt} ({100*cc/tt:.2f}%->{100*tc/tt:.2f}%)  "
          f"abst {ca}->{ta}  delta {delta:+.2f}/run")

# sub-kind attribution via classifyTemporalQuestion
print()
print("=== TR sub-kind attribution (turnDate affects deterministic kinds only) ===")
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

by_kind = defaultdict(lambda: defaultdict(lambda: {"c": 0, "t": 0}))
for run_id, arm in ids.items():
    for r in load_single(run_id):
        if r.get("capability") != "TR":
            continue
        k = kind[r["question"]]
        key = "c" if arm == "control" else "t"
        by_kind[k][r["question"]][key] += 1 if r.get("correct") else 0

for k in ["relative", "interval", "ordering", "eventLookup", "other"]:
    qs = by_kind.get(k, {})
    if not qs:
        continue
    ctot = sum(v["c"] for v in qs.values())
    ttot = sum(v["t"] for v in qs.values())
    n = len(qs) * 4
    affected = "YES (deterministic path)" if k in ("relative", "interval", "ordering") else "no"
    print(f"  {k:12}: {len(qs):2d} questions, control {ctot}/{n}, treatment {ttot}/{n}, "
          f"delta {ttot-ctot:+d}  [{affected}]")

# per-question movement within deterministic kinds (relative/interval/ordering)
print()
print("=== deterministic-kind per-question movement ===")
det_kinds = {"relative", "interval", "ordering"}
moved = defaultdict(lambda: {"control": 0, "treatment": 0})
for run_id, arm in ids.items():
    for r in load_single(run_id):
        if r.get("capability") != "TR":
            continue
        if kind[r["question"]] not in det_kinds:
            continue
        if r.get("correct"):
            moved[r["question"]][arm] += 1

up = down = 0
for q, st in sorted(moved.items(), key=lambda kv: (kv[1]["treatment"] - kv[1]["control"], kv[0])):
    d = st["treatment"] - st["control"]
    if d > 0:
        up += 1
        print(f"  [UP   c{st['control']}/4 -> t{st['treatment']}/4] {q[:75]}")
    elif d < 0:
        down += 1
        print(f"  [DOWN c{st['control']}/4 -> t{st['treatment']}/4] {q[:75]}")
print(f"  deterministic kinds: {up} up, {down} down")
