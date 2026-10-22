/**
 * Test the prediction P22 attached to session-coherent admission.
 *
 * P22 established, on run 34915402976, that a failure admits 40.9% of its
 * evidence session where a correct answer admits 54.8%, with the gap surviving
 * inside fixed session-size bands. The fix completes a hit's session before
 * spending budget on unrelated neighbours, so it predicts three things at once:
 *
 *   1. The admitted fraction of the answer session RISES, and rises most where
 *      it was lowest (the failures), because those are the questions where the
 *      session was being read through neighbour expansion.
 *   2. Accuracy rises on questions whose answering turn was previously absent
 *      from the prompt -- the population the fix is aimed at.
 *   3. Questions whose answering turn was ALREADY present do not lose accuracy.
 *      This is the guard: session completion must not evict the turn the
 *      ranking liked in order to make room for its siblings, which is the one
 *      way this change can be actively harmful.
 *
 * Prediction 3 is the one that can embarrass the change, so it is reported with
 * the same weight as the others rather than as an afterthought.
 *
 * Usage: node p23_admission_outcome.mjs <afterRunDir> [beforeRunDir]
 */

import { readFileSync, existsSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const LME = '/tmp/lme-data/lme.json';
const DEFAULT_BEFORE = '/workspace/analysis/ab_retry/run_34915402976';

const afterDir = process.argv[2];
const beforeDir = process.argv[3] ?? DEFAULT_BEFORE;
if (!afterDir) {
  console.error('usage: node p23_admission_outcome.mjs <afterRunDir> [beforeRunDir]');
  process.exit(2);
}

const norm = (s) => String(s ?? '').replace(/\s+/g, ' ').trim();
const head = (s, n = 60) => norm(s).slice(0, n);

function contentWords(s) {
  return new Set(
    (String(s ?? '').toLowerCase().match(/[a-z][a-z0-9']*/g) ?? []).filter((w) => w.length >= 4)
  );
}

/** Does a turn state the gold value (verbatim, or >=75% of its content words)? */
function carriesGold(turn, gold) {
  const n = turn.toLowerCase();
  const g = String(gold).toLowerCase().trim();
  if (g !== '' && n.includes(g)) return true;
  const kw = [...contentWords(gold)];
  if (kw.length === 0) return false;
  return kw.filter((w) => n.includes(w)).length / kw.length >= 0.75;
}

function turnsOf(inst, sid) {
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const k = idsAll.indexOf(sid);
  if (k < 0) return [];
  const turns = sessions[k] ?? [];
  return Array.isArray(turns)
    ? turns.map((u) => String(u?.content ?? ''))
    : Object.values(turns).map((u) => String(u?.content ?? ''));
}

function readRun(dir) {
  const mr = `${dir}/MR_diagnostics.json`;
  const ss = `${dir}/Single-session_diagnostics.json`;
  if (!existsSync(mr) || !existsSync(ss)) return null;
  return [
    ...load(mr).map((d) => ['MR', d]),
    ...load(ss).map((d) => [d.capability, d]),
  ];
}

/** Per-question admission + correctness, keyed by question_id. */
function index(dir, meta) {
  const rows = readRun(dir);
  if (rows === null) return null;
  const out = new Map();
  for (const [cap, d] of rows) {
    const inst = meta.get(d.question_id);
    if (!inst) continue;
    const retrieved = norm(d.decision?.retrieved ?? '');
    let total = 0;
    let present = 0;
    let carriedPresent = false;
    let carriesTurns = 0;
    for (const sid of inst.answer_session_ids ?? []) {
      for (const t of turnsOf(inst, sid)) {
        if (!t) continue;
        total += 1;
        const isPresent = retrieved.includes(head(t));
        if (isPresent) present += 1;
        if (carriesGold(t, d.ground_truth)) {
          carriesTurns += 1;
          if (isPresent) carriedPresent = true;
        }
      }
    }
    out.set(d.question_id, {
      cap,
      correct: Boolean(d.correct),
      abstained: Boolean(d.decision?.abstained),
      present,
      total,
      carriedPresent,
      carriesTurns,
      retrievedChars: retrieved.length,
    });
  }
  return out;
}

const meta = new Map(load(LME).map((x) => [x.question_id, x]));
const before = index(beforeDir, meta);
const after = index(afterDir, meta);
if (before === null) {
  console.error(`FAIL: ${beforeDir} has no diagnostics files`);
  process.exit(1);
}
if (after === null) {
  console.error(`FAIL: ${afterDir} has no diagnostics files`);
  process.exit(1);
}

const shared = [...before.keys()].filter((id) => after.has(id));
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
const frac = (r) => r.present / Math.max(1, r.total);

console.log(`before: ${beforeDir}`);
console.log(`after : ${afterDir}`);
console.log(`questions present in both runs: ${shared.length}`);
console.log('');

console.log('=== prediction 1: admitted fraction of the answer session ===');
console.log('| group | before | after | delta |');
for (const [label, sel] of [
  ['all', () => true],
  ['CORRECT (before)', (r) => r.correct],
  ['FAIL (before)', (r) => !r.correct],
  ['answering turn absent (before)', (r) => !r.carriedPresent],
]) {
  const ids = shared.filter((id) => sel(before.get(id)));
  const b = mean(ids.map((id) => frac(before.get(id))));
  const a = mean(ids.map((id) => frac(after.get(id))));
  console.log(
    `| ${label.padEnd(30)} | ${(b * 100).toFixed(1)}% | ${(a * 100).toFixed(1)}% | ${((a - b) * 100 >= 0 ? '+' : '') + ((a - b) * 100).toFixed(1)} pp |`
  );
}
console.log('');

console.log('=== prediction 1b: the same contrast inside fixed session-size bands ===');
console.log('| band | before CORRECT | after CORRECT | before FAIL | after FAIL |');
for (const [label, lo, hi] of [
  ['10-30 turns', 10, 30],
  ['30-60 turns', 30, 60],
]) {
  const cell = (sel) => {
    const ids = shared.filter((id) => {
      const r = before.get(id);
      return r.total >= lo && r.total < hi && sel(r);
    });
    return mean(ids.map((id) => frac(after.get(id))));
  };
  const b = (sel) => {
    const ids = shared.filter((id) => {
      const r = before.get(id);
      return r.total >= lo && r.total < hi && sel(r);
    });
    return mean(ids.map((id) => frac(before.get(id))));
  };
  const c = (r) => r.correct;
  console.log(
    `| ${label.padEnd(11)} | ${(b(c) * 100).toFixed(1)}% | ${(cell(c) * 100).toFixed(1)}% | ${(b((r) => !r.correct) * 100).toFixed(1)}% | ${(cell((r) => !r.correct) * 100).toFixed(1)}% |`
  );
}
console.log('');

console.log('=== prediction 2: accuracy on the targeted population ===');
console.log('| population | n | before correct | after correct | delta |');
for (const [label, sel] of [
  ['answering turn absent (before)', (r) => !r.carriedPresent],
  ['answering turn present (before)', (r) => r.carriedPresent],
  ['all shared', () => true],
]) {
  const ids = shared.filter((id) => sel(before.get(id)));
  const b = ids.filter((id) => before.get(id).correct).length;
  const a = ids.filter((id) => after.get(id).correct).length;
  console.log(
    `| ${label.padEnd(30)} | ${String(ids.length).padStart(3)} | ${b} (${((b / Math.max(1, ids.length)) * 100).toFixed(1)}%) | ${a} (${((a / Math.max(1, ids.length)) * 100).toFixed(1)}%) | ${a - b >= 0 ? '+' : ''}${a - b} |`
  );
}
console.log('');

console.log('=== prediction 3 (the guard): questions already admitting the answering turn ===');
const already = shared.filter((id) => before.get(id).carriedPresent);
const lost = already.filter((id) => before.get(id).correct && !after.get(id).correct);
const gained = already.filter((id) => !before.get(id).correct && after.get(id).correct);
const bN = already.filter((id) => before.get(id).correct).length;
const aN = already.filter((id) => after.get(id).correct).length;
console.log(`n = ${already.length}`);
console.log(`before ${bN} correct -> after ${aN} correct  (${aN - bN >= 0 ? '+' : ''}${aN - bN})`);
console.log(`gained: ${gained.length}   lost: ${lost.length}`);
for (const id of lost) {
  const r = before.get(id);
  console.log(`  LOST ${id.padEnd(14)} ${r.cap}  admitted ${r.present}/${r.total}`);
}
console.log('');

console.log('=== churn overview: every question that changed verdict ===');
const churn = shared.filter((id) => before.get(id).correct !== after.get(id).correct);
console.log(`changed: ${churn.length} of ${shared.length}`);
console.log('| id | cap | before | after | admitted before | admitted after |');
for (const id of churn) {
  const b = before.get(id);
  const a = after.get(id);
  console.log(
    `| ${id.padEnd(14)} | ${b.cap.padEnd(3)} | ${b.correct ? 'ok' : 'BAD'} | ${a.correct ? 'ok' : 'BAD'} | ${b.present}/${b.total} | ${a.present}/${a.total} |`
  );
}
console.log('');

console.log('=== per-capability accuracy ===');
console.log('| cap | n | before | after | delta (pp) |');
for (const c of ['IE', 'MR', 'KU', 'TR', 'ABS']) {
  const ids = shared.filter((id) => before.get(id).cap === c);
  if (ids.length === 0) continue;
  const b = ids.filter((id) => before.get(id).correct).length;
  const a = ids.filter((id) => after.get(id).correct).length;
  const bp = (b / ids.length) * 100;
  const ap = (a / ids.length) * 100;
  console.log(
    `| ${c} | ${ids.length} | ${b} (${bp.toFixed(2)}%) | ${a} (${ap.toFixed(2)}%) | ${ap - bp >= 0 ? '+' : ''}${(ap - bp).toFixed(2)} |`
  );
}
console.log('');

console.log('=== prompt size: did the budget actually hold? ===');
console.log('| group | before mean chars | after mean chars | ratio |');
for (const [label, sel] of [
  ['all', () => true],
  ['CORRECT (after)', (r) => r.correct],
  ['FAIL (after)', (r) => !r.correct],
]) {
  const ids = shared.filter((id) => sel(after.get(id)));
  const b = mean(ids.map((id) => before.get(id).retrievedChars));
  const a = mean(ids.map((id) => after.get(id).retrievedChars));
  console.log(
    `| ${label.padEnd(16)} | ${b.toFixed(0)} | ${a.toFixed(0)} | ${(a / Math.max(1, b)).toFixed(3)}x |`
  );
}
