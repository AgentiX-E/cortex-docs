"""Offline attribution: are the un-retrieved MR evidence sessions a topK problem,
a ranking problem, or a truncation problem?

Cannot re-run retrieval offline (no embedding key, no local dataset), so this uses
the 8 already-collected runs instead. Embeddings are deterministic, so any question
whose evidence-recall state FLIPS across runs is sitting at a retrieval boundary;
a question that misses in 8/8 is failing systematically.
"""
import json, re, math
from pathlib import Path
from collections import Counter
import statistics as st

ROOT = Path("ab_deriv")
RUNS = [d for d in sorted((ROOT / "control").iterdir()) if d.is_dir()] + \
       [d for d in sorted((ROOT / "treatment").iterdir()) if d.is_dir()]
NAMES = [d.name for d in RUNS]

NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)")

def gtnum(s):
    m = NUM.search(str(s))
    return float(m.group(1).replace(",", "")) if m else None

def norm(a):
    return re.sub(r"\s+", " ", str(a).strip().lower())

def fingerprint(t, n=80):
    return re.sub(r"\W+", "", str(t).lower())[:n]

def load(d):
    return json.loads((d / "benchmark-mr-diagnostics.json").read_text())

DATA = {d.name: load(d) for d in RUNS}

# index rows by question_id
by_q = {}
for name in NAMES:
    for x in DATA[name]:
        by_q.setdefault(x["question_id"], {})[name] = x

print(f"MR questions: {len(by_q)}   runs: {len(NAMES)}")

def evidence_recalled(x):
    """Fraction of the gold evidence sessions present in the retrieved context."""
    dec = x["decision"] or {}
    ret = dec.get("retrieved", "") or ""
    ev = x.get("answer_sessions_content") or []
    if not ev:
        return None
    fp_ret = fingerprint(ret, 10 ** 7)
    found = sum(1 for c in ev if fingerprint(c) and fingerprint(c) in fp_ret)
    return found / len(ev)

# ---- per-question recall state across the 8 runs ----
states = {}
for qid, runs in by_q.items():
    if not any(runs[n].get("answer_sessions_content") for n in NAMES):
        continue
    frac = [evidence_recalled(runs[n]) for n in NAMES if n in runs]
    if not frac:
        continue
    states[qid] = frac

full = [q for q, f in states.items() if all(v >= 1 - 1e-9 for v in f)]
none = [q for q, f in states.items() if all(v <= 1e-9 for v in f)]
partial = [q for q, f in states.items() if q not in set(full) and q not in set(none)]
flipping = [q for q, f in states.items()
            if q not in set(full) and q not in set(none)
            and len({round(v, 6) for v in f}) > 1]

print(f"\n== evidence-recall stability across {len(NAMES)} runs ==")
print(f"  fully recalled in ALL runs : {len(full):3d}")
print(f"  fully missing in ALL runs  : {len(none):3d}")
print(f"  partial (some sessions)    : {len(partial):3d}")
print(f"    of which FLIP across runs: {len(flipping):3d}  <- retrieval boundary, fixable by rank/topK")
print(f"    stable-partial           : {len(partial)-len(flipping):3d}  <- systematic")

# ---- is the flip driven by query expansion? ----
print("\n== do the flipping questions differ in expansionQueries across runs? ==")
diff_q = 0
same_q = 0
for qid in flipping:
    qs = set()
    for n in NAMES:
        if n in by_q[qid]:
            dec = by_q[qid][n]["decision"] or {}
            qs.add(tuple(dec.get("expansionQueries") or []))
    if len(qs) > 1:
        diff_q += 1
    else:
        same_q += 1
print(f"  flipping questions whose expansionQueries DIFFER across runs: {diff_q}")
print(f"  flipping questions with IDENTICAL expansionQueries          : {same_q}")
if same_q > 0:
    print("  -> identical queries but different recall means the retrieval itself is")
    print("     non-deterministic (embedding batching/float), NOT an expansion issue.")

# ---- correctness vs recall state: where is the headroom? ----
print("\n== accuracy by evidence-recall state (deterministic verdicts only) ==")
def correct(x):
    dec = x["decision"] or {}
    gt, ans = x["ground_truth"], dec.get("answer")
    g, a = gtnum(gt), gtnum(ans)
    if g is not None:
        return a == g
    return norm(ans) == norm(gt)

for label, qs in (("full recall", full), ("partial", partial), ("no recall", none)):
    if not qs:
        continue
    rates = []
    for q in qs:
        vals = [correct(by_q[q][n]) for n in NAMES if n in by_q[q]]
        rates.append(sum(vals) / len(vals))
    print(f"  {label:<14} n={len(qs):3d}  mean accuracy {sum(rates)/len(rates)*100:6.2f}%")

# ---- retrieved length / truncation ----
print("\n== retrieved-context length and truncation ==")
lens = []
trunc = 0
for qid, runs in by_q.items():
    for n in NAMES:
        if n not in runs:
            continue
        ret = (runs[n]["decision"] or {}).get("retrieved", "") or ""
        lens.append(len(ret))
        if "[truncated]" in ret or "…" in ret:
            trunc += 1
lens.sort()
n = len(lens)
print(f"  n={n}  median={lens[n//2]}  p90={lens[int(n*.9)]}  p99={lens[int(n*.99)]}  max={lens[-1]}")
print(f"  contexts containing a truncation marker: {trunc}/{n}")

# ---- headroom: what could retrieval work buy? ----
print("\n== headroom from retrieval work ==")
worst = []
for qid in partial + none:
    vals = [correct(by_q[qid][n]) for n in NAMES if n in by_q[qid]]
    worst.append((sum(vals) / len(vals), qid))
wrong_partial = [q for q, v in worst if v < 0.5]
print(f"  questions with incomplete evidence recall: {len(partial)+len(none)}")
print(f"    of those, currently answered correctly <50% of runs: {len(wrong_partial)}")
print(f"    => upper bound if ALL of them were fixed: "
      f"{len(wrong_partial)/len(by_q)*100:.2f}pp MR, "
      f"{len(wrong_partial)/500*100:.2f}pp overall")
