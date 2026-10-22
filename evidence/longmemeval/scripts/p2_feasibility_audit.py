#!/usr/bin/env python3
"""P2 feasibility audit: does the correct eventLookup turn sit inside the
resolveTimeRange window but outside the retrieved top-k? If so, a date-range
filter arm can recover it; if not, P2 is doomed like reorderByDateProximity."""
import json, glob, os, re, subprocess
from collections import defaultdict

ROOT = "/workspace/analysis/ab_tr_turnanchor"
RUN_IDS = "/workspace/analysis/run-ids/ab_tr_turnanchor_v2_run_ids.tsv"

ids = {}
for line in open(RUN_IDS):
    p = line.rstrip().split("\t")
    if p[0] == "arm":
        continue
    ids[p[1]] = p[0]

def load_single(run_id):
    fs = glob.glob(f"{ROOT}/run_{run_id}/*/benchmark-single-session-diagnostics.json")
    return json.load(open(fs[0]))

# Use the SHIPPED engine for classify + resolveTimeRange (nothing reimplemented).
JS = """import { classifyTemporalQuestion, resolveTimeRange } from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';
const qs = JSON.parse(process.argv[1]);
const out = qs.map(q => {
  const kind = classifyTemporalQuestion(q);
  return { kind };
});
console.log(JSON.stringify(out));"""

all_tr = {}
for run_id in ids:
    for r in load_single(run_id):
        if r.get("capability") == "TR":
            all_tr[r["question"]] = r

qlist = sorted(all_tr.keys())
out = subprocess.run(["node", "--input-type=module", "-e", JS, json.dumps(qlist)],
                     capture_output=True, text=True, check=True)
kinds = dict(zip(qlist, [o["kind"] for o in json.loads(out.stdout.strip().splitlines()[-1])]))
event_q = [q for q in qlist if kinds[q] == "eventLookup"]
print(f"eventLookup TR questions: {len(event_q)}")

# resolveTimeRange per eventLookup question
JS2 = """import { resolveTimeRange } from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';
const items = JSON.parse(process.argv[1]);
console.log(JSON.stringify(items.map(([q, d]) => resolveTimeRange(q, d))));"""
qdate_pairs = []
for q in event_q:
    r = all_tr[q]
    qd = (r.get("question_date") or "").split(" ")[0]
    qdate_pairs.append([q, qd])
out2 = subprocess.run(["node", "--input-type=module", "-e", JS2, json.dumps(qdate_pairs)],
                      capture_output=True, text=True, check=True)
ranges = json.loads(out2.stdout.strip().splitlines()[-1])
qrange = dict(zip(event_q, ranges))

HDR = re.compile(r"\[(\d{4}/\d{2}/\d{2})")
def header_dates(ctx):
    return HDR.findall(ctx)

# For each eventLookup question, find whether the gold entity appears in the
# retrieved context and, when it does, whether its turn header date is in-window.
def in_window(date, rng):
    if not rng:
        return None
    return rng["start"] <= date <= rng["end"]

summary = defaultdict(lambda: {"anchor": 0, "gold_in_retrieved": 0, "correct_turn_in_window": 0,
                               "correct_turn_out_window": 0, "correct_turn_absent": 0})
for q in event_q:
    r = all_tr[q]
    rng = qrange[q]
    if not rng:
        continue
    summary[q]["anchor"] += 1
    ctx = str((r.get("decision") or {}).get("retrieved") or "")
    gold = str(r.get("ground_truth") or "")
    # locate a turn whose text contains the gold's leading alphanumeric token
    token = re.sub(r"[^a-zA-Z0-9 ]", " ", gold).split()[0] if gold else ""
    found_in_ctx = False
    found_in_window = False
    if token and len(token) >= 3:
        for m in re.finditer(re.escape(token), ctx, re.IGNORECASE):
            # walk back to the nearest header date before this match
            prefix = ctx[: m.start()]
            hdrs = HDR.findall(prefix)
            if hdrs:
                d = hdrs[-1]
                found_in_ctx = True
                if in_window(d, rng):
                    found_in_window = True
                    break
    summary[q]["gold_in_retrieved"] += 1 if found_in_ctx else 0
    if not found_in_ctx:
        summary[q]["correct_turn_absent"] += 1
    elif found_in_window:
        summary[q]["correct_turn_in_window"] += 1
    else:
        summary[q]["correct_turn_out_window"] += 1

print()
print("=== eventLookup questions with a resolvable anchor ===")
for q in sorted(summary):
    s = summary[q]
    print(f"  [{s['gold_in_retrieved'] and 'gold-in-ctx' or 'gold-absent'}] "
          f"range={qrange[q]}  Q={q[:60]}")
print()
n = len(summary)
inwin = sum(s["correct_turn_in_window"] for s in summary.values())
outwin = sum(s["correct_turn_out_window"] for s in summary.values())
absent = sum(s["correct_turn_absent"] for s in summary.values())
print(f"anchored eventLookup: {n}")
print(f"  gold turn ABSENT from retrieved: {absent}")
print(f"  gold turn in retrieved, header date IN window:  {inwin}")
print(f"  gold turn in retrieved, header date OUT of window: {outwin}")
print()
print("P2 can only help the 'absent' bucket (widen recall + date filter) — and only")
print("if the turn is absent for date reasons, not semantic reasons.")
