"""Offline proxy for the retrieval rank of un-recalled evidence sessions.

Cannot re-run embeddings offline, so this asks a cheaper question: is the missed
evidence session SEMANTICALLY CLOSE to the question at all? If it is lexically as
close as the recalled ones, the miss is a ranking/topK artefact and lifting topK
should recover it. If it is much further away, lifting topK is a waste of tokens
and the fix must instead improve the QUERY (expansion) or the session embedding.
"""
import json, re, math
from pathlib import Path
from collections import Counter

ROOT = Path("ab_deriv")
RUNS = [d for d in sorted((ROOT/"control").iterdir()) if d.is_dir()] + \
       [d for d in sorted((ROOT/"treatment").iterdir()) if d.is_dir()]
NAMES = [d.name for d in RUNS]

STOP = set("""a an the and or of to in for on with my me i you your it is are was were be been
this that these those as at from by have has had do does did can could would should will
any some more most other others than then there their they them he she his her about into
over under also very just not no yes what which who when where how many much did do does
i'm i've i'd was were am""".split())
TOKEN = re.compile(r"[a-z0-9']+")
def toks(s):
    return {t for t in TOKEN.findall(str(s).lower()) if t not in STOP and len(t) > 2}

def fp(t, n=80):
    return re.sub(r"\W+", "", str(t).lower())[:n]

load = lambda d: json.loads((d/"benchmark-mr-diagnostics.json").read_text())
DATA = {d.name: load(d) for d in RUNS}
by_q = {}
for name in NAMES:
    for x in DATA[name]:
        by_q.setdefault(x["question_id"], {})[name] = x

def overlap(q, sess):
    """Cosine similarity on content tokens, plus raw IDF-free lexical overlap."""
    A, B = toks(q), toks(sess)
    if not A or not B:
        return 0.0
    return len(A & B) / math.sqrt(len(A) * len(B))

recalled_ov, missed_ov = [], []
rows_detail = []
for qid, runs in by_q.items():
    x = runs[NAMES[0]]
    q = x["question"]
    ev = x.get("answer_sessions_content") or []
    if not ev:
        continue
    ret = (x["decision"] or {}).get("retrieved", "") or ""
    fpr = fp(ret, 10**7)
    for c in ev:
        ov = overlap(q, c)
        hit = fp(c) and fp(c) in fpr
        (recalled_ov if hit else missed_ov).append(ov)
        if not hit:
            rows_detail.append((ov, qid, q))

def stat(name, xs):
    if not xs:
        print(f"  {name}: n=0")
        return
    xs = sorted(xs)
    m = sum(xs)/len(xs)
    print(f"  {name:<26} n={len(xs):3d}  mean {m:.4f}  median {xs[len(xs)//2]:.4f}  "
          f"p90 {xs[int(len(xs)*.9)]:.4f}  max {xs[-1]:.4f}")

print("== lexical question/session overlap: recalled vs missed evidence sessions ==")
stat("RECALLED evidence sessions", recalled_ov)
stat("MISSED evidence sessions", missed_ov)
if recalled_ov and missed_ov:
    mr, mm = sum(recalled_ov)/len(recalled_ov), sum(missed_ov)/len(missed_ov)
    print(f"\n  ratio missed/recalled = {mm/mr:.3f}")
    print("  -> near 1.0 means the miss is a ranking artefact (lifting topK should work);")
    print("     well below 1.0 means the query never reaches these sessions (fix the query).")
print()

# how many MISSED sessions are lexically strong (i.e. SHOULD have been retrieved)?
thr = sorted(recalled_ov)[int(len(recalled_ov)*0.25)] if recalled_ov else 0
strong = [r for r in rows_detail if r[0] >= thr]
print(f"== missed sessions whose overlap is at/above the recalled 25th pct ({thr:.4f}) ==")
print(f"   {len(strong)}/{len(rows_detail)}  <- these are ranking/topK recoverable in principle")
print()
rows_detail.sort(reverse=True)
print("   strongest missed sessions (most likely recoverable by lifting topK):")
for ov, qid, q in rows_detail[:12]:
    print(f"     ov={ov:.4f}  {q[:78]}")
print()

# query-expansion effectiveness: does expansion add sessions beyond base topK?
print("== query-expansion contribution to the retrieved session count ==")
DATE = re.compile(r"^\[\d{4}/\d{2}/\d{2}")
def nsess(ret):
    return sum(1 for b in ret.split("\n\n") if DATE.match(b.strip()))
with_exp, no_exp = [], []
for qid, runs in by_q.items():
    x = runs[NAMES[0]]
    dec = x["decision"] or {}
    nq = len(dec.get("expansionQueries") or [])
    ret = dec.get("retrieved","") or ""
    (with_exp if nq else no_exp).append(nsess(ret))
stat("sessions when expansion ran", with_exp)
stat("sessions when expansion empty", no_exp)
nq_dist = Counter(len((runs[NAMES[0]]["decision"] or {}).get("expansionQueries") or [])
                  for runs in by_q.values())
print(f"  expansionQueries count distribution: {dict(sorted(nq_dist.items()))}")
