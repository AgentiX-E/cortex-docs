#!/usr/bin/env node
/**
 * Characterise the ABS block across the before/after pair of the P23
 * session-coherent admission change.
 *
 * The P23 verdict attributed the ABS regression (86.67% -> 80.00%) to dilution:
 * all four flips had their evidence session entirely admitted, so the answer
 * changed because the prompt changed, not because evidence was missing. That is
 * a hypothesis about a mechanism, and this script tests it rather than restating
 * it. It reports, per ABS question:
 *
 *   - correctness before / after
 *   - the fraction of the answer session that reached the prompt (before/after)
 *   - the prompt length in characters (before/after)
 *   - how many turns were admitted, and how many of them are the answering ones
 *
 * It then aggregates the dilution claim into the specific prediction it makes:
 * if completion-added turns dilute, the questions that gained the MOST
 * non-evidence turns should lose accuracy, and the lost questions should show a
 * larger prompt growth than the retained ones.
 *
 * No network. Reads only the diagnostics artifacts.
 */

import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const AFTER = process.argv[2];
const BEFORE = process.argv[3];
if (!AFTER || !BEFORE) {
  console.error('usage: node p23_abs_dilution.mjs <afterDir> <beforeDir>');
  process.exit(2);
}

const load = (dir) =>
  JSON.parse(readFileSync(`${dir}/Single-session_diagnostics.json`, 'utf8'));

const before = load(BEFORE);
const after = load(AFTER);
const byId = (rows) => new Map(rows.map((r) => [r.question_id, r]));
const B = byId(before);
const A = byId(after);

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();

/** Character 5-gram shingles, the same distance the other P2x scripts use. */
const shingles = (s) => {
  const t = norm(s);
  const out = new Set();
  for (let i = 0; i + 5 <= t.length; i++) out.add(createHash('sha1').update(t.slice(i, i + 5)).digest('hex'));
  return out;
};

const overlap = (a, b) => {
  if (a.size === 0) return 0;
  let hit = 0;
  for (const s of a) if (b.has(s)) hit++;
  return hit / a.size;
};

/** The prompt payload the retrieval actually delivered, as one string. */
const promptText = (row) => {
  const r = row?.decision?.retrieved;
  if (Array.isArray(r)) return r.join('\n\n');
  if (typeof r === 'string') return r;
  return '';
};

/**
 * Coverage of the answer session: what fraction of the answer session's
 * characters are present in the prompt. `answer_sessions_content` is the list of
 * ground-truth evidence sessions, so its concatenation is the target.
 */
const coverage = (row) => {
  const prompt = shingles(promptText(row));
  const target = shingles(joined(row));
  return { cov: overlap(target, prompt), promptLen: promptText(row).length };
};

/**
 * The ground-truth evidence text. Diagnostics store it either as one string per
 * session or as one string overall; handle both.
 */
function joined(row) {
  const c = row.answer_sessions_content;
  if (Array.isArray(c)) return c.join('\n\n');
  return String(c ?? '');
}

const isAbs = (r) =>
  String(r.capability ?? '').toLowerCase().includes('abstention') ||
  String(r.capability ?? '').toLowerCase() === 'abs';

const absRows = (rows) => rows.filter(isAbs);

const bAbs = absRows(before);
const aAbs = absRows(after);

console.log(`ABS rows: before=${bAbs.length} after=${aAbs.length}\n`);

const ids = [...new Set([...bAbs, ...aAbs].map((r) => r.question_id))].sort();
const rows = [];
for (const id of ids) {
  const b = B.get(id);
  const a = A.get(id);
  if (!b || !a) {
    console.log(`  !! ${id} missing on one side (before=${!!b} after=${!!a})`);
    continue;
  }
  const cb = coverage(b);
  const ca = coverage(a);
  rows.push({
    id,
    cap: b.capability,
    okBefore: b.correct === true,
    okAfter: a.correct === true,
    covBefore: cb.cov,
    covAfter: ca.cov,
    lenBefore: cb.promptLen,
    lenAfter: ca.promptLen,
    q: String(b.question ?? '').slice(0, 70),
  });
}

const pct = (x) => (100 * x).toFixed(1).padStart(5);
const signed = (x) => (x >= 0 ? '+' : '') + x.toFixed(1);

console.log('question_id            cov_before cov_after  len_before  len_after  dLen    ok');
for (const r of rows.sort((x, y) => Number(x.okBefore) - Number(y.okBefore) || x.id.localeCompare(y.id))) {
  console.log(
    `${r.id.padEnd(22)} ${pct(r.covBefore)}%   ${pct(r.covAfter)}%   ${String(
      r.lenBefore,
    ).padStart(9)}  ${String(r.lenAfter).padStart(9)}  ${signed(
      r.lenAfter - r.lenBefore,
    ).padStart(7)}   ${r.okBefore ? 'Y' : 'n'}->${r.okAfter ? 'Y' : 'n'}`,
  );
}

// ---- the flips, and what moved around them -------------------------------
const flips = rows.filter((r) => r.okBefore !== r.okAfter);
const gained = flips.filter((r) => r.okAfter);
const lost = flips.filter((r) => !r.okAfter);

console.log(`\n=== flips (n=${flips.length}) ===`);
for (const r of flips) {
  const d = r.lenAfter - r.lenBefore;
  console.log(
    `${r.okAfter ? 'GAIN' : 'LOST'}  ${r.id.padEnd(22)} cov ${pct(r.covBefore)}% -> ${pct(
      r.covAfter,
    )}%   prompt ${signed(d)} chars (${r.lenBefore} -> ${r.lenAfter})`,
  );
  console.log(`      q: ${r.q}`);
}

// ---- the dilution prediction ---------------------------------------------
// If added non-evidence turns dilute, accuracy loss should track prompt growth.
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
const dLenLost = mean(lost.map((r) => r.lenAfter - r.lenBefore));
const dLenGain = mean(gained.map((r) => r.lenAfter - r.lenBefore));
const dLenStay = mean(
  rows.filter((r) => r.okBefore === r.okAfter).map((r) => r.lenAfter - r.lenBefore),
);

console.log('\n=== dilution prediction: prompt growth by outcome ===');
console.log(`  lost   n=${String(lost.length).padStart(3)}  mean dLen = ${signed(dLenLost)} chars`);
console.log(`  gained n=${String(gained.length).padStart(3)}  mean dLen = ${signed(dLenGain)} chars`);
console.log(`  stable n=${String(rows.length - flips.length).padStart(3)}  mean dLen = ${signed(dLenStay)} chars`);

// ---- coverage of the evidence session ------------------------------------
console.log('\n=== coverage of the evidence session ===');
const band = (r) => {
  const c = r.covAfter;
  if (c >= 0.999) return '100%';
  if (c >= 0.5) return '50-99%';
  if (c >= 0.01) return '1-49%';
  return '0%';
};
for (const b of ['0%', '1-49%', '50-99%', '100%']) {
  const g = rows.filter((r) => band(r) === b);
  if (!g.length) continue;
  const ok = g.filter((r) => r.okAfter).length;
  console.log(`  ${b.padEnd(7)} after: n=${String(g.length).padStart(3)}  acc=${pct(ok / g.length)}%`);
}

const fully = rows.filter((r) => r.covAfter >= 0.999);
console.log(
  `\n  fully-admitted after: n=${fully.length}  correct=${fully.filter((r) => r.okAfter).length}` +
    `  (before: fully-admitted n=${rows.filter((r) => r.covBefore >= 0.999).length})`,
);

console.log('\n=== summary ===');
const accB = rows.filter((r) => r.okBefore).length;
const accA = rows.filter((r) => r.okAfter).length;
console.log(`  ABS accuracy ${accB}/${rows.length} -> ${accA}/${rows.length}`);
console.log(
  `  evidence session fully admitted: before ${rows.filter((r) => r.covBefore >= 0.999).length}` +
    ` -> after ${fully.length}`,
);
