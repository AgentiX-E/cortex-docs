"""
MR counting-error feasibility audit.

For each MR enumeration counting error (correct=false, numeric-diff), dump the
question/gold/predicted and the retrieved context turns that carry digits or
relevant evidence, to decide — per question — whether the evidence for the gold
answer WAS in the retrieved window (a semantic-judgment failure, potentially
fixable by clearer context presentation) or was MISSING (a retrieval failure,
not fixable by prompt).
"""
import json
import glob
import os
import re
import subprocess

ROOT = "/workspace/analysis/ab_wronganswer"

KIND_JS = """
import { classifyAggregationKind } from '/workspace/cortex/packages/cortex-eval/dist/natural-language-memory.js';
const qs = JSON.parse(process.argv[1]);
console.log(JSON.stringify(qs.map(q => classifyAggregationKind(q))));
"""


def classify_kind(qs):
    out = subprocess.run(
        ["node", "--input-type=module", "-e", KIND_JS, json.dumps(qs)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def first_num(s):
    if s is None:
        return None
    m = re.search(r"\d[\d,]*\.?\d*", str(s))
    return m.group(0).replace(",", "") if m else None


def norm(s):
    return re.sub(r"\s+", " ", str(s).lower().strip().rstrip("."))


def main():
    qs = {}
    for d in sorted(glob.glob(f"{ROOT}/run_*")):
        mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
        for r in mr:
            if r.get("correct") is not False:
                continue
            dec = r.get("decision") or {}
            if dec.get("abstained"):
                continue
            pred, gold = dec.get("answer"), r["ground_truth"]
            fp, fg = first_num(pred), first_num(gold)
            if fp is None or fg is None or float(fp) == float(fg):
                continue  # not a numeric-diff error
            if r["question"] not in qs:
                qs[r["question"]] = {
                    "pred": pred,
                    "gold": gold,
                    "ctx": dec.get("retrieved") or "",
                    "full": "\n".join(str(x) for x in (r.get("answer_sessions_content") or [])),
                }

    qlist = list(qs.keys())
    kinds = dict(zip(qlist, classify_kind(qlist)))
    enum = [q for q in qlist if kinds[q] == "enumeration"]

    print(f"enumeration numeric-diff wrong: {len(enum)}\n")
    for q in enum:
        v = qs[q]
        # Turns in retrieved context that carry a digit (candidate evidence).
        ctx = v["ctx"]
        digit_turns = [
            t for t in re.split(r"\n(?=\[)", ctx)
            if re.search(r"\d", t)
        ]
        print("=" * 100)
        print(f"Q: {q}")
        print(f"  GOLD={v['gold']!r}  PRED={v['pred']!r}")
        print(f"  retrieved len={len(ctx)}  digit-turns={len(digit_turns)}")
        for t in digit_turns[:8]:
            print(f"    {t[:170]}")
        print()


if __name__ == "__main__":
    main()
