Embedding: `openai-compatible` · model `embedding-3` · baseUrl `https://open.bigmodel.cn/api/paas/v4` · dimensions 1024

# Cortex Benchmark Report — `nl-abstain-feature`

- Dataset: `longmemeval+oracle` (500 questions)
- System under test: `nl-abstain-feature` vs baseline `nl-naive-baseline`
- Generated at: 2026-11-21T07:43:07.160Z
- Feature: `nl-abstain-feature` vs baseline `nl-naive-baseline`
- Feature config: `aggregationCritique=off`, `aggregationCritiquePerItem=off`, `candidateDiscrimination=off`, `entityIdentityClause=on`, `reranker=off`, `retrievalSides=off`
- Annotation version: `not applied`

## Ablation (abstention-aware accuracy)

| System | min | avg | max | median |
|---|---|---|---|---|
| nl-naive-baseline | 83.80% | 83.80% | 83.80% | 83.80% |
| nl-abstain-feature | 89.00% | 89.00% | 89.00% | 89.00% |

- Δ accuracy (feature − baseline): **+5.20%**
- Baseline 95% Wilson CI: **[80.31%–86.77%]**
- Feature 95% Wilson CI: **[85.95%–91.45%]**
- Paired McNemar p-value: **2.556e-6** (significant: yes)
- Discordant pairs: baseline-correct/feature-wrong = 3, baseline-wrong/feature-correct = 29
- Welch t-test p-value (over stochastic runs): **n/a (deterministic)** (significant: no)
- Cohen's d: **+∞**

## Per-capability breakdown (`nl-abstain-feature` arm)

| Capability | Accuracy (first repetition) | Total |
|---|---|---|
| IE | 95.33% | 150 |
| MR | 90.91% | 121 |
| KU | 86.11% | 72 |
| TR | 79.53% | 127 |
| ABS | 96.67% | 30 |

- Overall accuracy (`nl-abstain-feature`): 89.00%
- Abstention rate (`nl-abstain-feature`): 7.40%
- Abstention correct rate (`nl-abstain-feature`): 78.38%
- `accuracyEstimator: first-repetition` — the accuracy lines above and every `questions[].correct` are one pass; the mean over every pass is the line beginning “Overall accuracy over all runs”.

## Per-capability paired significance (McNemar + Wilson CI)

| Capability | Total | Baseline acc | Feature acc | b✓f✗ | b✗f✓ | McNemar p | Significant |
|---|---|---|---|---|---|---|---|
| IE | 150 | 96.67% | 95.33% | 2 | 0 | 5.000e-1 | no |
| MR | 121 | 90.91% | 90.91% | 0 | 0 | 1.000e+0 | no |
| KU | 72 | 86.11% | 86.11% | 0 | 0 | 1.000e+0 | no |
| TR | 127 | 80.31% | 79.53% | 1 | 0 | 1.000e+0 | no |
| ABS | 30 | 0.00% | 96.67% | 0 | 29 | 3.725e-9 | yes |

### Discordant questions (identity)

- Baseline-correct/feature-wrong (3): 5d3d2817, 3b6f954b, gpt4_8279ba03
- Baseline-wrong/feature-correct (29): 0862e8bf_abs, 15745da0_abs, bc8a6e93_abs, 19b5f2b3_abs, 29f2956b_abs, f4f1d8a4_abs, 88432d0a_abs, 80ec1f4f_abs, eeda8a6d_abs, 60bf93ed_abs, edced276_abs, gpt4_372c3eed_abs, 2311e44b_abs, e5ba910e_abs, a96c20ee_abs, ba358f49_abs, 09ba9854_abs, gpt4_70e84552_abs, gpt4_93159ced_abs, 982b5123_abs, c8090214_abs, gpt4_c27434e8_abs, gpt4_fe651585_abs, 6aeb4375_abs, 031748ae_abs, 2698e78f_abs, 2133c1b5_abs, 0ddfec37_abs, f685340e_abs

### What kind of change each flip was

| flip | baseline | treatment | count |
|---|---|---|---|
| recovered | declined | answered correctly | 0 |
| corrected | answered wrongly | answered correctly | 29 |
| declined | answered correctly | declined | 3 |
| missed | answered correctly | answered wrongly | 0 |

- **Two mechanisms moved together**: flips crossed the abstention line and changed content, so the net figure below is the sum of a response-shape effect and a knowledge effect and must not be reported as one of them.
- Decline flow (recovered + declined) = 3 against content flow (corrected + missed) = 29
- Identity: recovered + corrected = 29 is the bought count above, declined + missed = 3 is the sold count above — this table refines those two numbers and cannot disagree with them.
