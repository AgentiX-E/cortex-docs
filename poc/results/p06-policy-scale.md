# POC-6: the rule layer on 1,467 candidate facts

Corpus: 10 CIMemories personas, **1467** attribute statements, 10 domains. The benchmark's GPT-5-generated share labels are not used.

## What this corpus can and cannot measure

| metric | value | bound |
| --- | --- | --- |
| publishing rule fired (opportunities to leak) | 0 / 1467 | 0 of them vetoed by an earlier private rule |
| leak, all rows | 0 / 1467 | NOT MEASURED — the corpus never gave the publishing rule a chance |
| coverage, all rows | 29.5% | 95% CI 27.2–31.9% |

**The leak count is not a measurement.** `org-knowledge` never matched a persona attribute, so this corpus cannot speak to false-share at all — and a Wilson bound over a mechanism that never ran would be a bound on nothing. What this corpus *does* measure is coverage, and it measures it well: 1,467 rows against 60.

## By domain

| domain | n | leak | coverage | top rule |
| --- | --- | --- | --- | --- |
| education | 151 | 0 | 6.0% | defer: 142 |
| employment | 151 | 0 | 19.9% | defer: 121 |
| finance | 152 | 0 | 91.4% | money: 136 |
| general | 107 | 0 | 12.1% | defer: 94 |
| health | 151 | 0 | 31.8% | defer: 103 |
| housing | 151 | 0 | 34.4% | defer: 99 |
| legal | 151 | 0 | 15.2% | defer: 128 |
| mental_health | 151 | 0 | 44.4% | defer: 84 |
| relationships | 152 | 0 | 13.2% | defer: 132 |
| schedule | 150 | 0 | 21.3% | defer: 118 |

## Every published row, verbatim

None.

