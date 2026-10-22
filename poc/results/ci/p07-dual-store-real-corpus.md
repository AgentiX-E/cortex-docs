# POC-7: the split applied to the evidence a real run admitted

Source: `run-39699987781/benchmark-cortex-memory-ablation-report.json` — 500 questions, **59675** admitted turns, 4 runs, dataset `longmemeval`.
Every turn the reader was actually shown is classified by the shipped rule table.

## What a shared task would have left

| metric | value | bound |
| --- | --- | --- |
| turns a shared task could read | 310 / 59675 = 0.52% | 95% CI 0.46–0.58% |
| questions with an empty shared window | 318 / 500 = 63.6% | not "less evidence" — nothing at all |
| questions with at most half the turns shareable | 500 / 500 | the population a shared task would be operating on |
| publishing rule matched | 413 turns | 103 of them (24.9%) vetoed by an earlier private rule |

## Where the decisions come from

| rule | turns | share |
| --- | --- | --- |
| defer | 52019 | 87.2% |
| money | 2726 | 4.6% |
| health | 2449 | 4.1% |
| family | 1153 | 1.9% |
| third-party | 539 | 0.9% |
| org-knowledge | 310 | 0.5% |
| credential | 166 | 0.3% |
| strong-pii | 164 | 0.3% |
| career-status | 149 | 0.2% |

## By speaker

| role | turns | shared | shared rate |
| --- | --- | --- | --- |
| user | 54316 | 256 | 0.47% |
| assistant | 5359 | 54 | 1.01% |

