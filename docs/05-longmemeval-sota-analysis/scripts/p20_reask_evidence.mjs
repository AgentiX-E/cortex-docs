/**
 * Is the re-ask declining because it skipped, or because the evidence was never
 * retrieved?
 *
 * First attempt at this read `answer_sessions_content`, which turned out to be
 * an empty string on all 379 single-session rows and a bare list of session IDs
 * (max length 5) on the 121 MR rows. The real prompt payload is
 * `decision.retrieved`. Re-running against the correct field is the whole point
 * of this script: the first conclusion was drawn from a field that carries no
 * text, which produced a spuriously clean 21/22 "absent".
 *
 * Membership is conservative — exact substring, then numeric equality, then a
 * >=12-char verbatim run — so "present" is trustworthy when it appears.
 */

import { readFileSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const DIRS = {
  base: '/workspace/analysis/ab_retry/run_34791592602',
  fix: '/workspace/analysis/ab_retry/run_34915402976',
};

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\s+/g, ' ')
    .trim();

function evidencePresent(blob, gold) {
  const b = norm(blob);
  const g = norm(gold);
  if (g === '') return null;
  if (b.includes(g)) return 'exact';
  const gn = Number(g.replace(/[^0-9.\-]/g, ''));
  if (!Number.isNaN(gn) && g.length <= 6) {
    const nums = b.match(/-?\d+(?:\.\d+)?/g) ?? [];
    if (nums.some((n) => Number(n) === gn)) return 'numeric';
  }
  for (let len = Math.min(40, g.length); len >= 12; len--) {
    if (b.includes(g.slice(0, len))) return `prefix${len}`;
  }
  return null;
}

function index(dir) {
  const fromMr = load(`${dir}/MR_diagnostics.json`).map((d) => ['MR', d]);
  const fromSs = load(`${dir}/Single-session_diagnostics.json`).map((d) => [d.capability, d]);
  const m = new Map();
  for (const [capability, d] of [...fromMr, ...fromSs]) m.set(d.question_id, { capability, d });
  return m;
}

const F = index(DIRS.fix);
const B = index(DIRS.base);

const fired = [...F.values()].filter((e) => (e.d.decision ?? {}).retryFired === true);

console.log('=== the 22 re-ask questions: was the gold value in the retrieved payload? ===');
console.log('| id | cap | after re-ask | payload chars | gold-in-payload |');
const rows = [];
for (const { capability, d } of fired) {
  const payload = d.decision?.retrieved ?? '';
  const hit = evidencePresent(payload, d.ground_truth);
  rows.push({ id: d.question_id, cap: capability, abstained: !!d.decision?.abstained, hit });
  console.log(
    `| ${d.question_id.padEnd(14)} | ${capability.padEnd(3)} | ${d.decision?.abstained ? 'declines' : 'answers '} | ${String(payload.length).padStart(6)} | ${hit ?? 'ABSENT'} |`
  );
}

const still = rows.filter((r) => r.abstained);
console.log('');
console.log(`retry fired          : ${rows.length}`);
console.log(`still declined       : ${still.length}`);
console.log(`  ...had evidence    : ${still.filter((r) => r.hit !== null).length}`);
console.log(`  ...no evidence     : ${still.filter((r) => r.hit === null).length}`);

// Sanity: what does the payload look like on the questions the retry DID convert
// historically? None converted here, so instead measure the population that
// answered successfully without any retry — that is the contrast class.
console.log('');
console.log('=== contrast: questions answered correctly with NO retry, same capabilities ===');
const okNoRetry = [...F.values()].filter(
  (e) =>
    e.d.correct &&
    !(e.d.decision ?? {}).retryFired &&
    ['TR', 'IE'].includes(e.capability)
);
let cPresent = 0;
for (const { d } of okNoRetry) {
  if (evidencePresent(d.decision?.retrieved ?? '', d.ground_truth) !== null) cPresent++;
}
console.log(`TR/IE answered correctly, no retry: ${okNoRetry.length}, gold in payload: ${cPresent} (${((cPresent / okNoRetry.length) * 100).toFixed(1)}%)`);

// And the same contrast restricted to abstentions that the retry did NOT fire on,
// to check the retry's abstention-detection scope is right.
const abstNoFire = [...F.values()].filter(
  (e) => (e.d.decision ?? {}).abstained && !(e.d.decision ?? {}).retryFired
);
let aPresent = 0;
for (const { d } of abstNoFire) {
  if (evidencePresent(d.decision?.retrieved ?? '', d.ground_truth) !== null) aPresent++;
}
console.log(`abstained, retry did NOT fire: ${abstNoFire.length}, gold in payload: ${aPresent} (${((aPresent / abstNoFire.length) * 100).toFixed(1)}%)`);
