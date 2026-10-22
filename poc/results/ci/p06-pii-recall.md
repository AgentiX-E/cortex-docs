# POC-6: fail-closed at corpus scale

Corpus: `ai4privacy/pii-masking-200k`, 52173 rows scanned, **3000** kept (49173 dropped for carrying non-deterministic labels).
Every kept row carries only annotated identifiers, so the published policy requires it to stay private.

## The two numbers

| metric | value | bound |
| --- | --- | --- |
| leak (published to the shared store) | 1 / 3000 | Wilson 95% upper 0.19% |
| coverage (decided by an explicit rule) | 87.5% | 95% CI 86.2–88.6% |

## By category

| category | n | leak | leak upper | coverage | top rule |
| --- | --- | --- | --- | --- | --- |
| strong-pii | 2524 | 1 | 0.2% | 88.6% | strong-pii: 1181 |
| credential | 476 | 0 | 0.8% | 81.3% | credential: 248 |

## What it means

Leak is near zero **because `defer` lands private**, not because the patterns are exhaustive.
That is the whole design: the default is the safety property, and the rules exist to keep the
card queue short. Which means the quantity that needs a large n is *coverage*, and the quantity
that needs a large n for safety is "how often a publishing rule fires on a private row" — both
of which this corpus measures directly, at a denominator two orders of magnitude larger than
the hand-labelled set.

## Leaks found (these are the next rule bugs, not statistics)

- `org-knowledge` on pii01216: In our latest Quality Assurance meeting, we decided to conduct an audit of all our transactions, paying special attention to those from Home Loan Account with IBAN LV96INJD0N7MZO8346877.

