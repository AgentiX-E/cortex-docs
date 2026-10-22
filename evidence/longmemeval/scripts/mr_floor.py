#!/usr/bin/env python3
"""
The MR-scoped noise floor, and the historical MR guard re-read against it.

The overall floor (11 questions, 2.20 pp) is measured on the full 500-question
graded sample. An MR-scoped guard is scored on 121 questions, so the overall
floor does not govern it — a comparison over a quarter of the sample has its own
sampling and endpoint variance. This script measures that floor directly, from
the same four config-identical runs the overall floor came from, using the
`featureCorrect` vectors the MR ablation report already carries.

`featureCorrect` is emitted per run in `sampleInstances` order, so the vectors
are positionally aligned across config-identical runs and can be compared
elementwise. That is the one place in this analysis where a positional join is
sound, and it is checked rather than assumed: every vector must be exactly 121
long, or the comparison is refused.

Usage:
  mr_floor.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import itertools
import json
import statistics
import sys
from pathlib import Path

MR_TOTAL = 121


def load(run_dir: Path) -> dict | None:
    """Read one run's MR ablation report and its per-question feature vector."""
    matches = sorted(run_dir.rglob("benchmark-mr-ablation-report.json"))
    if not matches:
        return None
    report = json.loads(matches[0].read_text())
    baseline, feature, ablation = report["baseline"], report["feature"], report["ablation"]
    vector = ablation.get("featureCorrect")
    return {
        "label": run_dir.name,
        "baseline": baseline["metrics"]["correct"],
        "feature": feature["metrics"]["correct"],
        "total": baseline["metrics"]["total"],
        "delta": feature["metrics"]["correct"] - baseline["metrics"]["correct"],
        "broken": ablation["discordant"]["baselineCorrectFeatureIncorrect"],
        "repaired": ablation["discordant"]["baselineIncorrectFeatureCorrect"],
        "vector": vector,
        "mcnemar_p": ablation.get("mcnemarPValue"),
    }


def spread(values: list[int]) -> dict:
    n = len(values)
    mean = sum(values) / n
    return {
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "mean": mean,
        "sd": (sum((v - mean) ** 2 for v in values) / n) ** 0.5,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    runs = [r for r in (load(Path(p)) for p in argv[1:]) if r is not None]
    if len(runs) < 2:
        print(f"need at least 2 runs with an MR ablation report, found {len(runs)}")
        return 1

    print(f"# MR-scoped between-run floor over {len(runs)} config-identical runs\n")
    print("| # | run | baseline | feature | delta (q) | delta (pp) | churn in/out |")
    print("|---|---|---|---|---|---|---|")
    for i, r in enumerate(runs, 1):
        print(
            f"| {i} | `{r['label']}` | {r['baseline']}/{r['total']} | {r['feature']}/{r['total']} | "
            f"{r['delta']:+d} | {r['delta']/r['total']*100:+.2f} | {r['repaired']}/{r['broken']} |"
        )

    print("\n## Spread of each quantity across runs\n")
    print("| quantity | series | range (q) | sd (q) | spread (pp) |")
    print("|---|---|---|---|---|")
    for key, label in (("baseline", "baseline correct"), ("feature", "feature correct"), ("delta", "delta")):
        s = spread([r[key] for r in runs])
        series = [r[key] for r in runs]
        print(
            f"| {label} | {series} | **{s['range']}** | {s['sd']:.2f} | {s['range']/MR_TOTAL*100:.2f} |"
        )
    churn = [r["broken"] + r["repaired"] for r in runs]
    s = spread(churn)
    print(f"| churn (discordant pairs) | {churn} | **{s['range']}** | {s['sd']:.2f} | {s['range']/MR_TOTAL*100:.2f} |")

    # Elementwise vector comparison: the floor for "how many questions does a
    # re-run move", which is a different question from "how much does the score
    # move", and the one that governs whether a guard is distinguishable from noise.
    vectors = [r["vector"] for r in runs]
    aligned = all(v is not None and len(v) == MR_TOTAL for v in vectors)
    print("\n## Per-question churn between run pairs (elementwise on `featureCorrect`)\n")
    if not aligned:
        print(
            "Refused: at least one run does not carry a "
            f"{MR_TOTAL}-long `featureCorrect` vector, so a positional join would "
            "mis-align the questions silently."
        )
        return 1
    flips: list[int] = []
    print("| pair | questions differing | of | rate |")
    print("|---|---|---|---|")
    labels = [r["label"] for r in runs]
    for a, b in itertools.combinations(range(len(runs)), 2):
        diff = sum(1 for x, y in zip(vectors[a], vectors[b], strict=True) if x != y)
        flips.append(diff)
        print(f"| {labels[a]} vs {labels[b]} | **{diff}** | {MR_TOTAL} | {diff/MR_TOTAL*100:.1f}% |")
    s = spread(flips)
    print(
        f"\nMR-scoped per-question churn: **{s['min']}–{s['max']} questions** "
        f"(mean {s['mean']:.1f}, sd {s['sd']:.2f}) over {len(flips)} run pairs.\n"
    )

    print("## Historical MR guards re-read against this floor\n")
    print(
        "Each row is a guard as historically reported. The floor below is the MR-scoped\n"
        "one measured above; a guard clears it only if its net delta exceeds it.\n"
    )
    print("| run | delta (q) | delta (pp) | MR floor (q) | clears? | churn | churn vs observed band |")
    print("|---|---|---|---|---|---|---|")
    for r in runs:
        delta = r["delta"]
        clears = abs(delta) > s["max"]
        churn_q = r["broken"] + r["repaired"]
        band = f"{s['min']}–{s['max']}"
        if churn_q > s["max"]:
            note = f"above the band ({band})"
        elif churn_q >= s["min"]:
            note = f"inside the band ({band})"
        else:
            note = f"below the band ({band})"
        print(
            f"| `{r['label']}` | {delta:+d} | {delta/r['total']*100:+.2f} | {s['max']} | "
            f"{'✅ yes' if clears else '❌ no'} | {churn_q} | {note} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
