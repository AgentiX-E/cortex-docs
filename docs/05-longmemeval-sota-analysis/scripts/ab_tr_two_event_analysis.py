"""TR two-event temporal A/B: control db92e62 vs treatment d793db4.

Pre-registered design (see /workspace/analysis/tr-two-event-plan.md §6).

  PRIMARY (mechanism endpoint)
      The N `relative` questions that name a second event, scored on the
      majority-vote bucket of 4 runs. Control is 0/N; treatment must reach
      >= (N-1)/N.

  SECONDARY (noise-floored, descriptive only)
      TR accuracy and overall accuracy. These are sampled endpoints; the
      permutation test below is reported for completeness but the study is not
      powered to detect the ~1pp effect this fix can produce on 500 questions,
      so it is NOT an acceptance criterion.

  GUARDS (all four must pass)
      G1  0 bucket-level regressions among the single-event `relative` questions
      G2  0 bucket-level regressions among `interval` + `ordering`
      G3  no capability outside TR moves beyond its own run-to-run spread
      G4  TR abstention does not rise

Usage: python3 ab_tr_two_event_analysis.py
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/analysis/ab_tr_two_event")
CENSUS = ROOT / "census.json"

LEADING_NUM = re.compile(r"^\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def norm(v) -> str:
    return re.sub(r"\s+", " ", str(v).strip().lower())


def lead(v):
    """First number in an answer, or None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = LEADING_NUM.match(str(v).strip())
    return float(m.group(1).replace(",", "")) if m else None


def gold_nums(text) -> list[float]:
    out = []
    for m in NUM.finditer(str(text)):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def correct(answer, gold):
    """True / False / None(=needs a judge). None is treated as not-wrong.

    TR answers are numeric spans, so a leading-number match against any number
    in the gold string is a genuine hit rather than a lenient one: the gold of a
    temporal question carries exactly one intended quantity.
    """
    if answer is None:
        return False
    if norm(answer) == norm(gold):
        return True
    p, gs = lead(answer), gold_nums(gold)
    if p is not None and gs:
        return any(abs(p - g) < 1e-9 for g in gs)
    return None


def bucket(answers) -> str | None:
    """Majority-vote answer over the runs of one arm.

    A 2/2 tie has no mode, and the benchmark scores an unresolved question as
    wrong, so a tie is scored wrong rather than being resolved by run order.
    """
    present = [a for a in answers if a is not None]
    if not present:
        return None
    counts = Counter(present)
    top = max(counts.values())
    if sum(1 for v in counts.values() if v == top) > 1:
        return None  # tie -> no mode -> wrong
    return counts.most_common(1)[0][0]


def score(answers, gold) -> bool:
    """Bucket-level correctness: the modal answer, ties counted as wrong."""
    return correct(bucket(answers), gold) is True


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def perm_test_p(a: list[float], b: list[float]) -> float:
    """Exact two-sided permutation test on the difference of means.

    With 4 + 4 runs there are C(8,4) = 70 splits, so the smallest attainable
    p is 1/70 = 0.0143. That floor is reported alongside the value because it
    bounds what this design can ever claim.
    """
    pool = a + b
    n = len(a)
    obs = abs(mean(a) - mean(b))
    total = hits = 0
    for idx in combinations(range(len(pool)), n):
        g1 = [pool[i] for i in idx]
        g2 = [pool[i] for i in range(len(pool)) if i not in idx]
        total += 1
        if abs(mean(g1) - mean(g2)) >= obs - 1e-12:
            hits += 1
    return hits / total


def main() -> None:
    data = json.loads(CENSUS.read_text())
    qs = data["questions"]
    arms = data["runs"]
    C, T = "control", "treatment"
    nC, nT = len(arms[C]), len(arms[T])
    print(f"control   {nC} runs: {', '.join(arms[C])}")
    print(f"treatment {nT} runs: {', '.join(arms[T])}")
    print(f"{len(qs)} questions in every run\n")

    # ---------------------------------------------------------------- PRIMARY
    two = [q for q in qs if q["twoEvent"]]
    print("=" * 78)
    print(f"PRIMARY  two-event `relative` questions  (n={len(two)})")
    print("=" * 78)
    print(f"{'':<3}{'gold':<12}{'control':<26}{'treatment':<26}")
    c_hits = t_hits = 0
    for q in two:
        ca, ta = q["answers"][C], q["answers"][T]
        c_ok, t_ok = score(ca, q["gold"]), score(ta, q["gold"])
        c_hits += c_ok
        t_hits += t_ok
        print(
            f"{'OK ' if t_ok else 'BAD'} {str(q['gold'])[:10]:<12}"
            f"{str(sorted(set(ca)))[:24]:<26}{str(sorted(set(ta)))[:24]:<26}"
        )
        print(f"      {q['question'][:92]}")
    print(f"\n  control   {c_hits}/{len(two)}")
    print(f"  treatment {t_hits}/{len(two)}")
    need = len(two) - 1
    print(f"  acceptance: treatment >= {need}/{len(two)}  ->  "
          f"{'PASS' if t_hits >= need else 'FAIL'}")

    # Within-arm agreement: if all four runs of an arm return the same string,
    # the bucket is decided by the arithmetic rather than by the vote. Under the
    # temporal-null A/B (see tr_guard_noise_floor.py) this bucket never moved
    # across any of the 35 possible 4v4 splits, so any movement here is not
    # sampling noise.
    print("\n  within-arm agreement (all 4 runs identical?)")
    for q in two:
        cu, tu = set(q["answers"][C]), set(q["answers"][T])
        print(f"    control {len(cu)}={'y' if len(cu) == 1 else 'n'}  "
              f"treatment {len(tu)}={'y' if len(tu) == 1 else 'n'}   "
              f"{q['question'][:64]}")

    # ------------------------------------------------------------- SECONDARY
    print("\n" + "=" * 78)
    print("SECONDARY  accuracy (noise-floored, descriptive only)")
    print("=" * 78)

    def cap_acc(cap: str | None, arm: str) -> list[float]:
        """Run-level PRODUCTION accuracy (scored by the product, judge included).

        Read from benchmark-report.json rather than recomputed, so the secondary
        endpoints use exactly the scoring the product uses. ABS has no
        per-question dump, so this is the only place it can be measured.
        """
        out = []
        for rep in data["reports"][arm]:
            if rep is None:
                continue
            v = rep["accuracy"] if cap is None else rep["perCapability"].get(cap, {}).get("accuracy")
            if v is not None:
                out.append(100.0 * v)
        return out

    def q_acc(cap: str, arm: str, i: int) -> float:
        """Accuracy recomputed from the per-question dump, as a cross-check."""
        sel = [q for q in qs if q["capability"] == cap]
        return 100.0 * mean(
            [1.0 if correct(q["answers"][arm][i], q["gold"]) is True else 0.0 for q in sel]
        )

    print(f"{'group':<10}{'control':>22}{'treatment':>22}{'delta':>9}{'perm p':>9}")
    for label, cap in (
        ("ALL", None),
        ("TR", "TR"),
        ("IE", "IE"),
        ("MR", "MR"),
        ("KU", "KU"),
        ("ABS", "ABS"),
    ):
        c, t = cap_acc(cap, C), cap_acc(cap, T)
        if not c or not t:
            continue
        p = perm_test_p(c, t)
        print(
            f"{label:<10}{mean(c):>8.2f}% [{min(c):.1f}-{max(c):.1f}]"
            f"{mean(t):>10.2f}% [{min(t):.1f}-{max(t):.1f}]"
            f"{mean(t) - mean(c):>+9.2f}{p:>9.3f}"
        )
    print("  (perm p floor with 4+4 runs = 0.014; not an acceptance criterion)")

    print("\n  cross-check: reported vs recomputed TR accuracy")
    for arm in (C, T):
        rep = cap_acc("TR", arm)
        rec = [q_acc("TR", arm, i) for i in range(len(rep))]
        print(f"    {arm:<10} reported {mean(rep):6.2f}%   recomputed {mean(rec):6.2f}%")
    print("    (recomputed counts only exact/numeric hits and defers the rest to a")
    print("     judge it cannot run offline, so it is a LOWER BOUND, not a dispute)")

    # ---------------------------------------------------------------- GUARDS
    print("\n" + "=" * 78)
    print("GUARDS")
    print("=" * 78)

    # G1 G2: bucket-level regressions inside TR, by temporal kind.
    #
    # The thresholds are NOT "0 regressions". They are the maxima observed over
    # all 35 possible 4v4 splits of a temporal-NULL A/B (ab_turn, whose two arms
    # are byte-identical in temporal-engine.ts). Demanding fewer regressions than
    # the null itself produces would reject a fix that changed nothing.
    # See tr_guard_noise_floor.py.
    NULL_MAX_LOSSES = {
        "two-event relative": 0,
        "single-event relative": 1,
        "interval": 0,
        "ordering": 3,
        "other/eventLookup": 1,
    }
    print("G1/G2  bucket-level regressions within TR")
    print("       threshold = max losses over 35 null 4v4 splits of ab_turn")
    # Only `relative` questions can be affected: `hasSecondEventReference` is
    # consulted inside `case 'relative'` alone. `interval` and `ordering` are
    # the in-path control group; `other`/`eventLookup` return null before the
    # switch, so the fix is unreachable for them and any movement is drift.
    UNREACHABLE = {"other/eventLookup"}
    for label, sel in (
        ("single-event relative", [q for q in qs if q["kind"] == "relative" and not q["twoEvent"]]),
        ("two-event relative", two),
        ("interval", [q for q in qs if q["kind"] == "interval"]),
        ("ordering", [q for q in qs if q["kind"] == "ordering"]),
        ("other/eventLookup", [q for q in qs if q["kind"] in ("other", "eventLookup")]),
    ):
        if not sel:
            continue
        gains = losses = 0
        for q in sel:
            c_ok, t_ok = score(q["answers"][C], q["gold"]), score(q["answers"][T], q["gold"])
            if t_ok and not c_ok:
                gains += 1
            elif c_ok and not t_ok:
                losses += 1
        cb = sum(score(q["answers"][C], q["gold"]) for q in sel)
        tb = sum(score(q["answers"][T], q["gold"]) for q in sel)
        tol = NULL_MAX_LOSSES.get(label, 0)
        if label in UNREACHABLE:
            verdict = "n/a (fix unreachable: returns null before the switch)"
        else:
            verdict = "PASS" if losses <= tol else "FAIL"
        # Per-run correctness exposes tie artifacts. The bucket rule scores a
        # 2/2 tie as wrong even when every run answered correctly in a different
        # surface form, so a loss that shows up here but not per-run is an
        # artefact of the metric, not a regression.
        cr = 100.0 * mean([mean([1.0 if correct(a, q["gold"]) is True else 0.0
                                 for a in q["answers"][C]]) for q in sel])
        trr = 100.0 * mean([mean([1.0 if correct(a, q["gold"]) is True else 0.0
                                  for a in q["answers"][T]]) for q in sel])
        print(
            f"  {label:<24} n={len(sel):<4} bucket {cb:>3} -> {tb:>3}   "
            f"+{gains} -{losses}  (null<={tol})   {verdict}"
        )
        print(f"  {'':<24} per-run mean {cr:5.2f}% -> {trr:5.2f}%  ({trr - cr:+.2f}pp)")

    # G3: outside TR. `answerTemporal` is reached only when
    # `q.capability === 'TR'` (benchmark.ts), so the fix cannot execute for any
    # of these capabilities. `own spread` is therefore context, not a verdict: a
    # movement here is drift by construction, and is reported, not gated.
    print("\nG3  capabilities outside TR (structurally unreachable by the fix)")
    for cap in ("IE", "MR", "KU", "ABS"):
        c, t = cap_acc(cap, C), cap_acc(cap, T)
        if not c or not t:
            print(f"  {cap:<4} no run-level data")
            continue
        n = next(
            (
                v["perCapability"][cap].get("total")
                for v in data["reports"][T]
                if v and cap in v["perCapability"]
            ),
            0,
        ) or 0
        spread = max(max(c) - min(c), max(t) - min(t))
        d = abs(mean(t) - mean(c))
        print(
            f"  {cap:<4} n={n:<4} control {mean(c):6.2f}%  treatment {mean(t):6.2f}%  "
            f"delta {mean(t) - mean(c):+6.2f}pp  own spread {spread:5.2f}pp  "
            f"{'within spread' if d <= spread else 'exceeds spread (drift, not regression)'}"
        )

    # G4: TR abstention. RATES must be compared, not counts: the two arms do not
    # necessarily hold the same number of runs (a run can fail and be replaced),
    # and dividing both by the control's denominator understates the treatment.
    print("\nG4  TR abstention rate")
    tr = [q for q in qs if q["capability"] == "TR"]
    rates = {}
    for label, arm in (("control", C), ("treatment", T)):
        tot = sum(sum(q["abstained"][arm]) for q in tr)
        den = len(tr) * len(arms[arm])
        rates[label] = 100.0 * tot / den if den else 0.0
        print(f"  {label:<10} {tot}/{den} = {rates[label]:.2f}%")
    print(
        f"  {'PASS' if rates['treatment'] <= rates['control'] else 'FAIL'}  "
        f"(treatment must not abstain more; delta "
        f"{rates['treatment'] - rates['control']:+.2f}pp)"
    )


if __name__ == "__main__":
    main()
