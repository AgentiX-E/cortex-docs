# The disclosure chain, recorded

One file: `transcript.txt`, the output of eighteen separate process invocations of
`tools/triage-demo.mjs` against two real SQLite files and a real 0.5B on-device model.
`replay.sh` is the exact sequence, so the file can be regenerated rather than trusted.

## What it shows

1. A credential is **not stored anywhere**, and no card exists for it.
2. A sentence a shared rule claims is stored shared and **never becomes a question**.
3. A deferred sentence becomes a card; the model splits it into three atoms; the person
   publishes **one** of them, and the shared store holds that one, not the paragraph.
4. The export carries `text` (what was published), `source` (what was said) and
   `proposed` (what the model offered) — the three things an auditor asks in order.
5. Asking for the remote backend with no key **fails** with the names of the three variables, and
   does not fall back to the checkpoint.
6. A sentence a rule kept private can be **released** by its owner -- with the rule quoted at them
   first, a token typed, and a record left in a table of its own. Without the token the release is
   refused; the transcript shows both attempts.
7. A draft for a shared task that copies a private sentence is **blocked** (an echo), and
   the same draft for a private task is **clear** — the owner may hear their own memory.
   A shared draft that cites a published fact is clear; one that cites nothing is not.

## What it does not show

- No human acceptance rate. Nothing here says the atoms are *good*, only that they are
  grounded, clean of withheld categories, and that publishing one publishes exactly one.
- One model, one checkpoint, one machine, greedy decoding. The same model split one
  sentence into three atoms and left another whole, and the transcript records both.
- The remote backend was **not exercised with a key**: there is none on this host, and this
  repository stores none. What the transcript records is its failure path. `CORTEX_LLM_BACKEND=remote`
  with the three variables set runs the same commands against an API model.

The readings that matter are in `docs/04` §9.13; this directory holds the raw output the
section quotes.
