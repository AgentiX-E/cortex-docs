/**
 * Characterise the failures in run 34791592602 by capability, to decide where
 * the next iteration should go.
 *
 * Headline: IE 96.00% (150), MR 90.08% (121), KU 79.17% (72), TR 70.87% (127),
 * ABS 86.67% (30) -- overall 85.20%, so 74 questions are wrong. TR alone owns 37
 * of them, half the total. This script asks whether those 37 share a mechanism,
 * because "TR is weak" is not an actionable finding and "TR fails on X" is.
 */

import { readFileSync } from 'node:fs';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const LME = '/tmp/lme-data/lme.json';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const mr = load(`${BASE}/MR_diagnostics.json`);
const ss = load(`${BASE}/Single-session_diagnostics.json`);
const all = [...mr, ...ss];

const lme = load(LME);
const meta = new Map(lme.map((x) => [x.question_id, x]));

const cap = (d) => {
  const t = d.question_type ?? meta.get(d.question_id)?.question_type ?? '?';
  if (String(d.question_id).endsWith('_abs')) return 'ABS';
  return (
    { 'single-session-user': 'IE', 'single-session-assistant': 'IE', 'single-session-preference': 'IE', 'multi-session': 'MR', 'temporal-reasoning': 'TR', 'knowledge-update': 'KU' }[t] ?? t
  );
};

const groups = {};
for (const d of all) {
  const c = cap(d);
  (groups[c] ??= []).push(d);
}

console.log(`total records: ${all.length}`);
console.log('\n| cap | n | correct | acc | wrong |');
for (const c of ['IE', 'MR', 'KU', 'TR', 'ABS']) {
  const g = groups[c] ?? [];
  const ok = g.filter((d) => d.correct).length;
  console.log(
    `| ${c.padEnd(3)} | ${String(g.length).padStart(3)} | ${String(ok).padStart(3)} | ${((ok / g.length) * 100).toFixed(2)}% | ${g.length - ok} |`
  );
}

// ------------------------------------------------------------------ TR failures

const tr = groups['TR'] ?? [];
const trWrong = tr.filter((d) => !d.correct);
console.log(`\n=== TR failures: ${trWrong.length} of ${tr.length} ===`);

const reasonCount = {};
let abstained = 0;
for (const d of trWrong) {
  const r = (d.decision ?? {}).reason ?? '(none)';
  reasonCount[r] = (reasonCount[r] ?? 0) + 1;
  if ((d.decision ?? {}).abstained) abstained++;
}
console.log(`abstained: ${abstained} of ${trWrong.length}`);
console.log('reasons:');
for (const [r, n] of Object.entries(reasonCount).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${String(n).padStart(3)}  ${r}`);
}

// What does a TR question actually ask for? Bucket by the answer's shape.
const shape = (s) => {
  const t = String(s).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(t) || /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(t))
    return 'date';
  if (/^\d+(\.\d+)?\s*(day|days|week|weeks|month|months|year|years|hour|hours)?$/i.test(t))
    return 'count/duration';
  if (/\d/.test(t)) return 'other-numeric';
  return 'text';
};

const goldShape = {};
const wrongShape = {};
for (const d of tr) {
  const s = shape(d.ground_truth ?? '');
  goldShape[s] = (goldShape[s] ?? 0) + 1;
  if (!d.correct) wrongShape[s] = (wrongShape[s] ?? 0) + 1;
}
console.log('\nTR gold shape -> total / wrong / accuracy');
for (const s of Object.keys(goldShape).sort()) {
  const t = goldShape[s];
  const w = wrongShape[s] ?? 0;
  console.log(`  ${s.padEnd(16)} ${String(t).padStart(3)} / ${String(w).padStart(3)}  ${(((t - w) / t) * 100).toFixed(1)}%`);
}

console.log('\n--- the 37 TR failures ---');
for (const d of trWrong) {
  const dec = d.decision ?? {};
  console.log(
    `${d.question_id}  abst=${dec.abstained ? 'Y' : 'n'}  gold="${String(d.ground_truth).slice(0, 34)}"  got="${String(dec.answer ?? '').slice(0, 34)}"  reason=${String(dec.reason ?? '').slice(0, 44)}`
  );
}
