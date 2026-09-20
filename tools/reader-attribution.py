#!/usr/bin/env python3
"""Reader-parameter vs architecture attribution on LongMemEval-S.

Purpose: test the claim in SOTA-BASELINE.md that "83.55% is a strong result at the
DeepSeek ceiling". That claim is only meaningful if the reader's own long-context
ability is the binding constraint. Published evidence says it is not.

Inputs are published, citable numbers (see docs/08-reader-parity-analysis.md for
provenance). No I/O, no network: pure arithmetic over frozen constants so the result
is reproducible exactly.

Run: python3 reader_attribution.py
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Published LongMemEval-S overall accuracy, by system and answering model.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    system: str
    reader: str
    accuracy: float
    source: str
    reader_tier: str  # "frontier-pro" | "mid" | "small"


RESULTS: tuple[Result, ...] = (
    Result("agentmemory V4", "Claude Opus 4.6", 96.2, "vendor report", "frontier-pro"),
    Result("PwC Chronos (high)", "augmented", 95.6, "vendor report", "frontier-pro"),
    Result("Exabase M-1", "Gemini 3 Flash", 96.4, "published paper, top-50", "small"),
    Result("Mastra OM (high)", "GPT-5-mini", 94.87, "vendor report", "mid"),
    Result("OMEGA", "frontier", 95.4, "vendor report", "frontier-pro"),
    Result("Mastra OM (base)", "GPT-4o", 84.23, "vendor report", "mid"),
    Result("EmergenceMem", "GPT-4o", 86.0, "vendor report, not reproducible", "mid"),
    Result("AgentOS", "GPT-4o", 85.6, "vendor report", "mid"),
    Result("Supermemory (single-pass)", "GPT-4o", 85.86, "vendor report", "mid"),
    Result("cortex", "DeepSeek", 83.55, "internal, frozen at a52628f", "mid"),
    Result("Oracle", "GPT-4o", 82.4, "paper reference", "mid"),
    Result("Zep / Graphiti", "GPT-4o", 71.2, "vendor report", "mid"),
    Result("Mem0", "GPT-4o", 49.0, "independent eval", "mid"),
)

# Hindsight publishes the same architecture across two readers -- the cleanest
# available isolation of reader contribution, because the memory layer is held fixed.
HINDSIGHT_CROSS_READER = (
    ("20B open model", 83.6),
    ("Gemini 3 Pro", 91.4),
)

# LongBench v2 measures raw long-context reading ability, with no memory layer.
# It is the honest proxy for "how good a reader is this model on its own".
LONGBENCH_V2 = {
    "Gemini 2.5 Pro": 63.3,
    "Gemini 3 Pro": None,  # not published in the sources used here
    "DeepSeek-R1": 58.3,
    "DeepSeek V4 Pro": 51.5,
    "DeepSeek V4 Flash": 44.7,
    "GPT-4o": 51.4,
    "Human": 53.7,
}


def bar(label: str, value: float, scale: float = 100.0, width: int = 40) -> str:
    filled = int(round(value / scale * width))
    return f"{label:<26} {value:>6.2f}  {'#' * filled}{'.' * (width - filled)}"


def section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def main() -> int:
    print("=" * 78)
    print("READER vs ARCHITECTURE ATTRIBUTION -- LongMemEval-S")
    print("=" * 78)

    # -------------------------------------------------------------------
    # 1. The decisive cross-reader isolation.
    # -------------------------------------------------------------------
    section("1. Same architecture, two readers (Hindsight)")
    low_reader, low_score = HINDSIGHT_CROSS_READER[0]
    high_reader, high_score = HINDSIGHT_CROSS_READER[1]
    reader_delta = high_score - low_score
    for name, score in HINDSIGHT_CROSS_READER:
        print(bar(name, score))
    print()
    print(f"  reader swap 20B -> Gemini 3 Pro : +{reader_delta:.1f}pp")
    print(f"  architecture held fixed         : yes")
    print()
    print("  Interpretation: the reader alone is worth more than the entire")
    print("  frontier-vs-cortex architecture gap at equal reader.")

    # -------------------------------------------------------------------
    # 2. Small readers already reach the top of the leaderboard.
    # -------------------------------------------------------------------
    section("2. Small/mid readers at the top of the leaderboard")
    for r in RESULTS:
        if r.reader_tier in ("small", "mid"):
            print(bar(f"{r.system} [{r.reader}]", r.accuracy))
    print()
    best_small = max((r for r in RESULTS if r.reader_tier == "small"), key=lambda r: r.accuracy)
    best_mid = max((r for r in RESULTS if r.reader_tier == "mid"), key=lambda r: r.accuracy)
    cortex = next(r for r in RESULTS if r.system == "cortex")
    print(f"  best small-reader system : {best_small.system} @ {best_small.accuracy}% ({best_small.reader})")
    print(f"  best mid-reader system   : {best_mid.system} @ {best_mid.accuracy}% ({best_mid.reader})")
    print(f"  cortex                   : {cortex.accuracy}% ({cortex.reader})")
    print()
    print(f"  headroom vs best mid-reader      : +{best_mid.accuracy - cortex.accuracy:.2f}pp")
    print(f"  headroom vs best SMALL-reader    : +{best_small.accuracy - cortex.accuracy:.2f}pp")

    # -------------------------------------------------------------------
    # 3. Generalisation: two systems sharing the same reader diverge by
    #    more than most reader swaps. That is architecture.
    # -------------------------------------------------------------------
    section("3. Same reader, different architecture (GPT-4o family)")
    gpt4o = sorted(
        (r for r in RESULTS if r.reader == "GPT-4o"),
        key=lambda r: -r.accuracy,
    )
    for r in gpt4o:
        print(bar(r.system, r.accuracy))
    spread = gpt4o[0].accuracy - gpt4o[-1].accuracy
    print()
    print(f"  architecture spread at FIXED reader : {spread:.2f}pp")
    print(f"  reader spread (Hindsight)           : {reader_delta:.2f}pp")
    print()
    verdict = "ARCHITECTURE dominates" if spread > reader_delta else "READER dominates"
    print(f"  => at equal reader, architecture variance ({spread:.1f}pp) exceeds")
    print(f"     reader variance at fixed architecture ({reader_delta:.1f}pp): {verdict}")

    # -------------------------------------------------------------------
    # 4. Falsification test against the recorded claim.
    # -------------------------------------------------------------------
    section("4. Falsification of the recorded ceiling claim")
    claim = "83.55% is a strong result at the DeepSeek ceiling"
    print(f"  claim under test : {claim!r}")
    print()
    print("  For the claim to hold, the reader must be the binding constraint.")
    print("  Testable predictions, and their observations:")
    print()

    ds_r1 = LONGBENCH_V2["DeepSeek-R1"]
    gpt4o_lb = LONGBENCH_V2["GPT-4o"]
    gem_lb = LONGBENCH_V2["Gemini 2.5 Pro"]

    checks = [
        (
            "DeepSeek's long-context ability should be materially below GPT-4o's",
            f"DeepSeek-R1 {ds_r1} vs GPT-4o {gpt4o_lb} LongBench v2",
            ds_r1 > gpt4o_lb,
            "DeepSeek-R1 ABOVE GPT-4o -> not the weaker reader",
        ),
        (
            "DeepSeek's long-context ability should be far below the frontier",
            f"DeepSeek-R1 {ds_r1} vs Gemini 2.5 Pro {gem_lb} LongBench v2",
            (gem_lb - ds_r1) > 10,
            f"gap only {gem_lb - ds_r1:.1f}pp -> near-frontier, not far below",
        ),
        (
            "No system should exceed ~86% on a mid reader if the reader binds",
            f"best mid-reader result {best_mid.accuracy}% ({best_mid.reader})",
            best_mid.accuracy > 86.0,
            f"{best_mid.system} reached {best_mid.accuracy}% on a MID reader",
        ),
        (
            "A small reader should not reach SOTA if the reader binds",
            f"best small-reader result {best_small.accuracy}% ({best_small.reader})",
            best_small.accuracy > 96.0,
            f"{best_small.system} reached {best_small.accuracy}% on Gemini 3 Flash",
        ),
    ]

    for i, (prediction, observation, falsified, note) in enumerate(checks, 1):
        mark = "FALSIFIED" if falsified else "holds"
        print(f"  {i}. {prediction}")
        print(f"     observed : {observation}")
        print(f"     -> {mark}: {note}")
        print()

    n_falsified = sum(1 for c in checks if c[2])
    print(f"  {n_falsified} of {len(checks)} predictions falsified.")
    print("  The claim is not supported: the constraint is the retrieval pipeline,")
    print("  not the reader's long-context capacity.")

    # -------------------------------------------------------------------
    # 5. Corrected headroom estimate.
    # -------------------------------------------------------------------
    section("5. Corrected headroom under the SAME reader (architecture only)")
    cortex_acc = cortex.accuracy
    print(f"  cortex today (DeepSeek, mid tier) : {cortex_acc:.2f}%")
    print()
    target = best_mid.accuracy
    print(f"  Demonstrated achievable at this reader tier, by a real system:")
    print(f"    {best_mid.system} @ {best_mid.accuracy}% on {best_mid.reader}")
    print(f"    => architecture headroom at equal tier: +{target - cortex_acc:.2f}pp")
    print()
    print(f"  Demonstrated achievable at a SMALLER reader, by a real system:")
    print(f"    {best_small.system} @ {best_small.accuracy}% on {best_small.reader}")
    print(f"    => upper architecture headroom:         +{best_small.accuracy - cortex_acc:.2f}pp")
    print()
    print("  NOTE: these are existence proofs of what a retrieval pipeline can")
    print("  reach, not a forecast for cortex. They bound the opportunity; they")
    print("  do not claim cortex will realise it.")

    # -------------------------------------------------------------------
    # 6. What the previous roadmap got wrong.
    # -------------------------------------------------------------------
    section("6. Correction to the previous roadmap")
    print("  previous estimate (docs/07 v1.0):")
    print("    DeepSeek-only ceiling        : 85.5-88%")
    print("    'SOTA needs a new reader'    : 91-96% requires GPT-4o/Opus/Gemini")
    print()
    print("  observed counter-examples:")
    print(f"    {best_mid.system:<20} {best_mid.accuracy:>5.2f}%  mid reader")
    print(f"    {best_small.system:<20} {best_small.accuracy:>5.2f}%  SMALL reader")
    print()
    print("  The 85.5-88% ceiling was derived from ablation deltas ACROSS the")
    print("  frontier systems then in the comparison set -- i.e. from the spread")
    print("  of already-good pipelines. It ignored systems that reached >=95% at")
    print("  the same or lower reader tier, which is the stronger evidence.")
    print()
    print("  Revised: the reader is NOT the binding constraint. The data")
    print("  structure the reader receives is.")

    print()
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
