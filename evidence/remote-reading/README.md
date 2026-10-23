# The remote backend, measured

Everything in this directory was produced by one dispatch of `measure-models.yml`
(run `39986122582`, commit `a928475f`), on a GitHub runner, with the org-level secrets that this
sandbox and this repository do not have. The readings are also committed by that workflow to a
`readings/<run id>` branch; they are copied here because this is the document set that quotes them.

| file | what it is |
|---|---|
| `dosage-remote.txt` | `a3-review.mjs dosage` over twenty cards built by `deepseek-chat` |
| `cards-remote.json` | the twenty cards: source sentence, atoms, profile, prompt version |
| `live-result-remote.json` | the sixty-sentence gate reading, per row |
| `gates-remote.log` | the same run's stdout, as the job printed it |
| `embedding-smoke.json` | Zhipu `embedding-3`, provenance and two cosines |

## The two numbers that matter

**Dosage: 15 of 20 cards carry two or more atoms (75.0%, threshold 50%)** — against **1 of 20 (5.0%)**
for the 0.5B checkpoint on the same fixture, the same gates and the same prompt. The A3 review has a
treatment for the first time; the reason it had none was capacity, not phrasing, which is what step 14
established by changing the prompt and watching the number not move.

**Sixty sentences: 52/60 usable proposals, against 45/60.** Paired: 43 both, 2 only-local, 9
only-remote, 6 neither — exact McNemar **p = 0.065**. Not below 0.05, so this is a direction, not a
verdict; saying "the API model is better" would be reading a threshold that was never crossed.

Three readings inside that table are worth more than the aggregate:

- **`ungrounded` 3 → 0.** The large model invented nothing. Every refusal it produced came from a rule
  (health 12, money 5, career-status 1, family 1), so of the two failure modes the gate exists for,
  the remote configuration has one.
- **`too-short` 2 → 0**, and **`failed:empty` 0 → 1**. The local model produced two atoms with no
  information in them; the remote model produced one reply with no atoms at all. Different failure,
  not absence of failure.
- **Atoms 48 → 89** on the same sixty sentences: roughly 1.9 per usable proposal against 1.1.

## What this does not show

- **Whether the atoms are good.** Nothing here is a human judgement. A card can carry two grounded,
  clean atoms that are both useless.
- **That the comparison was fair to the local model.** It ran on a CPU with q4 weights and a 192-token
  cap; the API model ran on somebody else's datacentre. 5.88 s/sentence against 0.91 s is a cost
  reading, not a quality one.
- **That `p = 0.065` would reproduce.** One dispatch, one model, and `temperature: 0` is the
  client's request rather than the provider's guarantee.
- **That 20 cards is enough for a rate.** It is enough to pass or fail a 50% gate. It is not enough to
  estimate where the rate sits.
- **Anything about a second API model.** `measure-models.yml` takes `model` as an input; only
  `deepseek-chat` was dispatched.

## The embedding reading

```
provider  openai-compatible   model  embedding-3   dimensions  1024
cosine(related) 0.9172        cosine(unrelated) 0.5489        1.49 s for three texts
```

`provider` is asserted by the workflow: if it came back `hash`, the job fails. That is the check that
the benchmark's retrieval numbers are not computed against 256-dimension hash vectors while the log
says "embedding".
