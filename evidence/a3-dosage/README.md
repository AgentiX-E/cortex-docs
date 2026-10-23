# A3's dosage, measured twice

A3 asks whether showing a card's **atoms** beats showing the **sentence** the person said. Before
spending anyone's clicks on that, the two arms have to actually differ — and in step 13 they did not:
fourteen of twenty cards showed the same text in both arms.

This directory is the follow-up. Two runs of `tools/a3-review.mjs prepare` over the same twenty rows,
with the same checkpoint, the same dtype, the same gates, and the same greedy decoding; the only
difference is one line of the prompt that says how to split a sentence.

| file | what it is |
|---|---|
| `cards-0.5b-v2.json` | 20 cards, prompt `triage-proposer/v2` |
| `cards-0.5b-v3.json` | the same 20 cards, prompt `triage-proposer/v3` (split rule only) |
| `dosage-v2.txt` | `dosage` output for the first |
| `dosage-v3.txt` | `dosage` output for the second |
| `network-nocall.json` | the `fetch` count during a real local proposal (load 0, infer 0) |

Reproduce (from the `cortex` repository, after `pnpm -r build`):

```
CORTEX_HF_ENDPOINT=https://hf-mirror.com \
  node tools/a3-review.mjs prepare --out cards.json --limit 20 --llm local --dtype q4
node tools/a3-review.mjs dosage --cards cards.json
```

## What the two runs say

Both fail the gate, at exactly the same rate: **1 of 20 cards carries two or more atoms (5.0%,
threshold 50%)**. Inside that tie, three cards moved in three different directions — one gained a
split, one lost a split it used to have, one kept a leading clause it used to trim. Net zero is not
"no change"; it is three changes that cancel.

The conclusion the numbers support: at this size, under-splitting is **capacity**, not instruction.
Writing the rule more forcefully does not buy the treatment. That is why the next step is a larger
model (API, or ≥1.5B locally) rather than another prompt revision.

## What this does not show

- **Nothing about atom quality.** One split does not mean a good split. `docs/04` §9.17 records the
  card whose three atoms collapsed into one — grounded, clean, and a third of the sentence.
- **Nothing about the API configuration.** There is no key on this host and the repository stores
  none, so the `remote` backend is unmeasured here. `profile-transport.test.ts` proves the wiring
  reaches a socket; it says nothing about what a larger model would produce.
- **Nothing about a larger local model.** The 1.5B q4 weights are 1,705 MB and the mirror served
  them at 0.28 MB/s; the download was stopped after 579 MB. The command is unchanged when the
  weights are available.
- Twenty cards from one fixture. Wide enough to reject the prompt hypothesis, not wide enough to
  estimate a rate.
