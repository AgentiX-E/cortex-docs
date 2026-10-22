"""Calibrate the guard noise floor from a temporal-NULL A/B.

Why this exists
---------------
The pre-registered guard G2 was "0 regressions among interval + ordering".
That criterion is only meaningful if a null comparison actually produces zero.

`/workspace/analysis/ab_turn` IS a temporal null: its control (183a3cc) and
treatment (db92e62) differ in the MR turn-recall channel only, and
`temporal-engine.ts` / `temporal.ts` are byte-identical between the two refs
(verified with `git diff 183a3cc db92e62 -- .../temporal-engine.ts`).

That means all 8 of its runs share one temporal code path, so ANY split of them
into 4 vs 4 is a valid null comparison. There are C(8,4)/2 = 35 distinct
splits. Enumerating them turns a single anecdote into a distribution, and lets
the acceptance threshold be set from data BEFORE the real A/B is read.

Usage: python3 tr_guard_noise_floor.py [root]
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

from ab_tr_two_event_analysis import bucket, correct, score  # reuse one scorer

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/analysis/ab_turn")


def main() -> None:
    data = json.loads((ROOT / "census.json").read_text())
    qs = data["questions"]
    arms = data["runs"]
    runs = sorted(arms["control"] + arms["treatment"])

    # The census stores answers grouped by arm, each array ordered by that arm's
    # sorted run list. Flatten to [control runs..., treatment runs...] so a
    # global index addresses one specific run.
    for q in qs:
        q["flat"] = list(q["answers"]["control"]) + list(q["answers"]["treatment"])
    assert all(len(q["flat"]) == len(runs) for q in qs), "run count mismatch"

    print(f"{len(runs)} runs, all with identical temporal code")
    print("enumerating every 4v4 split -> null distribution of guard statistics\n")

    GROUPS = {
        "two-event relative": [q for q in qs if q["twoEvent"]],
        "single-event relative": [
            q for q in qs if q["kind"] == "relative" and not q["twoEvent"]
        ],
        "interval": [q for q in qs if q["kind"] == "interval"],
        "ordering": [q for q in qs if q["kind"] == "ordering"],
        "other/eventLookup": [q for q in qs if q["kind"] in ("other", "eventLookup")],
    }

    buckets = {name: [] for name in GROUPS}
    hits = {name: [] for name in GROUPS}

    for left in combinations(range(len(runs)), 4):
        right = tuple(i for i in range(len(runs)) if i not in left)
        # Skip the mirrored duplicate: keep each unordered split once.
        if left[0] != 0:
            continue
        for name, sel in GROUPS.items():
            if not sel:
                continue
            gains = losses = 0
            cb = tb = 0
            for q in sel:
                ca = [q["flat"][i] for i in left]
                ta = [q["flat"][i] for i in right]
                c_ok, t_ok = score(ca, q["gold"]), score(ta, q["gold"])
                cb += c_ok
                tb += t_ok
                if t_ok and not c_ok:
                    gains += 1
                elif c_ok and not t_ok:
                    losses += 1
            buckets[name].append((cb, tb))
            hits[name].append((gains, losses))

    print(f"{'group':<24}{'n':>4}{'max losses':>12}{'p95 losses':>12}{'max |delta|':>13}")
    THRESHOLD = {}
    for name, sel in GROUPS.items():
        if not sel:
            continue
        rows = hits[name]
        losses = sorted(r[1] for r in rows)
        deltas = sorted(abs(a - b) for a, b in buckets[name])
        p95 = losses[min(len(losses) - 1, int(0.95 * (len(losses) - 1) + 0.5))]
        THRESHOLD[name] = max(losses)
        print(
            f"{name:<24}{len(sel):>4}{max(losses):>12}{p95:>12}{max(deltas):>13}"
        )

    print("\nInterpretation")
    print("  `max losses` is the worst regression count seen across all 35 null")
    print("  splits. A guard demanding fewer regressions than that is demanding")
    print("  less noise than the benchmark actually has, and would fail a fix")
    print("  that changed nothing. Set each guard at its null maximum.")

    # ------------------------------------------------------------------------
    # Capability-level DRIFT under the null.
    #
    # The #145 treatment moved KU by -1.97pp, which exceeds KU's own run-to-run
    # spread of 1.39pp and so looks like a regression. It cannot be one:
    # `answerTemporal` runs only when `q.capability === 'TR'`, so the fix is
    # unreachable for KU. The question is whether a movement that large is
    # ordinary drift, and the null splits answer it directly.
    print("\n" + "=" * 78)
    print("capability-level drift under the null (all 35 splits)")
    print("=" * 78)
    print(f"{'capability':<12}{'null max |delta|':>18}{'null p95 |delta|':>20}")
    for cap in ("TR", "IE", "MR", "KU", "ABS"):
        series = []
        for rep in data["reports"]["control"] + data["reports"]["treatment"]:
            if rep and cap in rep["perCapability"]:
                series.append(100.0 * rep["perCapability"][cap]["accuracy"])
        if len(series) != len(runs):
            continue
        deltas = []
        for left in combinations(range(len(runs)), 4):
            if left[0] != 0:
                continue
            right = [i for i in range(len(runs)) if i not in left]
            a = sum(series[i] for i in left) / 4
            b = sum(series[i] for i in right) / 4
            deltas.append(abs(a - b))
        deltas.sort()
        p95 = deltas[min(len(deltas) - 1, int(0.95 * (len(deltas) - 1) + 0.5))]
        print(f"{cap:<12}{max(deltas):>18.2f}{p95:>20.2f}")
    print("  A capability movement in the treatment arm is ordinary drift when it")
    print("  is at or below the null max for that capability.")


if __name__ == "__main__":
    main()
