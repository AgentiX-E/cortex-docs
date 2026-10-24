# knowledge-model

Two readings over the **same twenty pairs** the reviewer judged in round 2
(`evidence/a3-review/review-remote.html`, `triage-proposer/v4`, remote `deepseek-chat`). Neither
calls a model, so both are reproducible without an API key.

| file | produced by | what it says |
|---|---|---|
| `census-remote-v4.txt` | `python3 tools/measure-atom-fidelity.py <review page>` | how much of a sentence's relation survives the split into atoms |
| `probe-remote-v4.txt` | `node tools/knowledge-probe.mjs --html <review page>` | what the assembly gate says about the same splits, and what a repaired unit costs in tokens |

The two are independent implementations of the same marker table — Python for the census, TypeScript
for the gate — which is why their agreement on the five lost relations is worth something: the table
is duplicated on purpose so that a change to one produces a diff in the other's reading rather than a
silent agreement.

Neither file is a verdict on the design. The gate's acceptance of 15 of 20 says the gate is aimed at
the right defect; it does not say the surviving 15 are what a reader wants, and it says nothing at all
about whether any of this helps on LongMemEval-S. That is the pre-registered A7 in
`../../docs/02-technical-design.md` §5.5.6 and in the cortex repository's
`docs/DESIGN-KNOWLEDGE-MODEL.md`, and it has not been run.
