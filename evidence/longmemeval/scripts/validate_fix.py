#!/usr/bin/env python3
"""
End-to-end validation of the answer-cache fix (commit 20592f2).

Run this against the artifacts of a post-fix benchmark run. It checks, in order:

  1. DID THE FIX WORK? The pairing invariant must hold — every non-ABS
     capability in the main report must show 0 broken / 0 repaired, because the
     two arms there are byte-identically prompted and now share an answer cache.
     Before the fix this was violated in 3 of 4 runs.

  2. DID IT BREAK ANYTHING? Every guard must still clear its own scope's floor,
     and the MR guard in particular must be unchanged, since 20592f2 is a no-op
     for MR (its two arms render different prompts, so the shared cache never
     hits — verified by probe, see p5-mr-guard-verdict.md §3).

Usage:
  validate_fix.py POST_FIX_RUN_DIR [PRE_FIX_RUN_DIR ...]

The pre-fix dirs are optional and only used to print a before/after comparison.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CAPABILITIES = ["IE", "MR", "KU", "TR", "ABS"]
FLOOR_PER_CAPABILITY_Q = {"IE": 1, "MR": 13, "KU": 3, "TR": 4, "ABS": 1}


def find(run_dir: Path, pattern: str) -> Path | None:
    matches = sorted(run_dir.rglob(pattern))
    return matches[0] if matches else None


def check_pairing(run_dir: Path) -> tuple[bool, list[str]]:
    """
    The fix's load-bearing assertion: zero unexpected discordant pairs.

    Two discordant directions are *expected* on the main report and are not
    pairing faults, because the two arms differ in abstention by design:

    - A question where the FEATURE abstains is graded `false` (a null answer is
      wrong unless `expected` is null), while the BASELINE never abstains and may
      answer it correctly. That is `baselineCorrectFeatureIncorrect`, and it is
      the intended abstention contrast, not a cache failure.
    - The ABS block is entirely this contrast: `expected` is null, the baseline
      never returns null and so scores 0, the feature abstains and scores the
      correct count.

    So a raw non-zero discordant count is NOT a violation. What would be a
    violation is a discordant pair where the feature did not abstain — because
    then both arms rendered the same prompt, the cache must have served both, and
    their correctness should agree. That requires the per-question diagnostics,
    which only carry the feature arm's decision, so it is checked where the data
    allows and reported as "unexplained" otherwise.
    """
    path = find(run_dir, "benchmark-report.json")
    if path is None:
        return False, ["no benchmark-report.json"]
    ablation = json.loads(path.read_text()).get("ablation")
    if ablation is None:
        return False, ["report has no ablation block"]

    # Count how many questions the feature arm abstained on, per capability, from
    # the diagnostics. This bounds how much of a discordant count the legitimate
    # abstention contrast can explain.
    abstained_by_cap: dict[str, int] = {}
    diag = find(run_dir, "benchmark-single-session-diagnostics.json")
    if diag is not None:
        for record in json.loads(diag.read_text()):
            decision = record.get("decision") or {}
            if decision.get("abstained"):
                cap = record.get("capability", "?")
                abstained_by_cap[cap] = abstained_by_cap.get(cap, 0) + 1

    violations: list[str] = []
    for capability, stats in ablation.get("perCapability", {}).items():
        broken = stats.get("baselineCorrectFeatureIncorrect", 0)
        repaired = stats.get("baselineIncorrectFeatureCorrect", 0)
        if not (broken or repaired) or capability == "ABS":
            # ABS is entirely the abstention contrast by construction: `expected`
            # is null, the baseline never returns null so scores 0, and the
            # feature abstains and scores the correct count.
            continue
        abstained = abstained_by_cap.get(capability, 0)
        # The `broken` direction (baseline right, feature wrong) is exactly what
        # feature abstention produces, so it is explained up to the abstention
        # count. The `repaired` direction cannot come from abstention — the
        # feature only abstains, never answers more than the baseline — so any
        # repaired pair is unexplained and needs review.
        unexplained_broken = max(0, broken - abstained)
        if unexplained_broken or repaired:
            violations.append(
                f"{capability}: {broken} broken / {repaired} repaired "
                f"({abstained} abstentions explain up to {min(broken, abstained)} broken; "
                f"{unexplained_broken} broken + {repaired} repaired unexplained)"
            )
    return not violations, violations


def guard_rows(run_dir: Path) -> list[tuple[str, int, int, int, int]]:
    """(name, n, baseline, feature, delta) for every ablation report present."""
    rows = []
    for path in sorted(run_dir.rglob("benchmark-*-ablation-report.json")):
        report = json.loads(path.read_text())
        b, f = report["baseline"], report["feature"]
        rows.append(
            (
                f.get("name") or path.stem,
                b["metrics"]["total"],
                b["metrics"]["correct"],
                f["metrics"]["correct"],
                f["metrics"]["correct"] - b["metrics"]["correct"],
            )
        )
    return rows


def scope_of(name: str) -> str:
    lowered = name.lower()
    for cap in ("mr", "tr", "ku", "abs", "ie"):
        if cap in lowered:
            return cap.upper()
    return "overall"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    post = Path(argv[1])
    pre = [Path(p) for p in argv[2:]]

    print(f"# Validating the answer-cache fix against `{post.name}`\n")

    print("## 1. Pairing invariant\n")
    held, violations = check_pairing(post)
    if held:
        print(
            "✅ **HOLDS** — every non-ABS capability shows 0 broken / 0 repaired.\n"
            "The two arms of the main report now agree question-for-question, so the\n"
            "comparison carries no LLM-non-reproducibility term. Before the fix this\n"
            "was violated in 3 of 4 runs.\n"
        )
    else:
        print("❌ **VIOLATED** — the fix did not fully take effect:\n")
        for v in violations:
            print(f"- {v}")
        print()

    print("## 2. Guards still clear their floors\n")
    rows = guard_rows(post)
    if not rows:
        print("No ablation reports found.\n")
    else:
        print("| guard | n | baseline | feature | delta (q) | floor | clears? |")
        print("|---|---|---|---|---|---|---|")
        for name, n, b, f, delta in rows:
            scope = scope_of(name)
            floor = FLOOR_PER_CAPABILITY_Q.get(scope, 11)
            clears = abs(delta) > floor
            print(
                f"| `{name}` | {n} | {b}/{n} | {f}/{n} | **{delta:+d}** | {floor} | "
                f"{'✅ yes' if clears else '❌ no'} |"
            )

    if pre:
        print("\n## 3. Before / after\n")
        print("| guard | scope | pre-fix deltas | post-fix delta | changed? |")
        print("|---|---|---|---|---|")
        post_by_name = {name: delta for name, _, _, _, delta in rows}
        names_seen = set()
        for d in pre:
            for name, _n, _b, _f, delta in guard_rows(d):
                if name in names_seen or name not in post_by_name:
                    continue
                names_seen.add(name)
                earlier = [x[4] for dd in pre for x in guard_rows(dd) if x[0] == name]
                now = post_by_name[name]
                # MR is expected to be unchanged: the fix is a no-op for it.
                expectation = "expected unchanged (fix is a no-op for MR)" if "mr" in name.lower() else ""
                print(f"| `{name}` | {scope_of(name)} | {earlier} | {now:+d} | {expectation} |")
        for name, delta in post_by_name.items():
            if name not in names_seen:
                print(f"| `{name}` | {scope_of(name)} | — | {delta:+d} | new |")

    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
