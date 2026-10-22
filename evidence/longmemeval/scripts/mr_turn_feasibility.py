"""Feasibility check for the turn-level recall parameters.

I cannot compute true rank lift (no haystack, no embedding provider), but I CAN
ask a sharper question than "does turn granularity help?":

  Among the sessions a question already retrieves, where would the MISSED
  evidence session rank if every session were scored by its best turn?

If a missed session's best-turn score sits at or above the retrieved sessions'
best-turn scores, then it is competitive with sessions that DID make the cut, so
a turn-level search deep enough to see it (turnsPerQuery=30) would very likely
surface it -- and it would then be admitted because the channel only needs it to
be in the top `turnRecallSessions` (3) among NOT-yet-retrieved sessions.

If instead it sits far BELOW the retrieved sessions even at turn granularity, the
miss is a genuine semantic-distance wall and turn-level recall will not help.

Proxy is token-set cosine (the only scoring available offline). Caveat: a lexical
proxy understates dense semantic matching, so a competitive showing here is
strong evidence, while a poor showing is suggestive but not conclusive.
"""
import json, re, math
from pathlib import Path

ROOT = Path("ab_deriv")
RUNS = sorted((ROOT / "treatment").iterdir())
load = lambda d: json.loads((d / "benchmark-mr-diagnostics.json").read_text())

STOP = set("""a an the and or of to in for on with my me i you your it is are was were be been
this that these those as at from by have has had do does did can could would should will
any some more most other others than then there their they them he she his her about into
over under also very just not no what which who when where how many much""".split())
TOKEN = re.compile(r"[a-z0-9']+")
DATE = re.compile(r"^\[\d{4}/\d{2}/\d{2}")


def toks(s):
    return {t for t in TOKEN.findall(str(s).lower()) if t not in STOP and len(t) > 2}


def cos(a, b):
    A, B = toks(a), toks(b)
    return len(A & B) / math.sqrt(len(A) * len(B)) if A and B else 0.0


def fp(t, n=80):
    return re.sub(r"\W+", "", str(t).lower())[:n]


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


def split_sessions(ctx):
    return [s for s in ctx.split("\n\n") if s.strip()]


rows = load(RUNS[0])
better = 0
worse = 0
ranks = []
details = []

for x in rows:
    q = x["question"]
    dec = x.get("decision") or {}
    retrieved = split_sessions(dec.get("retrieved", "") or "")
    ret_fp = {fp(s) for s in retrieved}
    queries = [q] + list(dec.get("expansionQueries") or [])
    if not retrieved:
        continue

    # Best-turn score for each RETRIEVED session: the bar the missed session
    # must clear to look competitive under turn-granularity scoring.
    ret_scores = sorted(
        (max(max(cos(qq, t) for qq in queries) for t in split_turns(s))
         if split_turns(s) else 0.0)
        for s in retrieved
    )

    for content in (x.get("answer_sessions_content") or []):
        if not fp(content) or fp(content) in ret_fp:
            continue
        turns = split_turns(content)
        if not turns:
            continue
        miss = max(max(cos(qq, t) for qq in queries) for t in turns)
        # Rank the missed session against the retrieved ones (1 = best).
        rank = 1 + sum(1 for s in ret_scores if s > miss)
        ranks.append(rank)
        details.append((rank, miss, ret_scores[-1] if ret_scores else 0.0,
                        ret_scores[len(ret_scores) // 2] if ret_scores else 0.0,
                        len(retrieved), q))
        # Competitive = at or above the median retrieved session's best turn.
        med = ret_scores[len(ret_scores) // 2] if ret_scores else 0.0
        if miss >= med:
            better += 1
        else:
            worse += 1

n = len(ranks)
ranks_sorted = sorted(ranks)
print(f"missed evidence sessions compared: n={n}")
print(f"  competitive with retrieved (>= median best-turn): {better}/{n} "
      f"({better/n*100:.0f}%)")
print(f"  below median:                                     {worse}/{n} ({worse/n*100:.0f}%)")
print()
print(f"rank of missed session among retrieved by best-turn score "
      f"(1 = best of {details[0][4] if details else 0} retrieved):")
print(f"  median {ranks_sorted[n//2]:.1f}  mean {sum(ranks)/n:.2f}  "
      f"min {ranks_sorted[0]}  max {ranks_sorted[-1]}")
within3 = sum(1 for r in ranks if r <= 3)
within5 = sum(1 for r in ranks if r <= 5)
print(f"  within top-3 of retrieved: {within3}/{n} ({within3/n*100:.0f}%)")
print(f"  within top-5 of retrieved: {within5}/{n} ({within5/n*100:.0f}%)")
print()
print("WORST CASES (missed session ranks poorly even at turn granularity)")
details.sort(key=lambda d: (-d[0], d[1]))
print(f"  {'rank':>4} {'miss':>7} {'med':>7} {'best':>7}  question")
for rank, miss, best, med, nret, q in details[:8]:
    print(f"  {rank:>4} {miss:7.4f} {med:7.4f} {best:7.4f}  {q[:50]}")
