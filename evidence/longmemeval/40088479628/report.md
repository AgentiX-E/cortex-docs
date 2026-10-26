# Cortex Benchmark Report

- Dataset: `longmemeval` (500 questions)
- Generated at: 2026-10-24T11:06:43.503Z
- Feature: `cortex-memory` vs baseline `reference-pipeline`
- Feature config: `cortexMemory=on`
- Memory arm config: `threshold=0`, `retrievalThreshold=0`, `sessionBudget=unbounded`, `sourceTrust=0.5`, `confidenceSignal=none`, `promptContract=abstention-evidence-blocks`, `relevanceSignal=retrieval-hybrid`, `relevanceTopK=256`, `maxTurnChars=400`, `maxPromptChars=48000`, `maxTurnCharsRoutes=multi-session+temporal`, `reviewPass=recover`, `selfConsistency=none`, `queryExpansion=none`, `evidenceRoles=user`, `evidenceRolesRoutes=multi-session+temporal`, `relevanceUnits=turn`, `embedding=openai-compatible/embedding-3@1024`, `embeddingPreflight=ok`
- Evidence rendering reached: 6 route(s) — `abstention`, `multi-session`, `temporal`, `knowledge-update`, `assistant`, `flat`
- Evidence ask: `enumerated`
- Evidence ask reached: 3 route(s) — `multi-session`, `flat`, `temporal`

## Ablation (abstention-aware accuracy)

| System | min | avg | max | median |
|---|---|---|---|---|
| reference-pipeline | 43.40% | 43.40% | 43.40% | 43.40% |
| cortex-memory | 80.80% | 80.80% | 80.80% | 80.80% |

- Δ accuracy (feature − baseline): **+37.40%**
- Baseline 95% Wilson CI: **[39.12%–47.78%]**
- Feature 95% Wilson CI: **[77.12%–84.01%]**
- Paired McNemar p-value: **1.694e-33** (significant: yes)
- Discordant pairs: baseline-correct/feature-wrong = 38, baseline-wrong/feature-correct = 225
- Welch t-test p-value (over stochastic runs): **n/a (deterministic)** (significant: no)
- Cohen's d: **+∞**

## Per-capability breakdown (feature system)

| Capability | Accuracy (first repetition) | Total |
|---|---|---|
| IE | 89.33% | 150 |
| MR | 69.42% | 121 |
| KU | 86.11% | 72 |
| TR | 74.02% | 127 |
| ABS | 100.00% | 30 |

- Overall accuracy: 80.80%
- Abstention rate: 15.00%
- Abstention correct rate: 40.00%

## Per-capability paired significance (McNemar + Wilson CI)

| Capability | Total | Baseline acc | Feature acc | b✓f✗ | b✗f✓ | McNemar p | Significant |
|---|---|---|---|---|---|---|---|
| IE | 150 | 0.67% | 89.33% | 0 | 133 | 1.837e-40 | yes |
| MR | 121 | 84.30% | 69.42% | 26 | 8 | 2.935e-3 | yes |
| KU | 72 | 0.00% | 86.11% | 0 | 62 | 4.337e-19 | yes |
| TR | 127 | 66.14% | 74.02% | 12 | 22 | 1.214e-1 | no |
| ABS | 30 | 100.00% | 100.00% | 0 | 0 | 1.000e+0 | no |

### Discordant questions (identity)

- Baseline-correct/feature-wrong (38): 0a995998, 28dc39ac, 2e6d26dc, gpt4_15e38248, 88432d0a, d682f1a2, 7024f17c, 60bf93ed, 9d25d4e0, a9f6b44c, 5a7937c8, 2b8f3739, gpt4_2f91af09, 81507db6, a11281a2, e6041065, d905b33f, a4996e51, 5025383b, a1cc6108, 92a0aa75, 6c49646a, ba358f49, d6062bb9, c18a7dc8, 21d02d0d, 9a707b81, gpt4_1d80365e, gpt4_8279ba02, gpt4_7a0daae1, 2ebe6c90, gpt4_e414231e, gpt4_7ca326fa, gpt4_65aabe59, d01c6aa8, gpt4_cd90e484, gpt4_4cd9eba1, gpt4_fe651585
- Baseline-wrong/feature-correct (225): e47becba, 118b2229, 51a45a95, 58bf7951, 1e043500, c5e8278d, 6ade9755, 6f9b354f, 58ef2f1c, f8c5f88b, 5d3d2817, 7527f7e2, c960da58, 3b6f954b, 726462e0, 94f70d80, 66f24dbb, ad7109d1, af8d2e46, dccbc061, c8c3f81d, 8ebdbe50, 6b168ec8, 21436231, 95bcc1c8, 0862e8bf, 853b0a1d, a06e4cfe, 37d43f65, d52b4f67, 25e5aa4f, caf9ead2, 8550ddae, 60d45044, 3f1e9474, 86b68151, 577d4d32, ec81a493, 15745da0, e01b8e2f, bc8a6e93, ccb36322, 001be529, b320f3f8, 19b5f2b3, 4fd1909e, 545bd2b5, 8a137a7f, 76d63226, 86f00804, 8e9d538c, 311778f1, c19f7a0b, 4100d0a0, 29f2956b, 1faac195, faba32e5, f4f1d8a4, c14c00dd, 36580ce8, 3d86fd0a, a82c026e, 46a3abf7, gpt4_2f8be40d, d23cf73b, gpt4_5501fe77, 2ce6a0f2, 129d1232, d851d5ba, 1a8a66a6, 8a2466db, 06878be2, 195a1a1b, afdc33df, caf03d32, 54026fce, 6b7dfb22, 1a1907b4, 505af2f5, 75f70248, fca70973, b6025781, b0479f84, 1d4e3b97, 07b6f563, 1c0ddc50, 0a34ad58, gpt4_45189cb4, gpt4_e061b84f, gpt4_d6585ce8, 6e984301, gpt4_21adecb5, gpt4_b0863698, gpt4_d6585ce9, 9a707b82, 6e984302, gpt4_b5700ca0, gpt4_76048e76, 08f4fc43, gpt4_385a5000, bbf86515, 982b5123, b9cfe692, gpt4_4edbafa2, e4e14d04, gpt4_9a159967, cc6d1ec1, gpt4_2f56ae70, gpt4_0a05b494, 6aeb4375, 830ce83f, 852ce960, 945e3d21, d7c942c3, 71315a70, 89941a93, ce6d2d27, 9ea5eabc, 07741c44, a1eacc2a, 184da446, 031748ae, 4d6b87c8, 08e075c7, f9e8c073, 41698283, 2698e78f, b6019101, 45dc21b6, 5a4f22c0, 6071bd76, e493bb7c, 618f13b2, 72e3ee87, c4ea545c, 01493427, 6a27ffc2, 2133c1b5, 18bc8abd, db467c8c, e61a7584, 1cea1afa, ed4ddc30, 8fb83627, b01defab, 22d2cb42, 0e4e4c46, 4b24c848, 7e974930, 603deb26, 5831f84d, eace081b, affe2881, e66b632c, 0ddfec37, cc5ded98, dfde3500, cf22b7bf, c7dc5443, 06db6396, 3ba21379, 9bbe84a2, 10e09553, dad224aa, ba61f0b9, 42ec0761, 5c40ec5b, c6853660, 26bdc477, 89941a94, 07741c45, 7161e7e2, c4f10528, 89527b6b, e9327a54, 4c36ccef, 6ae235be, 7e00a6cb, 1903aded, ceb54acb, f523d9fe, 0e5e2d1a, fea54f57, cc539528, dc439ea3, 18dcd5a5, 488d3006, 58470ed2, 8cf51dda, 1d4da289, 8464fc84, 71a3fd6b, 2bf43736, 70b3e69b, 8752c811, 3249768e, 1b9b7252, 1568498a, 6222b6eb, e8a79c70, d596882b, e3fc4d6e, 51b23612, 3e321797, e982271f, 352ab8bd, fca762bc, 7a8d0b71, a40e080f, 8b9d4367, 5809eb10, 41275add, 4388e9dd, 4baee567, 561fabcd, b759caee, ac031881, 28bcfaac, 16c90bf4, c8f1aeed, eaca4986, c7cf7dfd, e48988bc, 1de5cff2, 65240037

## Abstention reasons

> Scope: **every route that can decline** (session, temporal, abstention, knowledge-update, assistant, preference, flat). One exception, stated rather than implied: `threshold` is reachable only on the abstention route, because that is the only caller of the retrieval gate — on every other route the key is `0` because no gate exists there, not because the gate stayed open. This table used to count the abstention route alone, which is how §12.5's `llm = 120` came to be read as the model declining 120 times when it was 30 `ABS` questions passing across 4 runs.

| Reason | Count | Share | Decided by |
|---|---|---|---|
| `empty` | 0 | 0.00% | machine (no evidence admitted) |
| `threshold` | 0 | 0.00% | machine (retrieval gate closed; abstention route only) |
| `llm` | 75 | 15.00% | model (declined) |
| `answered` | 425 | 85.00% | model (answered) |

- Total: **500** questions that reached a decision
- Machine-derived share (`empty` + `threshold`): **0.00%**
- Model-side share (`llm`): **15.00%**

## Abstention recovery

| Consultations | Answered | Converted |
|---|---|---|
| 10 | 1 | 10.0% |

Attempted counts declines that contradicted their own Step 1 list; a decline with an empty list
is the state the contract licenses and is not consulted. This pass fires only on a decline, so
no answer that was already correct can move.
