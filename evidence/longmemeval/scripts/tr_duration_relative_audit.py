"""
TR duration-error relative-time audit.

For every TR duration question scored wrong (correct=false, not abstained),
inspect the retrieved context for relative-time phrases INSIDE a turn's content
(e.g. "yesterday", "last week", "next month", "a month ago", "two weeks before")
that describe the EVENT but are not a [YYYY/MM/DD] turn prefix. The engine only
resolves "N days/weeks/months ago/before" (and only against the question date),
so a turn-relative phrase like "yesterday" is silently dropped and the turn date
is used instead — off by the offset.

This audit quantifies how much of the TR duration-error pool is that specific
root cause, to decide whether a turn-relative-time resolver is the right fix.
"""
import json
import glob
import os
import re

ROOT = "/workspace/analysis/ab_wronganswer"

# Relative-time phrases that can appear INSIDE a turn's body (not a date prefix).
REL_PHRASES = re.compile(
    r"(?i)\b(yesterday|the day before yesterday|last week|last month|last year|"
    r"next week|next month|next year|the week before|the month before|the day before|"
    r"a day before|a week before|a month before|two days ago|two weeks ago|"
    r"three days ago|three weeks ago)\b"
)
# Duration-question detector.
DURATION_Q = re.compile(r"(?i)how many (days|weeks|months)|how long|days? passed|days? ago|weeks? ago|months? ago")


def is_duration_wrong(r):
    return (
        r.get("capability") == "TR"
        and r.get("correct") is False
        and (r.get("decision") or {}).get("abstained") is not True
        and DURATION_Q.search(r["question"])
    )


def main():
    seen = {}
    for d in sorted(glob.glob(f"{ROOT}/run_*")):
        s = json.load(open(os.path.join(d, "benchmark-single-session-diagnostics.json")))
        for r in s:
            if not is_duration_wrong(r):
                continue
            q = r["question"]
            if q in seen:
                continue
            dec = r.get("decision") or {}
            ctx = str(dec.get("retrieved") or "")
            # Strip date prefixes so only IN-TURN relative phrases remain.
            body = re.sub(r"\[\d{4}/\d{2}/\d{2}[^\]]*\]", " ", ctx)
            rels = sorted(set(m.group(1).lower() for m in REL_PHRASES.finditer(body)))
            seen[q] = {
                "pred": dec.get("answer"),
                "gold": str(r.get("ground_truth")),
                "rels": rels,
                "ctx_len": len(ctx),
            }

    total = len(seen)
    with_rel = [q for q, v in seen.items() if v["rels"]]
    print(f"TR duration wrong questions (distinct): {total}")
    print(f"  with in-turn relative-time phrase: {len(with_rel)}")
    print(f"  without: {total - len(with_rel)}")
    print()
    print("=== with relative-time phrase ===")
    for q in sorted(with_rel, key=lambda x: -len(seen[x]["rels"])):
        v = seen[q]
        print(f"  pred={v['pred']!r} gold={v['gold'][:45]!r} rels={v['rels']}  Q={q[:65]}")
    print()
    print("=== without relative-time phrase (other root causes) ===")
    for q in sorted(seen, key=lambda x: seen[x]["ctx_len"]):
        if seen[q]["rels"]:
            continue
        v = seen[q]
        print(f"  pred={v['pred']!r} gold={v['gold'][:45]!r}  Q={q[:65]}")


if __name__ == "__main__":
    main()
