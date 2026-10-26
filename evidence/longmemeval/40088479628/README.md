# Run `40088479628` — the run that measured both systems at once

`benchmark-cortex-memory.yml`, 2026-10-24T11:05:18Z, 40m15s, `limit=0` (all 500 questions),
`ablation_runs=1`, `temperature=0`.

This directory exists for one reason: **on 2026-10-27 the project discovered that its two benchmark
workflows write the same report headline for two different systems, and this run is the artifact that
makes the pair readable.** It was already on disk while a round was spent treating `81.0% → 44.2%` as an
end-to-end drift.

## What it measures

The ablation's two arms are constructed in one invocation and share one reader, one embedding model,
one answer cache and one judge:

| | accuracy | IE | MR | KU | TR | ABS |
| --- | --- | --- | --- | --- | --- | --- |
| `reference-pipeline` (baseline) | **43.40%** | 0.67% | 84.30% | 0.00% | 66.14% | 100% |
| `cortex-memory` (feature) | **80.80%** | 89.33% | 69.42% | 86.11% | 74.02% | 100% |

- Δ = **+37.40%**, McNemar **p = 1.694e-33**, discordant pairs **38 / 225** (baseline-correct-feature-wrong
  / baseline-wrong-feature-correct), over 500 questions.
- Both Wilson intervals: baseline **[39.12%, 47.78%]**, feature **[77.12%, 84.01%]**.

## Why those two rows settle the question

`benchmark.yml`'s feature arm (`nl-abstain-feature`) reads **43.80%** on run `40378588466`, and its five
capability rows match the **baseline** row above to within one repetition (`KU 1.39` vs `0.00`,
`TR 66.93` vs `66.14`). So `40378588466` and this run's baseline are the same system measured twice, four
days apart, on different commits.

`cortex-memory` is the system the archived `81.0%` (405/500, four-run mean) belongs to: its
`memoryArmConfig` line in `report.md` reads `maxPromptChars=48000`, `relevanceTopK=256`,
`relevanceSignal=retrieval-hybrid`, `evidenceRoles=user` on two routes, `maxTurnChars=400`,
`ask=enumerated` — which is `PREREGISTRATION-CORTEX-MEMORY-ARM.md` §10.3's adopted configuration.

## Files

| file | what it is |
| --- | --- |
| `report.md` | the artifact's own Markdown, unmodified |
| `ablation.json` | the same report as JSON, with two size fields removed — `questions` (24.8 MB) and `ablation.featureRetrievedContexts` (22.9 MB). Both systems, both per-capability tables, the paired counts, the exact p, every per-question answer and raw output are kept. |

The unpruned artifact is the job's own `benchmark-cortex-memory-ablation-report.json`. This run was
produced **before** the renderer began naming the arm in its title (cortex `0527acc`), so `report.md`
still opens with the bare `# Cortex Benchmark Report` — that is the state the fix was written against,
kept as it was published rather than re-rendered.
