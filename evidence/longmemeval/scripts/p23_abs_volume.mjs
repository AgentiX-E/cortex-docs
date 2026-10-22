#!/usr/bin/env node
/**
 * ABS prompt-volume test, restricted to claims the artifacts can actually
 * support.
 *
 * The ABS rows in the diagnostics carry NO evidence field: they have no
 * `answer_sessions_content`, no `answer_session_ids` and no `haystack_dates`
 * (those exist only on the MR rows). So any statement of the form "the evidence
 * session of an ABS question was entirely admitted" is not derivable from these
 * artifacts, and the P23 verdict must not contain one.
 *
 * What IS derivable: the prompt payload, its length, and whether the model
 * abstained. This script uses only those, and reports:
 *
 *   1. the before/after prompt length per ABS question
 *   2. whether the lost questions grew more than the stable ones (dilution)
 *   3. the correlation between prompt growth and the flip direction
 *   4. how much of the ABS outcome is explained by abstention alone
 *
 * No network.
 */

import { readFileSync } from 'node:fs';

const AFTER = process.argv[2];
const BEFORE = process.argv[3];

const load = (dir) =>
  JSON.parse(readFileSync(`${dir}/Single-session_diagnostics.json`, 'utf8'));
const byId = (rows) => new Map(rows.map((r) => [r.question_id, r]));
const B = byId(load(BEFORE).filter((r) => r.capability === 'ABS'));
const A = byId(load(AFTER).filter((r) => r.capability === 'ABS'));

const promptLen = (r) => String(r?.decision?.retrieved ?? '').length;
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
const sd = (xs) => {
  if (xs.length < 2) return NaN;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1));
};
const pctF = (x) => (100 * x).toFixed(1) + '%';

const rows = [];
for (const id of [...B.keys()].sort()) {
  const b = B.get(id);
  const a = A.get(id);
  if (!a) continue;
  rows.push({
    id,
    okB: b.correct === true,
    okA: a.correct === true,
    lenB: promptLen(b),
    lenA: promptLen(a),
    absB: b.decision?.abstained === true,
    absA: a.decision?.abstained === true,
    top1B: b.decision?.top1Score,
    top1A: a.decision?.top1Score,
  });
}

console.log(`ABS n=${rows.length}\n`);

// ---- 1. abstention behaviour --------------------------------------------
const absRateB = rows.filter((r) => r.absB).length / rows.length;
const absRateA = rows.filter((r) => r.absA).length / rows.length;
console.log('=== abstention ===');
console.log(`  abstained  before ${rows.filter((r) => r.absB).length}/${rows.length} (${pctF(absRateB)})`);
console.log(`  abstained  after  ${rows.filter((r) => r.absA).length}/${rows.length} (${pctF(absRateA)})`);

// On ABS the correct answer IS the abstention, so agreement between the
// abstention flag and correctness measures how mechanical this block is.
const agree = rows.filter((r) => r.absA === r.okA).length;
console.log(`  abstention flag == correctness (after): ${agree}/${rows.length} (${pctF(agree / rows.length)})`);

// ---- 2. prompt volume ----------------------------------------------------
console.log('\n=== prompt volume (chars) ===');
console.log(`  mean before ${mean(rows.map((r) => r.lenB)).toFixed(0)}  sd ${sd(rows.map((r) => r.lenB)).toFixed(0)}`);
console.log(`  mean after  ${mean(rows.map((r) => r.lenA)).toFixed(0)}  sd ${sd(rows.map((r) => r.lenA)).toFixed(0)}`);
console.log(`  mean growth ${mean(rows.map((r) => r.lenA - r.lenB)).toFixed(0)} chars`);

const flips = rows.filter((r) => r.okB !== r.okA);
const gained = flips.filter((r) => r.okA);
const lost = flips.filter((r) => !r.okA);
const stable = rows.filter((r) => r.okB === r.okA);

console.log('\n=== prompt growth by outcome (the dilution prediction) ===');
for (const [name, g] of [
  ['lost', lost],
  ['gained', gained],
  ['stable', stable],
]) {
  const d = g.map((r) => r.lenA - r.lenB);
  console.log(
    `  ${name.padEnd(7)} n=${String(g.length).padStart(3)}  mean dLen ${
      d.length ? (mean(d) >= 0 ? '+' : '') + mean(d).toFixed(0) : 'n/a'
    }  sd ${d.length ? sd(d).toFixed(0) : 'n/a'}`,
  );
}

// ---- 3. does growth predict the flip? ------------------------------------
console.log('\n=== growth vs outcome ===');
const dAll = rows.map((r) => r.lenA - r.lenB);
const yAll = rows.map((r) => (r.okA ? 1 : 0));
const mD = mean(dAll);
const mY = mean(yAll);
const cov = mean(dAll.map((d, i) => (d - mD) * (yAll[i] - mY)));
const r_ = cov / (sd(dAll) * sd(yAll));
console.log(`  Pearson r(prompt growth, correct after) = ${r_.toFixed(4)} (n=${rows.length})`);

const grewABove = rows.filter((r) => r.lenA - r.lenB > mean(rows.map((x) => x.lenA - x.lenB)));
const grewBelow = rows.filter((r) => r.lenA - r.lenB <= mean(rows.map((x) => x.lenA - x.lenB)));
console.log(
  `  above-median growth: n=${grewABove.length} acc=${pctF(
    grewABove.filter((r) => r.okA).length / grewABove.length,
  )}`,
);
console.log(
  `  below-median growth: n=${grewBelow.length} acc=${pctF(
    grewBelow.filter((r) => r.okA).length / grewBelow.length,
  )}`,
);

// ---- 4. the two questions that grew *less* ------------------------------
console.log('\n=== questions whose prompt SHRANK ===');
for (const r of rows.filter((x) => x.lenA - x.lenB < 0)) {
  console.log(`  ${r.id}  ${r.lenB} -> ${r.lenA} (${r.lenA - r.lenB})  ${r.okB ? 'Y' : 'n'}->${r.okA ? 'Y' : 'n'}`);
}

// ---- 5. top1 score shift -------------------------------------------------
console.log('\n=== top1Score ===');
const t = rows.filter((r) => typeof r.top1B === 'number' && typeof r.top1A === 'number');
console.log(`  mean before ${mean(t.map((r) => r.top1B)).toFixed(4)}  after ${mean(t.map((r) => r.top1A)).toFixed(4)}`);
const down = t.filter((r) => r.top1A < r.top1B - 1e-9);
const up = t.filter((r) => r.top1A > r.top1B + 1e-9);
console.log(`  top1 rose ${up.length}, fell ${down.length}, flat ${t.length - up.length - down.length}`);
