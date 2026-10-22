"""
Where is the next defective-abstention prize?

After the KU no-qualifier fix, measure how many abstentions are DEFECTIVE, i.e.
the gold answer was sitting verbatim in the retrieved context and the system
still refused to answer. Those are the only abstentions that are unambiguously
the system's fault.

The measurement has a false-positive mode that has to be controlled for: a
BARE-NUMBER gold like "4" matches any occurrence of that digit anywhere in the
context ("...for 4 years", "session 4"), so a naive substring test reports a hit
for almost every numeric gold. Splitting numeric from textual golds separates
the trusted evidence from the suspect evidence. Only the TEXTUAL hits are
actionable without a stricter matching test.
"""
import json
import glob
import os
import re
import sys

ROOT = "/workspace/analysis/ab_ku_noqual"
ARMS = ["control", "treatment"]
# Use the treatment arm: it is the current master, so the numbers describe the
# state we would actually be improving.
ARM = sys.argv[1] if len(sys.argv) > 1 else "treatment"


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()


def load(arm):
    runs = []
    for d in sorted(glob.glob(f"{ROOT}/{arm}/run_*")):
        if not os.path.isdir(d):
            continue
        report = json.load(open(os.path.join(d, "benchmark-report.json")))
        if report.get("questionCount") != 500:
            continue
        single = json.load(open(os.path.join(d, "benchmark-single-session-diagnostics.json")))
        mr = json.load(open(os.path.join(d, "benchmark-mr-diagnostics.json")))
        for r in mr:
            r["capability"] = "MR"
        runs.append({"run": os.path.basename(d), "records": single + mr})
    return runs


runs = load(ARM)
print(f"arm = {ARM}   runs = {len(runs)}")

# Two false-positive modes, both from matching a short gold against a long context:
#   (a) bare numerals  - "4" matches "...for 4 years", "session 4"
#   (b) spelled numbers - "Two" is an ordinary English word and matches anywhere
# Neither is evidence that the system could have produced the answer, so both
# are reported as SUSPECT. Only a non-numeric gold is treated as trusted.
NUMERIC = re.compile(r"^[\d\s.,:/%$-]+$")
SPELLED_NUMBER = re.compile(
    r"^\W*(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|hundred|thousand|million|a\s+couple|a\s+few|several)"
    r"(\s+(weeks?|days?|months?|years?|times?|hours?|nights?|cats?|dogs?|people))?"
    r"\W*$",
    re.I,
)


def gold_class(gold):
    if NUMERIC.match(gold):
        return "num"
    if SPELLED_NUMBER.match(gold):
        return "num"
    return "txt"

tally = {}
samples = []
for run in runs:
    for r in run["records"]:
        if r.get("decision", {}).get("abstained") is not True:
            continue
        cap = r.get("capability") or "?"
        gold = str(r.get("ground_truth") or "").strip()
        ctx = str(r.get("decision", {}).get("retrieved") or "")
        t = tally.setdefault(cap, {"abst": 0, "num": 0, "txt": 0, "none": 0})
        t["abst"] += 1
        if not gold:
            t["none"] += 1
            continue
        needle = " ".join(norm(gold))
        hit = bool(needle) and needle in " ".join(norm(ctx))
        if not hit:
            t["none"] += 1
            continue
        if gold_class(gold) == "num":
            t["num"] += 1
        else:
            t["txt"] += 1
            samples.append((cap, r["question"], gold, ctx))

print()
print(f"{'cap':<5} {'abst':>5} {'NUMERIC(suspect)':>18} {'TEXTUAL(trusted)':>18} {'no hit':>16}")
for cap in sorted(tally):
    t = tally[cap]
    print(f"{cap:<5} {t['abst']:>5} {t['num']:>9} ({100*t['num']/t['abst']:5.1f}%) "
          f"{t['txt']:>9} ({100*t['txt']/t['abst']:5.1f}%) {t['none']:>7} ({100*t['none']/t['abst']:5.1f}%)")

print()
print("=== TRUSTED (non-numeric gold, verbatim in context, still abstained) ===")
seen = set()
shown = 0
for cap, q, gold, ctx in samples:
    key = (cap, q)
    if key in seen:
        continue
    seen.add(key)
    shown += 1
    # Show the actual occurrence window so each hit can be audited rather than
    # taken on trust.
    toks = norm(ctx)
    ng = norm(gold)
    pos = None
    for i in range(len(toks) - len(ng) + 1):
        if toks[i:i + len(ng)] == ng:
            pos = i
            break
    window = " ".join(toks[max(0, pos - 25):pos + len(ng) + 25]) if pos is not None else "(not found)"
    print(f"[{cap}] Q: {q}")
    print(f"       GOLD : {gold!r}")
    print(f"       HIT  : ...{window}...")
    print()

print(f"distinct trusted defective abstentions: {shown} over {len(runs)} runs "
      f"= {shown/len(runs):.2f}/run = {100*shown/len(runs)/500:.2f}% of the benchmark")
