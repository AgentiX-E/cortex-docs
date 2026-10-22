/**
 * Two candidate mechanisms for the 37 TR failures, quantified separately so the
 * next iteration can be aimed at a number rather than at a vibe.
 *
 *   (A) RELATIVE-TIME ANCHOR. The question says "last Saturday", "10 days ago",
 *       "four weeks ago" and the answer session is identified by resolving that
 *       phrase against question_date. Nothing in the retrieved text says "last
 *       Saturday", so lexical retrieval cannot work; the engine must first turn
 *       the phrase into an absolute date.
 *
 *   (B) ORDERING / SEQUENCE. The question asks for the order of N >= 3 items.
 *       The MR path answers "how many" with an explicit enumerate-then-compute
 *       ledger plus a membership critique; the TR path has no such contract.
 *
 * For each: how many TR questions, what accuracy, and how much of the 37.
 */

import { readFileSync } from 'node:fs';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const all = [...load(`${BASE}/MR_diagnostics.json`), ...load(`${BASE}/Single-session_diagnostics.json`)];
const tr = all.filter((d) => d.capability === 'TR');

const RELATIVE =
  /\b(last|past|previous|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month|year|weekend)\b|\b(\d+|a\s+few|a\s+couple|several|two|three|four|five|six)\s+(day|days|week|weeks|month|months|year|years)\s+ago\b|\byesterday\b|\ba\s+couple\s+of\s+days\b/i;

const ORDER =
  /\border\s+of\s+(the\s+)?(\w+\s+)?(three|four|five|six|seven|eight|multiple|several|\d+|[a-z]+s)\b/i;

const rel = tr.filter((d) => RELATIVE.test(d.question ?? ''));
const ord = tr.filter((d) => ORDER.test(d.question ?? ''));
const both = tr.filter((d) => RELATIVE.test(d.question ?? '') && ORDER.test(d.question ?? ''));
const other = tr.filter((d) => !RELATIVE.test(d.question ?? '') && !ORDER.test(d.question ?? ''));

const stat = (name, g) => {
  const ok = g.filter((d) => d.correct).length;
  const ab = g.filter((d) => (d.decision ?? {}).abstained).length;
  console.log(
    `  ${name.padEnd(22)} n=${String(g.length).padStart(3)}  acc=${((ok / g.length) * 100).toFixed(2)}%  wrong=${String(g.length - ok).padStart(2)}  abstained=${ab}`
  );
  return g.filter((d) => !d.correct);
};

console.log(`TR total ${tr.length}, accuracy ${((tr.filter((d) => d.correct).length / tr.length) * 100).toFixed(2)}%`);
console.log('');
const wRel = stat('(A) relative-time', rel);
const wOrd = stat('(B) ordering', ord);
stat('(A and B)', both);
const wOther = stat('neither', other);

console.log(`\nshare of the 37 TR failures:`);
const uniq = new Set([...wRel, ...wOrd].map((d) => d.question_id));
console.log(`  (A) relative-time : ${wRel.length}`);
console.log(`  (B) ordering      : ${wOrd.length}`);
console.log(`  union             : ${uniq.size}  (${((uniq.size / 37) * 100).toFixed(0)}% of all TR failures)`);
console.log(`  neither           : ${wOther.length}`);

console.log('\n--- (A) relative-time failures ---');
for (const d of wRel) {
  console.log(
    `  ${d.question_id} abst=${(d.decision ?? {}).abstained ? 'Y' : 'n'} | ${String(d.question).slice(0, 66)} | gold="${String(d.ground_truth).slice(0, 26)}"`
  );
}

console.log('\n--- (B) ordering failures ---');
for (const d of wOrd) {
  console.log(
    `  ${d.question_id} abst=${(d.decision ?? {}).abstained ? 'Y' : 'n'} | ${String(d.question).slice(0, 66)} | gold="${String(d.ground_truth).slice(0, 26)}"`
  );
}

console.log('\n--- neither: the residual ---');
for (const d of wOther) {
  console.log(
    `  ${d.question_id} abst=${(d.decision ?? {}).abstained ? 'Y' : 'n'} | ${String(d.question).slice(0, 60)} | gold="${String(d.ground_truth).slice(0, 24)}" got="${String((d.decision ?? {}).answer).slice(0, 24)}"`
  );
}
