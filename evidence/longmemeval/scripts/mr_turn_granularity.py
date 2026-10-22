"""Decisive offline test for the turn-level retrieval hypothesis.

Sessions are embedded as ONE vector over the whole session, so a session whose
head is off-topic gets a diluted centroid and ranks outside top-K even though the
answer lives in one of its turns. This measures, with no embedding calls, whether
scoring at TURN granularity would rank those sessions materially higher.
"""
import json, re, math
from pathlib import Path

ROOT = Path("ab_deriv")
NAMES = [d.name for d in sorted((ROOT/"treatment").iterdir()) if d.is_dir()]
load = lambda d: json.loads((d/"benchmark-mr-diagnostics.json").read_text())
rows = load(ROOT/"treatment"/NAMES[0])

STOP = set("""a an the and or of to in for on with my me i you your it is are was were be been
this that these those as at from by have has had do does did can could would should will
any some more most other others than then there their they them he she his her about into
over under also very just not no what which who when where how many much i'm i've""".split())
TOKEN = re.compile(r"[a-z0-9']+")
def toks(s):
    return {t for t in TOKEN.findall(str(s).lower()) if t not in STOP and len(t) > 2}
def cos(a, b):
    A, B = toks(a), toks(b)
    return len(A & B)/math.sqrt(len(A)*len(B)) if A and B else 0.0
def fp(t, n=80):
    return re.sub(r"\W+", "", str(t).lower())[:n]
DATE = re.compile(r"^\[\d{4}/\d{2}/\d{2}")

def split_turns(session_text):
    out, cur = [], None
    for line in session_text.split("\n"):
        if DATE.match(line.strip()):
            if cur:
                out.append(cur)
            cur = line
        elif cur is not None:
            cur += "\n" + line
    if cur:
        out.append(cur)
    return out

sess_scores, turn_scores = [], []
detail = []
for x in rows:
    q = x["question"]
    dec = x["decision"] or {}
    ret = dec.get("retrieved","") or ""
    fpr = fp(ret, 10**7)
    eqs = dec.get("expansionQueries") or []
    queries = [q] + list(eqs)
    for c in (x.get("answer_sessions_content") or []):
        if not fp(c) or fp(c) in fpr:
            continue  # only the MISSED evidence sessions
        s_best = max(cos(qq, c) for qq in queries)
        turns = split_turns(c)
        t_best = max((max(cos(qq, t) for qq in queries) for t in turns), default=0.0)
        sess_scores.append(s_best)
        turn_scores.append(t_best)
        detail.append((t_best - s_best, s_best, t_best, len(turns), q))

def stat(name, xs):
    xs = sorted(xs)
    print(f"  {name:<34} n={len(xs):3d}  mean {sum(xs)/len(xs):.4f}  "
          f"median {xs[len(xs)//2]:.4f}  max {xs[-1]:.4f}")

print("== on the 18 MISSED evidence sessions: session-level vs turn-level best match ==")
stat("best score at SESSION granularity", sess_scores)
stat("best score at TURN granularity", turn_scores)
ms, mt = sum(sess_scores)/len(sess_scores), sum(turn_scores)/len(turn_scores)
print(f"\n  lift = {mt/ms:.2f}x")
print("  -> a large lift means turn-level scoring would rank these sessions much higher,")
print("     i.e. the miss is a GRANULARITY artefact, not a semantic-distance wall.")
print()
detail.sort(reverse=True)
print("  per-session lift (turn best - session best), strongest first:")
for lift, s, t, nturns, q in detail:
    print(f"    lift {lift:+.4f}  (session {s:.4f} -> turn {t:.4f}, {nturns} turns)  {q[:58]}")
