# assumption

Two files, both produced by one command with no model in it:

| file | produced by | what it is |
|---|---|---|
| `ablation-remote.txt` | `node tools/assumption-ablation.mjs --verbose` | the three arms, the per-family split, the four ablations, and every case's answer |
| `ablation-remote.json` | `node tools/assumption-ablation.mjs --json` | the same as data, for anyone who wants to recompute a delta |

The set is twelve cases generated in-repo (`packages/cortex-eval/src/assumption-ablation.ts`), each
isolating one family from the published literature: STALE Type I (co-referential conflict) and Type II
(propagated conflict), PACMI's stale-premise and historical arms, a conflict family where the correct
answer is "unknown", and a **false-stale control** where an update exists but lies outside the
question's instant, so marking it stale is the error.

Three things about this evidence that a reader should hold on to:

1. **It is deterministic.** No embedding model, no judge, no sampling. Two runs disagreeing is a bug,
   not noise, which is why the artefact can be committed rather than versioned by run id.
2. **It measures attribution, not effect size.** The baseline is a lexical tie-break, the conflicts are
   constructed, and there are twelve of them. The table says each mechanism moves the family it is
   aimed at and nothing else; it says nothing about how much any of this is worth on a real corpus.
3. **It does not measure discovery.** `invalidates` is declared per case, the same boundary PACMI
   draws. Whether a system can *notice* that an upstream change broke a downstream fact is a separate
   problem and is not claimed here.
