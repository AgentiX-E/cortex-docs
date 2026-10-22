# P7 plan — MR's remaining error, attributed and addressed

**Status**: awaiting approval. No code has been changed.

## 0. Why this iteration exists

`p6-verdict.md` §7 named one open question and it is now the only substantive
one left: **MR plateaus at ~79–84%** under a prompt that already forces
enumeration. Everything upstream of the answer — caches, pairing, diagnostics —
is verified correct, so the measurement is trustworthy. Whatever is left is a
real capability gap. This plan finds it and closes as much of it as the data
licenses.

Standing constraints, applied as usual: scientifically rigorous verification,
≥95% coverage on every dimension, real tests (no mocks where a real path can be
exercised), root-cause fixes only, English comments/docs/commits, committed as
`Lambertyan`.

## 1. What I measured before proposing anything

New script: `analysis/scripts/mr_attribution.py`. It needs no LLM and no judge —
each MR instance carries `answer_session_ids`, and the diagnostics record the
rendered `retrieved` text, so a gold session is either present in the evidence
handed to the model or it is not. Whitespace is normalised and a session counts
as present if any of four disjoint 200-char windows from its body appears
verbatim.

Result on run `34594513996` (121 instances, 102 correct = 84.3%):

| evidence state | n | correct | accuracy |
|---|---|---|---|
| **PRESENT** — every gold session in context | 99 | 88 | **88.9%** |
| **MISSING** — ≥1 gold session absent | 22 | 14 | **63.6%** |

- 19 errors total. **8 (42.1%) are retrieval-attributable**; 11 are extraction.
- **ERR = 0.63 × ERR_retrieval + 0.37 × ERR_extraction** (0.157 = 0.099 + 0.058).
- 5 abstentions, **0 correct**.

Two facts that matter for sequencing:

1. Retrieval holds a **1.40× leverage** on extraction (63.6% vs 88.9% on the
   same denominator). Fixing all 22 MISSING instances would be worth
   +0.099 accuracy; fixing all extraction errors only +0.058. Both are needed
   for SOTA, but retrieval is the larger and better-localised term.
2. `top1Score` barely separates correct (0.609) from wrong (0.582) — retrieval
   confidence is **not** the bottleneck. The failures are ordering/coverage, not
   confidence calibration.

## 2. Root cause of the MISSING bucket

Tracing the retrieval frame against the LongMemEval-S schema: every instance in
the S pool is **one session document**. `answer_session_ids` are therefore
*whole sessions*, not turns. Our renderer emits a session as interleaved
`[timestamp] role: text` lines and groups the 44 haystack sessions onto the
**same** date, because the dataset dates are day-granular. Two consequences:

- **Redundancy collapse.** 22 of 121 instances need more than one gold session;
  a few need three. The top-k frame has to hold *all* of them simultaneously,
  but several near-duplicate sessions on one date compete for the same slots.
- **No frame margin.** `retrieved` is truncated at ~20 012 chars (median
  16 723). With 44 same-date sessions rendered in full, the frame is full of
  topically adjacent sessions while a gold session falls off the end.

This is corroborated by the failure mode: the MISSING-but-wrong examples are
**off-by-±1 counts** (`3→2`, `2→3`, `4→5`, `2→1`) — exactly what you get when
one and only one of several required items is absent.

## 3. Root cause of the extraction bucket

The 11 PRESENT-but-wrong examples are not arithmetic noise. They are
**enumerate-then-count without an item ledger**: the model lists some items as
prose and then reports a count that does not follow from its own list
(`$3,750 → $8,750`, `4 → 6`, `3 → 4`). The prompt asks for an enumeration but
never forces the final number to be *derivable* from the listed items, so the
counting step is unconstrained.

## 4. The plan

### P0 — retrieval frame coverage (largest term)

1. **Measure frame slack first.** Before changing anything, instrument a run to
   record, per MR instance, how many haystack sessions were rendered versus how
   many the frame could hold. Do not guess the budget — read it.
2. **Guarantee frame coverage for repeated-date haystacks.** The principled fix
   is that the retrieval frame must not evict a session whose date matches a
   date already in the frame while slots remain unused. If dedup is collapsing
   same-date sessions, that is the bug; if the budget is simply exceeded, raise
   the per-instance frame to hold the instance's full haystack for MR
   specifically.
3. Only if (2) is insufficient: expand the query set. `expansionQueries` are
   already per-query and non-empty (119 distinct sets), so this is a last
   resort, not a first move.

### P1 — enforce the item ledger in the aggregation prompt

Change `buildAggregationQaPrompt` so the model must emit a numbered item list
and the answer must be stated as the count of that list. Add a self-consistency
check in the parser: if the enumerated list length disagrees with the stated
answer, prefer the list. This directly targets the 11 extraction errors and is
testable offline against frozen `llmRaw` outputs.

### P2 — abstention correctness

5 abstentions, 0 correct, all `reason: llm`. MR has `enableAbstention: false` in
the ablation arms, so this is main-report-only. Two of the five are MISSING — an
honest abstention that the judge scores wrong. Decide deliberately whether MR
abstention should exist at all, and make the judge's treatment of an abstention
explicit rather than incidental.

### Verification protocol (applies to every item)

- **Offline first.** P1 and P2 are verifiable against the frozen diagnostics
  (`llmRaw` + `retrieved` are recorded), so a large part of this can be validated
  without spending a benchmark run. Replaying the new parser over the 121 stored
  outputs gives a real before/after with zero API calls.
- **Paired, cache-shared ablation** for P0, with the pairing invariant checked by
  `validate_fix.py` — it must read **0 broken / 0 repaired** or the comparison is
  void.
- **Noise floor.** Every delta reported in **questions**, against the measured
  floor (MR-scoped 13 q; overall 11 q). A result below the floor is not a result.
- **Evidence of real effect**: `pnpm check` green, ≥95% on all four coverage
  dimensions, and a benchmark run whose artifacts are downloaded and analyzed
  before any claim is made.

## 5. What I will not do

- I will not raise the MR prompt's strictness without measuring, because a
  stricter judge that moves the number is indistinguishable from a grader change.
- I will not touch PC Causal — it is settled at −4% and stays disabled.
- I will not claim a win from a single run: three hits or it does not count.

## 6. Cost and sequencing

Offline work (P1 parser replay, P2 analysis) is free and comes first. P0 requires
one instrumentation run, then one paired ablation run (~65–80 min each) before
any conclusion. I will report the offline results before spending a run.
