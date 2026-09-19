#!/usr/bin/env python3
"""
Between-run variance analysis over config-identical benchmark runs.

Reads the artifacts of N runs of the *identical* configuration and reports, per
capability and overall:

  1. the correct-count series, in chronological order, so a monotonic trend
     (endpoint drift) is visually separable from stationary noise;
  2. the spread in QUESTIONS first and percentages second, because percentages
     hide the denominator and the denominator is what P4 got wrong twice;
  3. the per-question flip count between every run pair, joined on `question_id`.

The last figure is the one that matters. With two runs of the same configuration,
`flippedIn`/`flippedOut` is not an effect size — it is measurement noise, and an
arm must move more questions than that to be distinguishable from re-running the
benchmark.

Usage:
  analyze_variance.py RUN_DIR [RUN_DIR ...]

Each RUN_DIR must contain `benchmark-report.json` and the diagnostics files
(`benchmark-single-session-diagnostics.json`, `benchmark-mr-diagnostics.json`).
The directory name is used as the run label, so name them with the run id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CAPABILITIES = ["IE", "MR", "KU", "TR", "ABS"]

# The graded sample is 500 questions in this benchmark, but the analyzer reads it
# from the data rather than assuming, so it stays honest if the sample changes.
def load_run(run_dir: Path) -> dict:
    report = json.loads((run_dir / "benchmark-report.json").read_text())
    per_capability: dict[str, dict[str, int]] = report["feature"]["metrics"]["perCapability"]

    # Join key: question_id is the only identifier stable across runs. Question
    # text is not, and neither is position — a re-sampled or re-ordered run would
    # silently mis-align under a positional join, which is exactly the class of
    # error this analysis exists to expose.
    correctness: dict[str, bool] = {}
    for name in ("benchmark-single-session-diagnostics.json", "benchmark-mr-diagnostics.json"):
        path = run_dir / name
        if not path.exists():
            continue
        for record in json.loads(path.read_text()):
            correctness[record["question_id"]] = bool(record["correct"])

    return {
        "label": run_dir.name,
        "perCapability": {
            cap: {"correct": per_capability[cap]["correct"], "total": per_capability[cap]["total"]}
            for cap in CAPABILITIES
            if cap in per_capability
        },
        "correct": report["feature"]["metrics"]["correct"],
        "total": report["feature"]["metrics"]["total"],
        "correctness": correctness,
    }


def capability_of(question_id: str, runs: list[dict]) -> str | None:
    """Recover a question's capability from the diagnostics' own ordering."""
    return None  # replaced below; capability comes from the diagnostics record


def load_capabilities(run_dir: Path) -> dict[str, str]:
    """Map question_id -> capability using the diagnostics records themselves."""
    mapping: dict[str, str] = {}
    single = run_dir / "benchmark-single-session-diagnostics.json"
    if single.exists():
        for record in json.loads(single.read_text()):
            mapping[record["question_id"]] = record["capability"]
    mr = run_dir / "benchmark-mr-diagnostics.json"
    if mr.exists():
        for record in json.loads(mr.read_text()):
            mapping[record["question_id"]] = "MR"
    return mapping


def summarize(series: list[int], sample_sizes: list[int]) -> dict:
    n = len(series)
    lo, hi = min(series), max(series)
    mean = sum(series) / n
    # Population sd, matching the TypeScript analyzer: these are the runs that
    # happened, not a sample from a process model, and n-1 would be undefined at
    # n=1 and inflated at n=4.
    sd = (sum((v - mean) ** 2 for v in series) / n) ** 0.5
    smallest = min(sample_sizes)
    return {
        "n": n,
        "min": lo,
        "max": hi,
        "range_q": hi - lo,
        "mean": mean,
        "sd_q": sd,
        "spread_pp": (hi - lo) / smallest * 100,
        "accuracy": sum(series) / sum(sample_sizes),
    }


def check_pairing_invariant(run_dir: Path) -> list[str]:
    """
    Check the cache-sharing invariant on a run's own report.

    The main report's two arms share a query-expansion cache and an answer cache,
    so on any capability where the two arms have the same configuration they must
    agree question-for-question — i.e. zero discordant pairs. `ABS` is the one
    exception by design: the baseline disables abstention and so never returns
    `null`, making the 0 -> total abstention contrast the intended treatment.

    A non-zero discordant count on a non-ABS capability means either the arms were
    not actually identical or the answer cache was not shared, both of which
    silently add an LLM-non-reproducibility term to the comparison. Returns a list
    of human-readable violations; empty means the invariant holds.
    """
    report_path = run_dir / "benchmark-report.json"
    if not report_path.exists():
        return []
    ablation = json.loads(report_path.read_text()).get("ablation")
    if ablation is None:
        return []
    violations: list[str] = []
    for capability, stats in ablation.get("perCapability", {}).items():
        if capability == "ABS":
            continue
        broken = stats.get("baselineCorrectFeatureIncorrect", 0)
        repaired = stats.get("baselineIncorrectFeatureCorrect", 0)
        if broken or repaired:
            violations.append(
                f"{run_dir.name} {capability}: {broken} broken / {repaired} repaired "
                "on a shared-cache pair — the arms are not identically configured, "
                "or the answer cache was not shared"
            )
    return violations


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    run_dirs = [Path(p) for p in argv[1:]]
    runs = [load_run(d) for d in run_dirs]

    # Cache-sharing invariant, checked before any comparison is drawn: a violation
    # means the run's own paired arms were not exactly paired, so its within-run
    # numbers carry an LLM-non-reproducibility term. See p5-pairing-verdict.md.
    violations: list[str] = []
    for d in run_dirs:
        violations.extend(check_pairing_invariant(d))
    if violations:
        print("## Pairing invariant VIOLATED\n")
        for v in violations:
            print(f"- {v}")
        print()

    # Capability comes from diagnostics; a question absent from the diagnostics is
    # still counted in the overall series via the report's own `correct`.
    capabilities: dict[str, str] = {}
    for d in run_dirs:
        capabilities.update(load_capabilities(d))

    print(f"# Between-run variance over {len(runs)} config-identical runs\n")
    print("| # | run id | " + " | ".join(CAPABILITIES) + " | overall |")
    print("|---|---|" + "---|" * (len(CAPABILITIES) + 1))
    for i, run in enumerate(runs, 1):
        cells = [
            f"{run['perCapability'].get(cap, {}).get('correct', '—')}"
            f"/{run['perCapability'].get(cap, {}).get('total', '—')}"
            for cap in CAPABILITIES
        ]
        print(f"| {i} | `{run['label']}` | " + " | ".join(cells) + f" | {run['correct']}/{run['total']} |")

    print("\n## Spread per capability (questions first)\n")
    print("| capability | series (correct) | range (q) | sd (q) | spread (pp) | mean acc |")
    print("|---|---|---|---|---|---|")
    for cap in CAPABILITIES:
        observed = [r for r in runs if cap in r["perCapability"]]
        if not observed:
            continue
        series = [r["perCapability"][cap]["correct"] for r in observed]
        sizes = [r["perCapability"][cap]["total"] for r in observed]
        s = summarize(series, sizes)
        print(
            f"| {cap} | {series} | **{s['range_q']}** | {s['sd_q']:.2f} | {s['spread_pp']:.2f} | {s['accuracy']*100:.2f}% |"
        )
    overall_series = [r["correct"] for r in runs]
    overall_sizes = [r["total"] for r in runs]
    s = summarize(overall_series, overall_sizes)
    print(
        f"| **overall** | {overall_series} | **{s['range_q']}** | {s['sd_q']:.2f} | "
        f"{s['spread_pp']:.2f} | {s['accuracy']*100:.2f}% |"
    )

    print("\n## Coverage of the per-question analysis\n")
    # The diagnostics files cover IE/MR/KU/TR only — ABS questions carry no
    # per-question record. Stating this explicitly matters: a flip table that
    # silently covers 470 of 500 questions reads as if it covered all of them, and
    # the ABS block has the largest percentage spread of any capability.
    graded = runs[0]["total"]
    diagnosed = len(runs[0]["correctness"])
    print(
        f"- graded questions per run: **{graded}**\n"
        f"- questions with a per-question record: **{diagnosed}** "
        f"({diagnosed / graded * 100:.1f}%)\n"
        f"- not covered by the flip analysis: **{graded - diagnosed}** "
        f"(the ABS block, which has no per-question diagnostics)\n"
    )

    print("## Per-question flips between run pairs (joined on `question_id`)\n")
    print("| pair | compared | stable | flipped in | flipped out | changed | changed % |")
    print("|---|---|---|---|---|---|---|")
    pair_flips: dict[tuple[int, int], dict[str, dict[str, bool]]] = {}
    for a in range(len(runs)):
        for b in range(a + 1, len(runs)):
            first, second = runs[a], runs[b]
            shared = sorted(set(first["correctness"]) & set(second["correctness"]))
            stable = flipped_in = flipped_out = 0
            by_cap: dict[str, dict[str, bool]] = {}
            for qid in shared:
                f, t = first["correctness"][qid], second["correctness"][qid]
                if f == t:
                    stable += 1
                    continue
                if t:
                    flipped_in += 1
                    # Only count an increase as reliable if the question is
                    # genuinely correct in the second run; a flip out is
                    # symmetric, so record both directions per capability.
                else:
                    flipped_out += 1
                cap = capabilities.get(qid, "?")
                entry = by_cap.setdefault(cap, {"in": 0, "out": 0})
                entry["in" if t else "out"] += 1
            pair_flips[(a, b)] = by_cap
            changed = flipped_in + flipped_out
            rate = changed / len(shared) * 100 if shared else 0
            print(
                f"| {a+1}→{b+1} | {len(shared)} | {stable} | {flipped_in} | {flipped_out} | "
                f"**{changed}** | {rate:.2f}% |"
            )

    print("\n## Flips per capability, per pair\n")
    print("| pair | " + " | ".join(f"{c} in/out" for c in CAPABILITIES) + " |")
    print("|---|" + "---|" * len(CAPABILITIES))
    for (a, b), by_cap in pair_flips.items():
        cells = [f"{by_cap.get(c, {}).get('in', 0)}/{by_cap.get(c, {}).get('out', 0)}" for c in CAPABILITIES]
        print(f"| {a+1}→{b+1} | " + " | ".join(cells) + " |")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
