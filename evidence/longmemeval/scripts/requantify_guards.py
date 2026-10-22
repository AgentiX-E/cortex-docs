#!/usr/bin/env python3
"""
Re-quantify the ablation guards against a same-batch, cache-sharing reference.

Why this exists
---------------
The historical guard numbers were produced by ablation runners in which each arm
allocated its own answer cache. The hosted endpoint is not reproducible across
calls even at `temperature=0`, so two arms with an identical configuration could
disagree on a handful of questions purely from re-querying the same prompt. Every
historical delta therefore carries an unknown non-reproducibility term in ADDITION
to the effect it claims to measure.

`20592f2` shares one answer cache across both arms of every ablation. Where the
arms render byte-identical prompts this makes the comparison exactly paired and
0/0 discordant by construction; where the prompts differ (MR, whose arms differ in
`aggregationPrompt`) it removes the term only on any prompt both arms happen to
render. This script re-reads the guards from a post-fix run and reports each
guarantee in QUESTIONS first, next to the between-run noise floor it must clear.

The floor is not a fixed constant: it is the range observed across config-identical
runs of the same endpoint. A guard whose net delta does not exceed the floor is
indistinguishable from re-running the benchmark, regardless of its McNemar p-value
— McNemar asks whether the discordant pairs are directionally consistent, not
whether the net movement is large enough to survive endpoint drift.

Usage:
  requantify_guards.py RUN_DIR [RUN_DIR ...]

Reports every `benchmark-*-ablation-report.json` found under each RUN_DIR.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The between-run noise floor measured over four config-identical runs at
# 2c2c635 (see analysis/verdicts/p5-verdict.md): 11 questions overall, 2.20 pp.
# Per-capability ranges govern a capability-scoped guard, because a TR-only
# comparison (127 questions) has a different floor from the full 500.
#
# The churn band is the same measurement expressed as discordant pairs: across
# every pair of those four runs the arms disagreed on 21–25 questions (mean 23.2)
# of 470 diagnostically-covered questions, i.e. ~4.9%. A guard's churn is scaled
# to its own n before being compared to that band, because an MR guard (n=121)
# and a TR guard (n=127) are not the 470-question population the band came from.
FLOOR_OVERALL_Q = 11
FLOOR_OVERALL_PP = 2.20
FLOOR_PER_CAPABILITY_Q = {"IE": 1, "MR": 6, "KU": 3, "TR": 4, "ABS": 1}
CHURN_BAND_Q = (21, 25)
CHURN_BAND_N = 470


def wilson(correct: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval — behaves at the small samples these guards use."""
    if total == 0:
        return (0.0, 0.0)
    phat = correct / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    half = z * ((phat * (1 - phat) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(broken: int, repaired: int) -> float:
    """Two-sided exact McNemar p-value on the discordant pairs."""
    n = broken + repaired
    if n == 0:
        return 1.0
    k = min(broken, repaired)
    # 2 * P(X <= k) for X ~ Binomial(n, 0.5), capped at 1.
    from math import comb

    tail = sum(comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def load_guard(path: Path) -> dict:
    report = json.loads(path.read_text())
    baseline = report["baseline"]
    feature = report["feature"]
    ablation = report["ablation"]
    total = baseline["metrics"]["total"]
    baseline_correct = baseline["metrics"]["correct"]
    feature_correct = feature["metrics"]["correct"]
    discordant = ablation.get("discordant", {})
    broken = discordant.get("baselineCorrectFeatureIncorrect", 0)
    repaired = discordant.get("baselineIncorrectFeatureCorrect", 0)
    return {
        "file": path.name,
        "dataset": report.get("dataset"),
        "baseline_name": baseline.get("name"),
        "feature_name": feature.get("name"),
        "total": total,
        "baseline_correct": baseline_correct,
        "feature_correct": feature_correct,
        "delta_q": feature_correct - baseline_correct,
        "delta_pp": (feature_correct - baseline_correct) / total * 100 if total else 0.0,
        "broken": broken,
        "repaired": repaired,
        "changed": broken + repaired,
        "baseline_rate": baseline_correct / total * 100 if total else 0.0,
        "feature_rate": feature_correct / total * 100 if total else 0.0,
        "baseline_ci": wilson(baseline_correct, total),
        "feature_ci": wilson(feature_correct, total),
        "mcnemar_p": mcnemar_exact(broken, repaired),
    }


def capability_of(guard: dict) -> str | None:
    """Infer the capability a guard is scoped to, from its own labels."""
    text = f"{guard['baseline_name']} {guard['feature_name']} {guard['dataset']}".lower()
    if "mr" in text:
        return "MR"
    if "tr" in text:
        return "TR"
    if "ku" in text:
        return "KU"
    if "abs" in text:
        return "ABS"
    if "ie" in text:
        return "IE"
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    run_dirs = [Path(p) for p in argv[1:]]
    guards: list[dict] = []
    for run_dir in run_dirs:
        for path in sorted(run_dir.rglob("benchmark-*-ablation-report.json")):
            guards.append(load_guard(path))

    if not guards:
        print("no `benchmark-*-ablation-report.json` found under the given run dirs")
        return 1

    print("# Guard re-quantification against a cache-sharing reference\n")
    print(
        "Re-reads every guard found under the given run dirs. The floor each guard\n"
        "must clear is the between-run range for its own scope, taken from four\n"
        "config-identical runs of the same endpoint (11 questions overall; 1–6\n"
        "questions per capability). A guide to how to read the table:\n"
        "\n"
        "- `delta (q)` is the net movement in questions. This is the number that has\n"
        "  to exceed the floor, and it is reported first because the percentage hides\n"
        "  the denominator.\n"
        "- `churn in/out` is the discordant-pair count. Two arms can churn heavily in\n"
        "  both directions and still post a small net delta; the net figure alone\n"
        "  would hide that, so both are shown.\n"
        "- `McNemar p` tests directional consistency of the discordant pairs. A small\n"
        "  p with a delta inside the floor means the arms moved consistently but not\n"
        "  by more than re-running the benchmark would move them.\n"
    )

    print("| guard | n | baseline | feature | delta (q) | delta (pp) | churn in/out | McNemar p |")
    print("|---|---|---|---|---|---|---|---|")
    for g in guards:
        print(
            f"| `{g['feature_name']}` | {g['total']} | "
            f"{g['baseline_correct']}/{g['total']} ({g['baseline_rate']:.1f}%) | "
            f"{g['feature_correct']}/{g['total']} ({g['feature_rate']:.1f}%) | "
            f"**{g['delta_q']:+d}** | {g['delta_pp']:+.2f} | "
            f"{g['repaired']}/{g['broken']} | {g['mcnemar_p']:.3g} |"
        )

    print("\n## Does each guard clear its noise floor?\n")
    print(
        "A guard clears the floor only if its net delta exceeds the between-run range\n"
        "for its scope; otherwise it is indistinguishable from re-running the same\n"
        "configuration. Churn is reported separately: high churn with a small net delta\n"
        "means the two arms disagree a lot in both directions, which a net figure hides.\n"
    )
    print("| guard | scope | delta (q) | floor (q) | clears floor? | churn | churn vs scaled band |")
    print("|---|---|---|---|---|---|---|")
    for g in guards:
        cap = capability_of(g)
        floor = FLOOR_PER_CAPABILITY_Q.get(cap, FLOOR_OVERALL_Q) if cap else FLOOR_OVERALL_Q
        clears = abs(g["delta_q"]) > floor
        churn = g["changed"]
        # Scale the 470-question churn band to this guard's n, then compare.
        scale = g["total"] / CHURN_BAND_N
        lo, hi = CHURN_BAND_Q[0] * scale, CHURN_BAND_Q[1] * scale
        if churn > hi:
            churn_note = f"**above** the band ({lo:.0f}–{hi:.0f} expected at n={g['total']})"
        elif churn >= lo:
            churn_note = f"inside the band ({lo:.0f}–{hi:.0f} expected at n={g['total']})"
        else:
            churn_note = f"**below** the band ({lo:.0f}–{hi:.0f} expected at n={g['total']})"
        print(
            f"| `{g['feature_name']}` | {cap or 'overall'} | {g['delta_q']:+d} | {floor} | "
            f"{'✅ yes' if clears else '❌ no'} | {churn} | {churn_note} |"
        )

    print("\n## Wilson 95% CIs (for reference; the paired test governs)\n")
    print("| guard | baseline 95% CI | feature 95% CI |")
    print("|---|---|---|")
    for g in guards:
        print(
            f"| `{g['feature_name']}` | "
            f"[{g['baseline_ci'][0]*100:.1f}, {g['baseline_ci'][1]*100:.1f}] | "
            f"[{g['feature_ci'][0]*100:.1f}, {g['feature_ci'][1]*100:.1f}] |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
