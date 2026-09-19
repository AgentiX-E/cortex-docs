"""
Wrong-answer root-cause characterization.

The diagnostics now carry a per-question `correct` flag, so a wrong answer can
be distinguished from a correct one WITHOUT re-running the judge. For every
WRONG (non-abstaining, correct=false) answer, classify it by comparing the
predicted answer to the gold:

  - SEMANTIC-MATCH (eval gap): the predicted answer is semantically the same
    value as the gold but differs in surface form — a spelled number ("two" vs
    "2"), an article/quotes ("Episcopal Church" vs "the Episcopal Church"),
    or a paraphrase. These are candidates for an evaluation-robustness fix, NOT
    a model fix.
  - NUMERIC-UNIT: the gold is a duration/quantity ("Two weeks", "38 days") and
    the predicted answer is a number that may be an alternative encoding
    ("14", "9") — needs the judge, but the leading-number test can often
    resolve equivalence.
  - GENUINE: the predicted value genuinely differs from the gold (wrong count,
    wrong entity, wrong arithmetic).

The output splits the wrong-answer pool so the NEXT fix targets the right layer
(evaluation vs model vs retrieval).
"""
import json
import glob
import os
import re

ROOT = "/workspace/analysis/ab_wronganswer"

SPELLED = re.compile(
    r"(?i)\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|hundred|thousand|million)\b"
)
NUM = re.compile(r"\d[\d,]*\.?\d*")


def norm(s):
    return re.sub(r"\s+", " ", str(s).lower().strip().rstrip("."))


def first_num(s):
    m = NUM.search(s)
    return m.group(0).replace(",", "") if m else None


def strip_decorations(s):
    """Lowercase, drop quotes/leading articles, collapse whitespace."""
    s = norm(s)
    s = s.replace("'", "").replace('"', "").replace("`", "")
    s = re.sub(r"^(the|a|an)\s+", "", s)
    return s


def classify(predicted, gold):
    p, g = norm(predicted), norm(gold)
    if p == g:
        return "exact"  # shouldn't happen: exact would already be correct
    # 1. strip decorations and compare — catches article/quote/case differences
    if strip_decorations(p) == strip_decorations(g):
        return "semantic-match"
    # 2. numeric equivalence: extract first number from both
    fp, fg = first_num(p), first_num(g)
    if fp is not None and fg is not None and float(fp) == float(fg):
        return "numeric-match"
    # 3. one side spelled number, other numeric
    if fp is not None and SPELLED.search(g):
        return "numeric-vs-spelled"
    if SPELLED.search(p) and fg is not None:
        return "spelled-vs-numeric"
    # 4. gold is a duration/quantity, predicted is a bare number (near-miss)
    return "genuine"


def load(run_dir):
    single = json.load(open(os.path.join(run_dir, "benchmark-single-session-diagnostics.json")))
    mr = json.load(open(os.path.join(run_dir, "benchmark-mr-diagnostics.json")))
    for r in mr:
        r["capability"] = "MR"
    return single + mr


def main():
    runs = sorted(glob.glob(f"{ROOT}/run_*"))
    print(f"runs: {len(runs)}")
    tally = {}
    samples = []
    for run in runs:
        for r in load(run):
            if r.get("correct") is not False:
                continue  # only wrong answers (correct=false)
            dec = r.get("decision") or {}
            if dec.get("abstained"):
                continue  # abstentions handled separately
            cap = r.get("capability") or "?"
            predicted = dec.get("answer")
            gold = r.get("ground_truth")
            if predicted is None:
                continue
            kind = classify(predicted, gold)
            t = tally.setdefault(cap, {})
            t[kind] = t.get(kind, 0) + 1
            samples.append((cap, kind, r["question"], predicted, gold))

    print("\n=== wrong-answer classification (per capability) ===")
    kinds = ["semantic-match", "numeric-match", "numeric-vs-spelled", "spelled-vs-numeric", "genuine"]
    print(f"{'cap':<4} " + " ".join(f"{k:>20}" for k in kinds))
    for cap in sorted(tally):
        t = tally[cap]
        row = " ".join(f"{t.get(k, 0):>20}" for k in kinds)
        print(f"{cap:<4} {row}")

    print("\n=== SEMANTIC-MATCH / NUMERIC samples (eval-gap candidates) ===")
    n = 0
    for cap, kind, q, pred, gold in sorted(samples, key=lambda s: (s[1], s[0], s[2])):
        if kind == "genuine":
            continue
        n += 1
        print(f"[{cap}/{kind}] pred={pred!r}  gold={str(gold)[:60]!r}  Q={q[:60]}")
        if n >= 40:
            break
    print(f"\n(eval-gap candidates shown: {n})")


if __name__ == "__main__":
    main()
