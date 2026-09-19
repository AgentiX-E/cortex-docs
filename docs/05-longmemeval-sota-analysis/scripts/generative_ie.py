"""BUG hunt: the tightened CoN contract abstains on GENERATIVE questions.

LongMemEval's IE gold answers come in two shapes:
  - EXTRACTIVE  "Business Administration"  -> the answer is a fact in the history
  - GENERATIVE  "The user would prefer responses that build upon ..." -> the
                answer must be COMPOSED from the history, not copied from it

conInstruction() now pins the reply to "Answer: <a word, name, number, or short
phrase>" and Step 2 to "using ONLY those identified facts". For a generative
question that reads as "add nothing", so the model abstains. This script sizes
the damage.
"""

import re
from pathlib import Path

exec(open("question_level_ab2.py").read().split('print("== A.')[0])

GENERATIVE = re.compile(r"^\s*the user would prefer", re.I)


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


print("== how many IE gold answers are generative? ==")
IE = [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == "IE"]
gen = [q for q in IE if GENERATIVE.match(str(DATA[CTRL[0]][q]["expected"]))]
ext = [q for q in IE if q not in set(gen)]
print(f"  IE total {len(IE)}   generative {len(gen)}   extractive {len(ext)}")

for cap in ("TR", "MR", "KU"):
    cs = [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == cap]
    g = [q for q in cs if GENERATIVE.match(str(DATA[CTRL[0]][q]["expected"]))]
    print(f"  {cap}: {len(g)}/{len(cs)} generative")
print()

print("== abstention rate by gold shape and arm ==")
print(f"  {'group':<22} {'n':>4}  {'control':>8}  {'treatment':>9}  {'delta':>8}")
for label, qs in (("IE generative", gen), ("IE extractive", ext),
                  ("IE all", IE),
                  ("TR", [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == "TR"]),
                  ("MR", [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == "MR"]),
                  ("KU", [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == "KU"])):
    if not qs:
        continue
    c = sum(DATA[r][q]["abstained"] for r in CTRL for q in qs) / (3 * len(qs))
    t = sum(DATA[r][q]["abstained"] for r in TREAT for q in qs) / (3 * len(qs))
    print(f"  {label:<22} {len(qs):>4}  {c*100:7.2f}%  {t*100:8.2f}%  {(t-c)*100:+7.2f}pp")
print()

print("== how many questions does that cost per run? ==")
for label, qs in (("IE generative", gen), ("IE extractive", ext)):
    c = sum(DATA[r][q]["abstained"] for r in CTRL for q in qs) / 3
    t = sum(DATA[r][q]["abstained"] for r in TREAT for q in qs) / 3
    print(f"  {label:<16} control {c:5.2f} abstentions/run   treatment {t:5.2f}   "
          f"delta {t-c:+5.2f} questions/run")

print()
print("== is the generative abstention stable across runs? ==")
det = sum(1 for q in gen if sum(DATA[r][q]["abstained"] for r in TREAT) in (0, 3))
print(f"  IE generative questions with the SAME verdict in all 3 treatment runs: "
      f"{det}/{len(gen)}  ({det/len(gen)*100:.1f}%)")
print(f"  of those, abstaining in all 3: "
      f"{sum(1 for q in gen if sum(DATA[r][q]['abstained'] for r in TREAT) == 3)}")
print(f"  abstaining in all 3 under CONTROL: "
      f"{sum(1 for q in gen if sum(DATA[r][q]['abstained'] for r in CTRL) == 3)}")
print()

print("== the abstain-token instruction the model is following ==")
print("  preference prompt: \"Respond with exactly <token> ONLY if the context")
print("  contains no information about the user's preferences at all.\"")
print("  -> these questions DO contain preferences, so the abstention is the model")
print("     reading Step 2's 'using ONLY those identified facts' + the 'short")
print("     phrase' reply contract as a prohibition on composing an answer.")
