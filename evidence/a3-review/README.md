# The A3 review, as a page

`review-remote.html` — open it in any browser. No server, no network, no build step; the file is
self-contained by construction and the test suite asserts it (`src="http`, `fetch(`,
`XMLHttpRequest`, `@import` are all absent).

Twenty cards from `evidence/remote-reading/cards-remote.json` (DeepSeek, prompt
`triage-proposer/v2`), each shown twice: once as the sentence the person said, once as the atoms the
model split it into. Order alternates by index, so a fatigue effect lands on both arms.

## What a reviewer does

1. Open the file.
2. For each card: **accept** if a colleague reading it would know what to do; **dismiss** if not;
   **accept with edits** and retype anything you would change; **skip** to leave it out.
3. At the end, download the JSONL (or copy it out of the textarea).
4. Score it:

```
node tools/a3-review.mjs score --decisions a3-decisions.jsonl
```

Progress is kept in `localStorage` under a key that includes the prompt version, so closing the tab
does not lose anything and a different prompt does not resume this run.

## What the screenshots show

| file | what it is |
|---|---|
| `screen-card.png` | first card, sentence arm, 0 / 40 |
| `screen-progress.png` | after six judgements: progress bar, and card 4 in the **atoms** arm — the alternation, visible |

## What this page is not

- **It is not scored by the page.** `scoreA3` is the only implementation of the arithmetic, and the
  last screen prints the command instead of a verdict.
- **It is not a product surface.** It is an instrument for one pre-registered experiment, and it says
  so on its own first line.
- **It is not blind.** A reviewer editing a card knows whether they are editing a sentence or an
  atom. Hiding that would need a different interface, not a different flag, and it is recorded as a
  limitation of the measurement.
