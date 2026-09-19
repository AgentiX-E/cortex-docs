"""
Age-operand ("32") retrieval fact table.

For each age-dependent MR question and each of the 4 treatment runs, record
whether the operand "32" is in (a) the full answer sessions and (b) the
retrieved window, what expansion queries were produced, and whether the run
answered or abstained. This isolates whether a miss is a retrieval failure
(full has it, retrieved does not), a truncation artifact, or an
operand-identification failure (retrieved has it, model still abstains).
"""
import json
import glob
import os
import re

ROOT = "/workspace/analysis/ab_mr_derivation/treatment"
AGE_QS = {
    "How old was I when Alex was born?",
    "How many years will I be when my friend Rachel gets married?",
    "How many years older is my grandma than me?",
    "What is the average age of me, my parents, and my grandparents?",
}

# "32" as the user's age, avoiding incidental matches like "32-year-old male".
P32 = re.compile(r"(?i)\b32\b|turned 32|32 is|32 on|age: 32|at 32")

print(f"{'question':<55} {'run':<12} {'full32':>7} {'retr32':>7} {'abst':>5} {'exp_queries'}")
for d in sorted(glob.glob(f"{ROOT}/run_*")):
    run = os.path.basename(d)
    mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
    for r in mr:
        if r["question"] not in AGE_QS:
            continue
        full = "\n".join(str(x) for x in (r.get("answer_sessions_content") or []))
        ctx = str(r.get("decision", {}).get("retrieved") or "")
        f32 = len(P32.findall(full))
        c32 = len(P32.findall(ctx))
        abst = r.get("decision", {}).get("abstained")
        exp = r.get("decision", {}).get("expansionQueries") or []
        q = r["question"]
        print(f"{q:<55} {run:<12} {f32:>7} {c32:>7} {str(abst):>5} {exp}")
    print()
