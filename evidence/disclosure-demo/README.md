# The disclosure chain, recorded

One file: `transcript.txt`, the output of thirteen separate process invocations of
`tools/triage-demo.mjs` against two real SQLite files and a real 0.5B on-device model.
`replay.sh` is the exact sequence, so the file can be regenerated rather than trusted.

## What it shows

1. A credential is **not stored anywhere**, and no card exists for it.
2. A sentence a shared rule claims is stored shared and **never becomes a question**.
3. A deferred sentence becomes a card; the model splits it into three atoms; the person
   publishes **one** of them, and the shared store holds that one, not the paragraph.
4. The export carries `text` (what was published), `source` (what was said) and
   `proposed` (what the model offered) — the three things an auditor asks in order.
5. A draft for a shared task that copies a private sentence is **blocked** (an echo), and
   the same draft for a private task is **clear** — the owner may hear their own memory.
   A shared draft that cites a published fact is clear; one that cites nothing is not.

## What it does not show

- No human acceptance rate. Nothing here says the atoms are *good*, only that they are
  grounded, clean of withheld categories, and that publishing one publishes exactly one.
- One model, one checkpoint, one machine, greedy decoding. The same model split one
  sentence into three atoms and left another whole, and the transcript records both.
- `--llm openai` was not exercised: it needs a key, and this repository stores none.
  The recorded run used the local checkpoint.

The readings that matter are in `docs/04` §9.13; this directory holds the raw output the
section quotes.
