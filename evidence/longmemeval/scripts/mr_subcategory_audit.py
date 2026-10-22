"""
MR sub-category error audit.

Split MR wrong answers (correct=false, not abstained) by classifyAggregationKind
(derivation vs enumeration) and by error shape (off-by-one count, sum error,
entity error, other), to decide whether a sub-category-specific fix (context
budget, prompt, or retrieval) is warranted, or whether the remaining errors are
too heterogeneous to route around.
"""
import json
import glob
import os
import re
import subprocess
from collections import Counter

ROOT = "/workspace/analysis/ab_wronganswer"

KIND_JS = """
import { classifyAggregationKind } from '/workspace/cortex/packages/cortex-eval/dist/natural-language-memory.js';
const qs = JSON.parse(process.argv[1]);
console.log(JSON.stringify(qs.map(q => classifyAggregationKind(q))));
"""


def classify_kind(questions):
    out = subprocess.run(
        ["node", "--input-type=module", "-e", KIND_JS, json.dumps(questions)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def norm(s):
    return re.sub(r"\s+", " ", str(s).lower().strip().rstrip("."))


def first_num(s):
    m = re.search(r"\d[\d,]*\.?\d*", s)
    return m.group(0).replace(",", "") if m else None


def err_shape(pred, gold):
    p, g = norm(pred), norm(gold)
    fp, fg = first_num(p), first_num(g)
    # Both numeric, different values -> counting/arithmetic error.
    if fp is not None and fg is not None:
        if float(fp) == float(fg):
            return "format-only"
        return "numeric-diff"
    # One side numeric, other not -> entity/verb mismatch.
    if fp is not None or fg is not None:
        return "numeric-vs-text"
    return "text-diff"


def main():
    # Collect distinct MR wrong questions (correct=false, not abstained).
    qs = {}
    for d in sorted(glob.glob(f"{ROOT}/run_*")):
        mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
        for r in mr:
            if r.get("correct") is not False:
                continue
            dec = r.get("decision") or {}
            if dec.get("abstained"):
                continue
            if r["question"] not in qs:
                qs[r["question"]] = (dec.get("answer"), r["ground_truth"])

    qlist = list(qs.keys())
    kinds = dict(zip(qlist, classify_kind(qlist)))

    by_kind = {"derivation": Counter(), "enumeration": Counter()}
    samples = {"derivation": [], "enumeration": []}
    for q, (pred, gold) in qs.items():
        kind = kinds[q]
        shape = err_shape(pred, gold)
        by_kind[kind][shape] += 1
        samples[kind].append((shape, pred, gold, q))

    print(f"distinct MR wrong questions: {len(qs)}")
    for kind in ["derivation", "enumeration"]:
        c = by_kind[kind]
        total = sum(c.values())
        print(f"\n=== {kind} ({total} wrong) ===")
        for shape, n in c.most_common():
            print(f"  {shape:16} {n}")

    print("\n=== numeric-diff samples (counting/arithmetic errors) ===")
    n = 0
    for kind in ["derivation", "enumeration"]:
        for shape, pred, gold, q in samples[kind]:
            if shape == "numeric-diff":
                n += 1
                print(f"[{kind}] pred={str(pred)!r} gold={str(gold)[:35]!r}  Q={q[:58]}")
                if n >= 30:
                    break
        if n >= 30:
            break
    print(f"(shown {n})")


if __name__ == "__main__":
    main()
