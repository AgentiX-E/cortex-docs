"""Refine the proxy: the 36 touched questions are long-gold IE items, so the
token-F1 proxy must be calibrated inside IE, not across the whole benchmark."""

import re
from pathlib import Path

exec(open("question_level_ab2.py").read().split('print("== A.')[0])

STOP = set("""a an the and or of to in for on with my me i you your it is are was were be been
this that these those as at from by have has had do does did can could would should
any some more most other others than then there their they them he she his her
about into over under also very just not no yes""".split())
TOKEN = re.compile(r"[a-z0-9']+")


def toks(s):
    return {t for t in TOKEN.findall(str(s).lower()) if t not in STOP and len(t) > 2}


def f1(a, b):
    A, B = toks(a), toks(b)
    if not A or not B:
        return 0.0
    return 2 * len(A & B) / (len(A) + len(B))


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


IE = [q for q in QIDS if DATA[CTRL[0]][q]["capability"] == "IE"]
touched = {q for q in QIDS if any(DATA[r][q]["collapsed"] for r in CTRL)}
ie_touched = [q for q in IE if q in touched]
ie_untouched = [q for q in IE if q not in touched]

print(f"IE questions: {len(IE)}   touched by the patch: {len(ie_touched)}")

# length of the gold answer, to show the two groups are comparable
gl_t = mean([len(str(DATA[CTRL[0]][q]["expected"]).split()) for q in ie_touched])
gl_u = mean([len(str(DATA[CTRL[0]][q]["expected"]).split()) for q in ie_untouched])
print(f"  mean gold length (words): touched {gl_t:.1f}   untouched {gl_u:.1f}")
print()

for label, qs in (("touched", ie_touched), ("untouched", ie_untouched)):
    fc = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"]) for q in qs for r in CTRL])
    ft = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"]) for q in qs for r in TREAT])
    print(f"  IE {label:<10} control F1 {fc:.4f}   treatment F1 {ft:.4f}   delta {ft-fc:+.4f}")

print()
print("== are the touched questions simply harder? ==")
allc = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"]) for q in IE for r in CTRL])
print(f"  IE overall control F1 {allc:.4f};  touched subset "
      f"{mean([f1(DATA[r][q]['answer'], DATA[CTRL[0]][q]['expected']) for q in ie_touched for r in CTRL]):.4f}")

print()
print("== abstention on the touched questions (a hard, non-proxy signal) ==")
for arm, rs in (("control", CTRL), ("treatment", TREAT)):
    ab = sum(DATA[r][q]["abstained"] for r in rs for q in ie_touched) / (3 * len(ie_touched))
    print(f"  {arm:<10} abstention {ab*100:5.2f}%")

print()
print("== the decisive non-proxy comparison: within the 36, who abstains? ==")
b = c = 0
for q in ie_touched:
    ca = sum(DATA[r][q]["abstained"] for r in CTRL)
    ta = sum(DATA[r][q]["abstained"] for r in TREAT)
    if ca > ta:
        b += 1
    elif ta > ca:
        c += 1
print(f"  questions abstained more under control: {b}   more under treatment: {c}")
print("  (an abstention is always wrong on IE, so 'more under control' favours the fix)")
