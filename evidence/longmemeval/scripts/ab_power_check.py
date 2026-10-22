"""Power check for turn_recall_ab.py: does the primary endpoint actually detect
a real effect?

A smoke test on null-effect data only proves the script reports zero when nothing
happened. It says nothing about sensitivity — a script whose primary endpoint
always reads zero would pass it too. So this builds a synthetic treatment arm
from a real control run by injecting the *known* missing evidence sessions, then
checks that the script recovers exactly the number injected.

Two variants, because they answer different questions:

  no_budget  -- append the missing session without applying the 20k aggregation
                cap. Isolates the endpoint's sensitivity: every injection that is
                not clipped must be detected.
  with_budget-- append, then apply `truncateText(.., 20_000)` exactly as
                `answerSessions` does. Measures how much of the achievable gain
                the aggregation budget actually costs, which is the real number
                the A/B will see.

Injection uses the SAME fingerprint test the analysis script uses. Exact string
matching is wrong here: the retrieved context is already truncated per session,
so an evidence session almost never appears verbatim even when the fingerprint
says it was found.

Usage: python3 ab_power_check.py [variant]   (default: no_budget)
"""
import json, re, shutil, sys
from pathlib import Path

SRC = Path("ab_deriv/control/run_33840216156")
DST = Path("ab_turn_power")
FILES = [
    "benchmark-mr-diagnostics.json",
    "benchmark-single-session-diagnostics.json",
    "benchmark-report.json",
    "benchmark-report.md",
]
FP_LEN = 80
AGG_BUDGET = 20_000


def fp(t, n=FP_LEN):
    return re.sub(r"\W+", "", str(t).lower())[:n]


def truncate_text(text, max_chars=AGG_BUDGET):
    """Mirror `truncateText` from natural-language-memory.ts."""
    return text[:max_chars] + "\n[truncated]" if len(text) > max_chars else text


def build(variant):
    if DST.exists():
        shutil.rmtree(DST)
    (DST / "control/run_c1").mkdir(parents=True)
    (DST / "treatment/run_t1").mkdir(parents=True)
    for f in FILES:
        shutil.copy(SRC / f, DST / "control/run_c1" / f)
        if f != "benchmark-mr-diagnostics.json":
            shutil.copy(SRC / f, DST / "treatment/run_t1" / f)

    mrd = json.loads((SRC / "benchmark-mr-diagnostics.json").read_text())
    injected = headroom = 0
    for rec in mrd:
        ev = rec.get("answer_sessions_content") or []
        dec = rec["decision"] or {}
        retrieved = dec.get("retrieved", "") or ""
        if not ev or not retrieved:
            continue
        hay = fp(retrieved, 10 ** 7)
        missing = [e for e in ev if e and fp(e) and fp(e) not in hay]
        if not missing:
            continue
        # Simulate the channel recovering ONE missing evidence session, appended
        # at the end exactly as `retrieveSessionsByTurns` output is appended.
        merged = retrieved + "\n\n" + missing[0]
        if variant == "with_budget":
            merged = truncate_text(merged)
        injected += 1
        if fp(missing[0]) in fp(merged, 10 ** 7):
            headroom += 1
        dec["retrieved"] = merged

    (DST / "treatment/run_t1/benchmark-mr-diagnostics.json").write_text(json.dumps(mrd))
    return injected, headroom


if __name__ == "__main__":
    variant = sys.argv[1] if len(sys.argv) > 1 else "no_budget"
    if variant not in ("no_budget", "with_budget"):
        raise SystemExit("variant must be no_budget or with_budget")
    n, h = build(variant)
    print(f"[{variant}] injected 1 missing evidence session into {n} MR questions; "
          f"{h} survive into the context")
    print(f"[{variant}] expected: recall improves on {h}, regresses on 0\n")
