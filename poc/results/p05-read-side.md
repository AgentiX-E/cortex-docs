# POC-5: the write/read boundary, end to end

Corpus: the same 60 hand-labelled LongMemEval-S utterances as POC-4 (12 private / 8 shared / 40 defer).
The rules decide the first pass; the card queue is simulated by the policy column.

## The four user policies

| policy | leak | leak upper | reach shared | reach private | noise | shared rows |
| --- | --- | --- | --- | --- | --- | --- |
| rules-only | 0 / 12 | 24.2% | 4 / 8 | 12 / 12 | 0 / 40 | 4 |
| oracle | 0 / 12 | 24.2% | 8 / 8 | 12 / 12 | 0 / 40 | 8 |
| defer-shared | 0 / 12 | 24.2% | 7 / 8 | 12 / 12 | 38 / 40 | 45 |
| no-triage | 12 / 12 | 100.0% | 8 / 8 | 12 / 12 | 40 / 40 | 60 |

**Reading it.** `rules-only` is the shipped default: the boundary holds at zero leakage, but a
shared task reaches only half of what is legitimately shareable, because four gold-shared rows
were classified private and became cards. `oracle` is the upper bound a perfect queue would
reach: 8/8 with no leakage, which is what makes the queue worth building rather than a tax.
`defer-shared` is the A4 ablation -- one line of code, `defer` landing shared instead of private:
it buys three more reachable facts and publishes three gold-private ones, and no later audit can
take those back. `no-triage` is A1, the thing the rule layer replaced: every gold-private fact
in the sample reaches the shared store.

## The guard, priced by a fault

| state | result | leak |
| --- | --- | --- |
| guard on | ScopeViolation | 0 / 1 |
| guard off | no error | 1 / 1 |

The guard is redundant while the writer is correct, so a clean run proves nothing about it.
Injecting one private row into the shared store -- bypassing the router, as a bug would -- is
the only way to show it is load-bearing: it refuses to launch a prompt rather than filtering
the row out, because filtering would keep the boundary looking intact while the writer stayed
broken.

## Assertions

| check | result | detail |
| --- | --- | --- |
| a shared window carries no gold-private row (rules-only) | PASS | leak 0/12, Wilson upper 24.2% |
| a private window carries every row, exactly once | PASS | 60 rows for 60 facts |
| every assembled row says where it came from | PASS | origin label survives the two-store merge |
| the guard fires on a private row injected into the shared store | PASS | ScopeViolation raised, no prompt launched |
| without the guard the same injection reaches the window | PASS | guard off: leak 1/1 -- this is what the guard buys |
| the A4 ablation is silent here, because no private row is deferred any more | PASS | deferred-private 0; A4 leak 0/12 -- the ablation moved to the 47,927-row census, where it publishes 40,822 (85.18%) |
| no-triage leaks everything, so the rule layer is load-bearing | PASS | leak 12/12 (A1 ablation) |
| a perfect confirmation buys completeness the rules cannot | PASS | reach 4/8 -> 8/8 |
| the perfect-confirmation path still leaks nothing | PASS | confirming the right cards is sound at both ends |
| assembly is deterministic across two passes | PASS | 60 ids identical |
| an unknown task scope is refused | PASS | "both" is not a task scope |

