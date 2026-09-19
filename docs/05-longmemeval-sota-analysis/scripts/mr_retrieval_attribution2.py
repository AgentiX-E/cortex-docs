"""Cross-validate the recall attribution with multiple fingerprint lengths, and
check whether sessionTopK is actually the binding constraint.

Truncation keeps the HEAD of a session and cuts the tail, so a fingerprint taken
from the head should still match. If a "missing" evidence session only matches at
a long fingerprint length, the earlier attribution was wrong (it was truncation,
not retrieval). Also count sessions per retrieved context against sessionTopK.
"""
import json, re
from pathlib import Path
from collections import Counter

ROOT = Path("ab_deriv")
RUNS = [d for d in sorted((ROOT / "control").iterdir()) if d.is_dir()] + \
       [d for d in sorted((ROOT / "treatment").iterdir()) if d.is_dir()]
NAMES = [d.name for d in RUNS]

def fp(t, n):
    return re.sub(r"\W+", "", str(t).lower())[:n]

load = lambda d: json.loads((d / "benchmark-mr-diagnostics.json").read_text())
DATA = {d.name: load(d) for d in RUNS}
by_q = {}
for name in NAMES:
    for x in DATA[name]:
        by_q.setdefault(x["question_id"], {})[name] = x

# ---- 1. multi-length fingerprint cross-validation ----
print("== recall state under different fingerprint lengths ==")
print("   (truncation keeps the head, so a head fingerprint should still match;")
print("    if counts DROP sharply at longer lengths, earlier attribution was too strict)")
SESS = re.compile(r"^\[\d{4}/\d{2}/\d{2}")
for L in (40, 80, 200, 500):
    full = none = part = 0
    for qid, runs in by_q.items():
        x = runs[NAMES[0]]
        ev = x.get("answer_sessions_content") or []
        if not ev:
            continue
        ret = (x["decision"] or {}).get("retrieved", "") or ""
        fpr = fp(ret, 10 ** 7)
        found = sum(1 for c in ev if fp(c, L) and fp(c, L) in fpr)
        if found == len(ev):
            full += 1
        elif found == 0:
            none += 1
        else:
            part += 1
    print(f"  len={L:4d}   full {full:3d}   partial {part:3d}   none {none:3d}")

# ---- 2. how many sessions are in each retrieved context? ----
print("\n== sessions per retrieved context (vs sessionTopK) ==")
counts = []
for qid, runs in by_q.items():
    ret = (runs[NAMES[0]]["decision"] or {}).get("retrieved", "") or ""
    n_sess = sum(1 for line in ret.split("\n") if SESS.match(line.strip()))
    counts.append(n_sess)
print(f"  n={len(counts)}  min={min(counts)}  median={sorted(counts)[len(counts)//2]}"
      f"  max={max(counts)}   distribution: {dict(sorted(Counter(counts).items()))}")

# ---- 3. length of the MISSED evidence sessions ----
print("\n== length of evidence sessions that were NOT recalled (heuristic: head fp len 80) ==")
missed_lens = []
recalled_lens = []
for qid, runs in by_q.items():
    x = runs[NAMES[0]]
    ev = x.get("answer_sessions_content") or []
    if not ev:
        continue
    ret = (x["decision"] or {}).get("retrieved", "") or ""
    fpr = fp(ret, 10 ** 7)
    for c in ev:
        (recalled_lens if fp(c, 80) in fpr else missed_lens).append(len(c))
if missed_lens:
    missed_lens.sort()
    print(f"  MISSED   n={len(missed_lens)}  median={missed_lens[len(missed_lens)//2]}"
          f"  max={missed_lens[-1]}")
recalled_lens.sort()
print(f"  RECALLED n={len(recalled_lens)}  median={recalled_lens[len(recalled_lens)//2]}"
      f"  max={recalled_lens[-1]}")
print("  -> if missed sessions are not systematically LONGER, truncation is not the cause.")

# ---- 4. headroom (fixed tuple order) ----
print("\n== headroom from retrieval work ==")
def gtnum(s):
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(s))
    return float(m.group(1).replace(",", "")) if m else None
def norm(a):
    return re.sub(r"\s+", " ", str(a).strip().lower())
def correct(x):
    dec = x["decision"] or {}
    g, a = gtnum(x["ground_truth"]), gtnum(dec.get("answer"))
    return (a == g) if g is not None else norm(dec.get("answer")) == norm(x["ground_truth"])

incomplete = []
for qid, runs in by_q.items():
    x = runs[NAMES[0]]
    ev = x.get("answer_sessions_content") or []
    if not ev:
        continue
    ret = (x["decision"] or {}).get("retrieved", "") or ""
    fpr = fp(ret, 10 ** 7)
    found = sum(1 for c in ev if fp(c, 80) and fp(c, 80) in fpr)
    if found < len(ev):
        rate = sum(correct(runs[n]) for n in NAMES if n in runs) / len(runs)
        incomplete.append((rate, qid, found, len(ev)))
incomplete.sort()
low = [t for t in incomplete if t[0] < 0.5]
print(f"  questions with incomplete evidence recall: {len(incomplete)}")
print(f"    answered correctly <50% of runs: {len(low)}")
print(f"    => UPPER BOUND if all fixed: {len(low)/len(by_q)*100:.2f}pp MR, "
      f"{len(low)/500*100:.2f}pp overall")
print("  (an upper bound only: fixing retrieval does not guarantee a correct answer)")
print()
print("  the incomplete-recall questions, worst first:")
for rate, qid, found, tot in incomplete:
    q = by_q[qid][NAMES[0]]["question"]
    print(f"    {rate*100:5.1f}%  {found}/{tot} sessions  {q[:72]}")
