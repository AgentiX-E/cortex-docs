"""Is a lexical-overlap proxy good enough to stand in for the LLM judge?

The 36 questions the patch actually touches are all judge-graded, so the A/B
cannot be settled analytically there. This script calibrates a token-F1 proxy
against the questions whose verdict IS deterministic, then applies it only if it
separates correct from incorrect answers.
"""

import json
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
    inter = len(A & B)
    return 2 * inter / (len(A) + len(B))


# ---- calibration: does token-F1 separate correct from incorrect? -------------
gold_f1 = {"correct": [], "incorrect": []}
for q in QIDS:
    s = DATA[CTRL[0]][q]
    if s["expected"] is None:
        continue
    for r in CTRL + TREAT:
        v = verdict(s["question"], DATA[r][q]["answer"], DATA[r][q]["expected"])
        if v is None:
            continue
        gold_f1["correct" if v else "incorrect"].append(
            f1(DATA[r][q]["answer"], s["expected"])
        )


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


c, w = gold_f1["correct"], gold_f1["incorrect"]
print("== calibration of the token-F1 proxy ==")
print(f"  deterministically correct   n={len(c):4d}  mean F1 = {mean(c):.4f}")
print(f"  deterministically incorrect n={len(w):4d}  mean F1 = {mean(w):.4f}")
pooled = ((len(c) - 1) * (sum((x - mean(c)) ** 2 for x in c) / (len(c) - 1)) +
          (len(w) - 1) * (sum((x - mean(w)) ** 2 for x in w) / (len(w) - 1))) / \
         (len(c) + len(w) - 2)
d = (mean(c) - mean(w)) / pooled ** 0.5
print(f"  Cohen's d = {d:.3f}   (a usable proxy needs d well above ~0.5)")

# is the split at some threshold predictive?
thr = (mean(c) + mean(w)) / 2
tp = sum(1 for x in c if x >= thr)
tn = sum(1 for x in w if x < thr)
print(f"  at F1 >= {thr:.3f}: sensitivity {tp/len(c):.3f}  specificity {tn/len(w):.3f}  "
      f"balanced acc {(tp/len(c) + tn/len(w))/2:.3f}")
print()

# ---- apply the proxy ONLY to the touched questions ---------------------------
touched = [q for q in QIDS if any(DATA[r][q]["collapsed"] for r in CTRL)]
print(f"== token-F1 on the {len(touched)} questions the patch touches ==")
print("   (all are judge-graded, so this is a proxy, not a verdict)")
fc = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"])
           for q in touched for r in CTRL])
ft = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"])
           for q in touched for r in TREAT])
print(f"  control   mean F1 = {fc:.4f}")
print(f"  treatment mean F1 = {ft:.4f}")
print(f"  delta = {ft - fc:+.4f}")

# per-question paired sign test
b = c2 = 0
for q in touched:
    a = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"]) for r in CTRL])
    e = mean([f1(DATA[r][q]["answer"], DATA[CTRL[0]][q]["expected"]) for r in TREAT])
    if a > e + 1e-9:
        b += 1
    elif e > a + 1e-9:
        c2 += 1
print(f"  questions favouring control: {b}   favouring treatment: {c2}   tied: "
      f"{len(touched) - b - c2}")
