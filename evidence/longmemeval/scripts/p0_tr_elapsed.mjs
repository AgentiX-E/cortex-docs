/**
 * Mechanism (C): TR questions that ask for an elapsed span between two events
 * ("how many days between X and Y", "how long had I been ... when ...").
 * These are pure date arithmetic over two retrieved dates, which is the one TR
 * sub-task that does not need an LLM at all.
 */

import { readFileSync } from 'node:fs';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const all = [...load(`${BASE}/MR_diagnostics.json`), ...load(`${BASE}/Single-session_diagnostics.json`)];
const tr = all.filter((d) => d.capability === 'TR');

const ELAPSED =
  /\bhow (?:many|much) (?:days|weeks|months|years|time)\b[\s\S]{0,80}\b(?:between|since|before|passed|elapsed)\b|\bhow long\b/i;

const g = tr.filter((d) => ELAPSED.test(d.question ?? ''));
const rest = tr.filter((d) => !ELAPSED.test(d.question ?? ''));
const ok = g.filter((d) => d.correct).length;
const ab = g.filter((d) => (d.decision ?? {}).abstained).length;
const rok = rest.filter((d) => d.correct).length;

console.log(
  `(C) elapsed-time TR: n=${g.length}  acc=${((ok / g.length) * 100).toFixed(2)}%  wrong=${g.length - ok}  abstained=${ab}`
);
console.log(`    rest          : n=${rest.length}  acc=${((rok / rest.length) * 100).toFixed(2)}%`);

console.log('\n(C) failures:');
for (const d of g.filter((x) => !x.correct)) {
  console.log(
    `  ${d.question_id} abst=${(d.decision ?? {}).abstained ? 'Y' : 'n'} | ${String(d.question).slice(0, 56)} | gold="${String(d.ground_truth).slice(0, 22)}" got="${String((d.decision ?? {}).answer).slice(0, 18)}"`
  );
}
