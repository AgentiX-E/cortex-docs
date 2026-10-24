# The A3 review, as a page

`review-remote.html` — open it in any browser. No server, no network, no build step; the file is
self-contained by construction and the test suite asserts it (`src="http`, `fetch(`,
`XMLHttpRequest`, `@import` are all absent).

Twenty cards from `evidence/remote-reading/cards-remote.json` (DeepSeek, prompt
`triage-proposer/v2`), each shown twice: once as the sentence the person said, once as the atoms the
model split it into. Order alternates by index, so a fatigue effect lands on both arms.

## What a reviewer does

1. Open the file.
2. For each card, answer **twice** — the same card comes back once as a paragraph and once as a list.
3. At the end, download the JSONL (or copy it out of the textarea).
4. Score it:

## The four buttons, and what each one is for

The question on every card is the same: **would a colleague be able to act on this, or could you
answer a question from it, as written?** The buttons differ only in what is wrong.

| Button | When | Example |
| --- | --- | --- |
| **Accept** (a) | Content is right and the wording is shippable. Complete, has a subject, sounds like you. | *"I work at Acme on the payments team, and I moved to Berlin in March."* |
| **Accept with edits** (e) | The content is worth keeping and the **wording** is not: filler at the front, two facts welded together, a pronoun with no referent, a fragment with no verb. Type the version you would keep, press Enter. | *"By the way, I've been really enjoying editing my photos in Lightroom - the online communities have been super helpful."* -> *"I edit photos in Lightroom and I am active in online photo-editing communities."* |
| **Dismiss** (d) | Nothing worth keeping, or nothing a colleague could use: a reaction, a pleasantry, a request you made of your assistant, a restatement of what the assistant just said, or something so vague it carries no information. | *"Thank you, that's really helpful!"* / *"Can you write the texts for the presentation ?"* (a task you gave the assistant, not a fact about you) |
| **Skip** (s) | You genuinely cannot judge: no context, or it is the same statement as an earlier card. **A skip costs the pair** — pairs are only scored when both presentations were judged, so N shrinks and the report says so. | A fragment like *"and the same for the other one"* with nothing before it |

Two rules that matter more than the labels:

- **Judge each showing on its own.** Do not try to remember what you said about the first one; the
  point of A3 is whether the presentation changes your decision, so a consistency check between the
  two showings would erase the effect being measured.
- **Do not try to guess which side the model wrote.** You will notice (one is a paragraph, one is a
  list) — that is a known limit of this measurement, recorded as such. Use the same standard on both.

## Redoing and resetting

The bar at the top of the page holds two controls, available from the first card to the last:

- **Undo last** — takes back the most recent judgement (or skip) and shows that card again.
- **Start over** — discards every judgement **recorded in this browser** for this prompt version, after
  a confirmation.

Progress is kept under a key that includes the prompt version, so a different prompt does not resume
this run, and closing the tab loses nothing. `Undo` and `Start over` were added after the first
attempt: both used to live inside the finish screen, which — see below — was never displayed.

## Two defects the first attempt found

The finish screen carried `.done{display:none}` in its stylesheet while the script revealed it with
`el.done.hidden = false`; an attribute cannot beat a class rule, so the fortieth click cleared the card
body and left **a blank page**. The step-16 end-to-end test passed anyway, because it read the hidden
textarea — reading a value is not clicking a button.

Because `Start over` lived inside that section, a person who wanted to start again at card seven had
no control at all. Both are fixed, and both are now covered by
`packages/cortex-eval/test/review-page/probe.mjs`, which drives a real Chromium and measures
`offsetHeight` rather than text (17 checks, with two injections confirming each check bites). The
record is `cortex/docs/FIX-REVIEW-PAGE-REDO.md`.

```
node tools/a3-review.mjs score --decisions a3-decisions.jsonl
```

Progress is kept in `localStorage` under a key that includes the prompt version, so closing the tab
does not lose anything and a different prompt does not resume this run.

## The result (one reviewer, one pass, 2026-10-24)

`decisions-remote.jsonl` is the export exactly as it came out of the page; `score-remote.txt` is the
verbatim output of `node tools/a3-review.mjs score --decisions decisions-remote.jsonl`.

```
20 pair(s), 1 discordant
  source  17/20 accepted (85.0%, 95% CI 64.0-94.8%), 0 edited
  atoms   16/20 accepted (80.0%, 95% CI 58.4-91.9%), 1 edited
  delta -5.0pp, exact McNemar p=1.0000
NO-DIFFERENCE
```

The verdict is the pre-registered one: `no-difference` was the expected outcome, and it is a result,
not a failure. With one discordant pair no exact McNemar can reach 0.05, so what this run establishes
is an **upper bound on the effect**, not an estimate of one.

### Split by whether the treatment actually fired

The dosage gate says 15 of the 20 cards carry two or more atoms; the other 5 show the same text
twice. That split is worth reporting, because the two halves answer different questions.

| Cards | n | accepted: sentence | accepted: atoms |
| --- | --- | --- | --- |
| the arms differ (the treatment) | 15 | **15** | **14** |
| the arms are the same text (a control nobody planned) | 5 | 2 | 2 |

- **The five identical pairs produced zero disagreements.** That is not evidence about atoms, and it is
  the most useful sanity check in the file: where the stimulus was literally the same twice, the
  reviewer gave the same answer twice.
- **Fifteen of fifteen split cards were accepted as a sentence; fourteen as atoms.** The single loss
  is `g04`, and the reason is visible in the proposal: the model cut
  *"By the way, I've been really enjoying editing my photos in Lightroom - the online communities I've
  joined have been super helpful…"* into three pieces, the last of which is
  *"getting feedback on my work"* — a fragment with no subject. Rejecting the atom set for containing
  a non-sentence is the rubric working as written.

### What the acceptance rate cannot see

85% against 80% is close to the ceiling, so this instrument cannot discriminate on a corpus where a
reviewer accepts almost everything. The signal that did appear is qualitative and points the other
way from "atoms are better": **splitting can manufacture a fragment, and a fragment loses the whole
card.** That suggests the next instrument should ask about the atoms themselves (does any atom fail to
be a claim?) rather than about the card's fate — recorded as a gap, not implemented here.

### One measurement defect the timing exposed

The score output prints a per-arm median elapsed time, and on this dataset it read
**6,605 ms (sentence) against 10,414 ms (atoms)** — which invites "atoms take longer to judge". The
timing says something else: the **first** showing took longer in **20 of 20** pairs, at a median of
21,948 ms against 2,446 ms. Reading a card is the cost; the second showing is a re-read.

The alternating order keeps that out of the verdict (both arms occupy the first position ten times),
but it does not make the per-arm median comparable — with ten cards per position, one slow card
landing in the atoms-first half moves that median by seconds. `positionEffect` now computes the
position split and the score output prints it beside the arm medians, labelled rather than suppressed.

## What the screenshots show

| file | what it is |
|---|---|
| `screen-card.png` | first card, sentence arm, 0 / 40 |
| `screen-progress.png` | after six judgements: progress bar, and card 4 in the **atoms** arm — the alternation, visible |

## A note on the two screenshots

The first commit carrying them published **corrupted copies**: the push tool sent every blob as
`encoding: "utf-8"` after reading it with `surrogateescape`, which is lossless for source code and
lossy for a PNG (118 KB on the remote for a 64 KB file). Its verification caught the mismatch after
the branch had moved, so the repair is this commit rather than an edit to that one. The tool now
uploads base64 and verifies before publishing; the bug and the ordering flaw are recorded in
`cortex/docs/04` and pinned by `tools/__tests__/test_push_blobs.py` in that repository.

## What this page is not

- **It is not scored by the page.** `scoreA3` is the only implementation of the arithmetic, and the
  last screen prints the command instead of a verdict.
- **It is not a product surface.** It is an instrument for one pre-registered experiment, and it says
  so on its own first line.
- **It is not blind.** A reviewer editing a card knows whether they are editing a sentence or an
  atom. Hiding that would need a different interface, not a different flag, and it is recorded as a
  limitation of the measurement.
