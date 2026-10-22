# POC: the experiments behind docs 01–04

Every quantitative claim in the design documents is produced here, by a script that a reviewer
can run. Nothing in this directory is product code; it exists so that a number in a doc has a
command behind it.

## Run

```bash
cd poc && npm install          # playwright-core + @sqlite.org/sqlite-wasm, no app dependencies
npm run p02                    # vector scan cost (Node)
npm run p03                    # federation semantics (Node)
npm run p04                    # disclosure rules on 60 labelled real utterances
npm run p05                    # write/read boundary end to end, plus the A1/A4/A5 ablations
npm run p06                    # the rule layer on 1,467 candidate facts (coverage at scale)
python3 p06-policy-scale/fetch.py p06-policy-scale/statements.json   # regenerate the corpus
npm run p01                    # SQLite-WASM on OPFS in Chromium, across a browser restart
```

Outputs land in `results/` as both `.json` (the numbers) and `.md` (the table a doc quotes).
`p01` needs a Chromium binary; set `CHROMIUM_PATH` if the default Playwright cache path differs.

### The corpus is not committed

`p04` reads `p04-triage-rules/corpus.json` (6,000 user turns of LongMemEval-S) only through
`extract.mjs`. That file is a derived copy of a public benchmark and is deliberately **not** in this
repository; what the measurement needs is the 60 labelled rows in `labels.json`, which are committed,
and `run.mjs` reads nothing else. To regenerate the corpus from a benchmark artifact you already have:

```bash
python3 - <<'PY'
import json, re
d = json.load(open('run-<id>/benchmark-cortex-memory-ablation-report.json'))
seen = {}
for q in d['questions']:
    for t in q['turns']:
        text = t['text']
        if not re.match(r'^\[[^\]]+\]\s*user:', text):
            continue
        body = re.sub(r'\s+', ' ', re.sub(r'^\[[^\]]+\]\s*user:\s*', '', text)).strip()
        if len(body) >= 40:
            seen.setdefault(body, 0)
json.dump({'turns': list(seen)[:6000]}, open('poc/p04-triage-rules/corpus.json', 'w'))
PY
node p04-triage-rules/extract.mjs   # -> candidates.json (1,138 facts)
node p04-triage-rules/run.mjs       # -> results/p04-triage-rules.{json,md}
```

This is also why the reported metric is reproducible while the text is not redistributed: the
labelled rows are the input, the corpus is only how they were sampled.

## What each POC answers, and what it cannot

| POC | Question | Cannot answer |
| --- | --- | --- |
| `p01-browser-storage` | Does SQLite-WASM on OPFS work in a Worker, survive a browser restart, and what does the KV workload cost? | Safari. The VFS exercised is the access-handle pool, which is the one PGlite's docs say breaks in Safari on a 252-handle limit. |
| `p02-vector-scan` | What does an exact cosine scan cost, and what does the storage dtype buy? | Wasm SIMD. It is plain JS, so the int8 result is a memory result only. |
| `p03-federation` | Does a router over two stores hold the privacy boundary, and what must it refuse? | Speed, and real cross-store durability. Cross-store atomicity is refused by design. |
| `p04-triage-rules` | Does a deterministic rule layer keep private facts out of the shared store, and how much of the traffic does it decide? | Anything about the LLM proposer, which needs a provider. The rule layer is measured alone, on purpose. |
| `p05-read-side` | Does the boundary hold once the rules, two stores and the read-side assembler are wired together, and what does holding it cost in reachable evidence? | Retrieval quality (60 rows are the whole corpus), the proposer, real users, non-English text. |
| `p06-policy-scale` | Does the coverage number survive two orders of magnitude more rows, and does the rule layer hold on facts that are already atomic? | False-share: the publishing rule never fires on persona attributes, so the leak column is deliberately reported as *not measured*. |

## The method rules these POCs follow

1. **A zero is a bound, not a rate.** `p04` reports 0 false-shares out of 12 gold-private rows as
   a Wilson 95% upper bound of 24.2%, not as "never".
2. **A benchmark's bookkeeping can masquerade as its algorithm.** `p02`'s first version reported
   f32 as three times slower than f64 because the top-k sorted on every candidate; the corrected
   insertion buffer moved the same measurement by 2×. The wrong numbers are kept in the docstring.
3. **A check that cannot fail is not a check.** `p03`'s first draft had `async () => true` in an
   assertion; it is removed, not commented out.
4. **Measure in the runtime you ship.** `p01` and `p02` measure the same scan in Chromium and in
   Node, and the browser is 1.7× faster, so the browser number is the one the docs quote and Node
   is kept as an upper bound.
5. **Never tune a rule to the label you just measured, except to fix a word-sense bug.** The one
   change made after seeing the gold set (`raise` firing on "raise funds") is recorded in
   `p04-triage-rules/rules.mjs` and it moved no metric.
6. **A zero is only a measurement if the mechanism that produces ones ran.** `p06` counts how
   often the *publishing* rule matched before it reports any leak figure; when that count is 0 the
   leak bound is printed as `NOT MEASURED` rather than as a Wilson interval over nothing. The
   same discipline as `p04`'s upper bound, applied one level down.
7. **A guard that never fires in a clean run has not been tested.** `p05`'s scope guard is
   redundant while the writer is correct, so it is exercised by injecting a private row into the
   shared store on purpose. With the guard on the run refuses to assemble a prompt; with it off
   the same row reaches the window. A guard only shown to pass is indistinguishable from one that
   cannot fail — the same defect `p03`'s `async () => true` assertion had.
