/**
 * Test one hypothesis about the 37 TR failures: that the ordering/sequence
 * questions are the concentrated failure, and that they fail because the TR path
 * has no equivalent of the MR aggregation ledger.
 *
 * MR answers "how many / how much in total" through an explicit two-step
 * contract: `Step 1` enumerate every matching item, `Step 2` compute, then a
 * critique pass that audits the item list's membership. TR has no such contract.
 * If TR ordering questions are answered with ONE event instead of the whole
 * ordered sequence, that is the same defect the ledger was built to fix, and it
 * is measurable from the diagnostics alone: compare the gold's item count with
 * the prediction's item count.
 */

import { readFileSync } from 'node:fs';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const all = [...load(`${BASE}/MR_diagnostics.json`), ...load(`${BASE}/Single-session_diagnostics.json`)];
const tr = all.filter((d) => (d.capability ?? '') === 'TR' || d.capability === undefined ? false : false);
const trReal = all.filter((d) => d.capability === 'TR');

const ORDER_Q = /\b(order|first|earliest|latest|last|before|after|sequence|chronolog)/i;
const orderQs = trReal.filter((d) => ORDER_Q.test(d.question ?? ''));
const nonOrder = trReal.filter((d) => !ORDER_Q.test(d.question ?? ''));

const acc = (g) => ((g.filter((d) => d.correct).length / g.length) * 100).toFixed(2);

console.log(`TR questions: ${trReal.length}`);
console.log(`  ordering-flavoured : ${orderQs.length}   accuracy ${acc(orderQs)}%`);
console.log(`  everything else    : ${nonOrder.length}   accuracy ${acc(nonOrder)}%`);

// How many items does the gold list versus the prediction?
const items = (s) => {
  const t = String(s ?? '');
  const commas = (t.match(/,|\bthen\b|\band finally\b|\bfinally\b/gi) ?? []).length;
  return commas + 1;
};

console.log('\n--- TR ordering-flavoured FAILURES: gold items vs predicted items ---');
let underCount = 0;
for (const d of orderQs.filter((x) => !x.correct)) {
  const g = items(d.ground_truth);
  const p = items((d.decision ?? {}).answer);
  if (p < g) underCount++;
  console.log(
    `  ${d.question_id}  gold~${g} pred~${p}  abst=${(d.decision ?? {}).abstained ? 'Y' : 'n'}  | ${String(d.question).slice(0, 62)}`
  );
}
console.log(
  `\nunder-enumerated (predicted fewer items than the gold): ${underCount} of ${orderQs.filter((x) => !x.correct).length}`
);

// Same question, applied to the whole TR set for a baseline rate.
let trUnder = 0;
const trWrong = trReal.filter((d) => !d.correct);
for (const d of trWrong) {
  if (items((d.decision ?? {}).answer) < items(d.ground_truth)) trUnder++;
}
console.log(`TR-wide under-enumeration among failures: ${trUnder} of ${trWrong.length}`);

console.log('\n--- abstentions among TR failures, with whether evidence was present ---');
for (const d of trWrong.filter((x) => (x.decision ?? {}).abstained)) {
  console.log(`  ${d.question_id}  ${String(d.question).slice(0, 70)}`);
}
