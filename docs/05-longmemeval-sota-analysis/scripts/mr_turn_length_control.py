"""Length-controlled re-test of the turn-granularity hypothesis.

The earlier 3.22x lift (mr_turn_granularity.py) was measured with a bag-of-words
cosine proxy. That proxy is length-biased: cosine divides by sqrt(|doc|), so a
SHORT document (a single turn) scores higher than a LONG one (a whole session)
even when both contain the same query terms. The 3.22x lift may therefore be an
artefact of turn brevity rather than evidence of semantic dilution.

This script isolates the two explanations with two controls per missed session:

  s_sess  = max_q cos(q, whole session)                  -- production today
  s_turn  = max_q max_i cos(q, turn_i)                   -- proposed change
  s_rand  = max_q cos(q, random window of length |best turn|, drawn from
                      OUTSIDE the best turn, averaged over K draws)
  s_head  = max_q cos(q, first |best turn| tokens of the session)

Interpretation:
  * If s_turn >> s_rand, the gain comes from LOCATING the relevant span, which is
    a real segmentation effect -> turn-level retrieval is justified.
  * If s_turn ~= s_rand, the gain is pure length bias -> the 3.22x was an artefact.
  * s_head low + s_turn high is the "off-topic head dilutes the centroid" story
    in its purest form.
"""
import json, re, math, random
from pathlib import Path

ROOT = Path("ab_deriv")
RUNS = sorted((ROOT / "treatment").iterdir())
load = lambda d: json.loads((d / "benchmark-mr-diagnostics.json").read_text())
rows = load(RUNS[0])

STOP = set("""a an the and or of to in for on with my me i you your it is are was were be been
this that these those as at from by have has had do does did can could would should will
any some more most other others than then there their they them he she his her about into
over under also very just not no what which who when where how many much""".split())
TOKEN = re.compile(r"[a-z0-9']+")
DATE = re.compile(r"^\[\d{4}/\d{2}/\d{2}")


def toks(s):
    return [t for t in TOKEN.findall(str(s).lower()) if t not in STOP and len(t) > 2]


def cos_set(a, b):
    """Cosine over token SETS (matches the original proxy)."""
    A, B = set(a), set(b)
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


random.seed(20260903)
K = 40

rec = []
for x in rows:
    q = x["question"]
    dec = x.get("decision") or {}
    retrieved_fp = fp(dec.get("retrieved", "") or "", 10 ** 7)
    queries = [q] + list(dec.get("expansionQueries") or [])

    for content in (x.get("answer_sessions_content") or []):
        if not fp(content) or fp(content) in retrieved_fp:
            continue  # only MISSED evidence sessions

        turns = split_turns(content)
        if len(turns) < 2:
            continue

        # best turn per query-set, and its token length
        best_i, s_turn = max(
            ((i, max(cos_set(toks(qq), toks(t)) for qq in queries))
             for i, t in enumerate(turns)),
            key=lambda p: p[1],
        )
        best_len = len(toks(turns[best_i]))

        all_toks = toks(content)
        s_sess = max(cos_set(toks(qq), all_toks) for qq in queries)

        # Control A: random windows of the SAME token length, excluding the best turn.
        # Rebuild the token stream with the best turn's span removed.
        best_tok_count = len(toks(turns[best_i]))
        other_toks = []
        for i, t in enumerate(turns):
            if i != best_i:
                other_toks.extend(toks(t))
        rands = []
        if len(other_toks) > best_tok_count:
            for _ in range(K):
                start = random.randrange(0, len(other_toks) - best_tok_count + 1)
                win = other_toks[start:start + best_tok_count]
                rands.append(max(cos_set(toks(qq), win) for qq in queries))
        s_rand = sum(rands) / len(rands) if rands else 0.0

        # Control B: head window of the same length
        s_head = max(cos_set(toks(qq), all_toks[:best_len]) for qq in queries)

        rec.append(dict(q=q, nturns=len(turns), best_len=best_len,
                        ntok=len(all_toks), s_sess=s_sess, s_turn=s_turn,
                        s_rand=s_rand, s_head=s_head))


def agg(key):
    v = sorted(r[key] for r in rec)
    n = len(v)
    mean = sum(v) / n
    med = v[n // 2]
    return mean, med, v[0], v[-1]


def fmt(label, key):
    mean, med, lo, hi = agg(key)
    print(f"  {label:<34} mean {mean:.4f}  median {med:.4f}  min {lo:.4f}  max {hi:.4f}")
    return mean


print(f"missed evidence sessions analysed: n={len(rec)}")
print(f"mean turns/session {sum(r['nturns'] for r in rec)/len(rec):.1f}  "
      f"mean tokens/session {sum(r['ntok'] for r in rec)/len(rec):.0f}  "
      f"mean best-turn tokens {sum(r['best_len'] for r in rec)/len(rec):.0f}")
print()
print("SCORES (token-set cosine, max over question + expansion queries)")
m_sess = fmt("s_sess  (whole session)", "s_sess")
m_turn = fmt("s_turn  (best single turn)", "s_turn")
m_rand = fmt("s_rand  (random window, len-matched)", "s_rand")
m_head = fmt("s_head  (first-turn-length window)", "s_head")
print()
print("LENGTH-BIAS DECOMPOSITION")
print(f"  raw lift vs session            {(m_turn/m_sess if m_sess else float('nan')):>6.2f}x")
print(f"  lift attributable to LENGTH    {(m_rand/m_sess if m_sess else float('nan')):>6.2f}x"
      f"   (random len-matched window)")
print(f"  lift attributable to SEGMENT   {(m_turn/m_rand if m_rand else float('nan')):>6.2f}x"
      f"   (best turn vs len-matched random)")
print()
print("PER-QUESTION DETAIL (top 10 by s_turn - s_sess)")
rec.sort(key=lambda r: r["s_turn"] - r["s_sess"], reverse=True)
print(f"  {'delta':>7} {'s_sess':>7} {'s_turn':>7} {'s_rand':>7} {'s_head':>7}  question")
for r in rec[:10]:
    print(f"  {r['s_turn']-r['s_sess']:+7.4f} {r['s_sess']:7.4f} {r['s_turn']:7.4f} "
          f"{r['s_rand']:7.4f} {r['s_head']:7.4f}  {r['q'][:52]}")

seg = [r for r in rec if r["s_turn"] > r["s_rand"]]
print()
print(f"sessions where best turn beats len-matched random window: "
      f"{len(seg)}/{len(rec)} ({len(seg)/len(rec)*100:.0f}%)")
worse = [r for r in rec if r["s_turn"] <= r["s_rand"]]
if worse:
    print(f"  counter-examples ({len(worse)}):")
    for r in worse[:6]:
        print(f"    s_turn {r['s_turn']:.4f} <= s_rand {r['s_rand']:.4f}  {r['q'][:50]}")
