/**
 * Does the session-coherent admission change move accuracy beyond run-to-run
 * noise?
 *
 * This is the decision script for the verdict, so it has to answer two
 * genuinely different questions and not let one masquerade as the other:
 *
 *   1. Is the head-line accuracy delta significant? At n = 500 paired
 *      questions, McNemar on the discordant pairs is the right test -- it uses
 *      only the questions that changed verdict, so it is not diluted by the
 *      400+ questions both runs answered the same way. It is exact, so it does
 *      not need a large-sample approximation, and it is one-sided in the
 *      direction the hypothesis predicts only if we say so explicitly.
 *
 *   2. Is the ADMITTED-FRACTION movement real? This is the mechanism claim, and
 *      it is far better powered than the accuracy claim: admission is a
 *      deterministic function of the retrieved set, so it moves on every
 *      question whose session was being read through neighbours rather than
 *      being completed. If the fix works as designed, this number must move
 *      whether or not the accuracy number does, and the two must be reported
 *      separately. "Accuracy moved" alone is uninterpretable: with a
 *      non-reproducible endpoint it is the expected output of both a working
 *      change and no change at all.
 *
 * A t-test on run means is deliberately NOT the primary test here. It is only
 * defined for R >= 2 runs and its power at R = 2 is poor; the paired McNemar
 * uses the 500 within-run comparisons that the paired design actually provides.
 * Where run means exist they are reported alongside as a cross-check, with the
 * smaller-R caveat stated rather than hidden.
 *
 * Usage: node p23_significance.mjs <afterRunDir> <beforeRunDir>
 */

import { readFileSync, existsSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const LME = '/tmp/lme-data/lme.json';

const afterDir = process.argv[2];
const beforeDir = process.argv[3];
if (!afterDir || !beforeDir) {
  console.error('usage: node p23_significance.mjs <afterRunDir> <beforeRunDir>');
  process.exit(2);
}

/** Exact two-sided binomial test, used for the sign test on flips. */
function signTest(lost, gained) {
  const n = lost + gained;
  if (n === 0) return { n: 0, k: 0, twoSidedP: 1 };
  const k = Math.max(lost, gained);
  let tail = 0;
  for (let i = k; i <= n; i++) {
    let c = 1;
    for (let j = 0; j < i; j++) c = (c * (n - j)) / (j + 1);
    tail += c * Math.pow(0.5, n);
  }
  return { n, k, twoSidedP: Math.min(1, 2 * tail) };
}

/** Exact McNemar p-value (two-sided) from the discordant counts. */
function mcnemar(a, b) {
  const n = a + b;
  if (n === 0) return 1;
  const k = Math.max(a, b);
  let tail = 0;
  for (let i = k; i <= n; i++) {
    let c = 1;
    for (let j = 0; j < i; j++) c = (c * (n - j)) / (j + 1);
    tail += c * Math.pow(0.5, n);
  }
  return Math.min(1, 2 * tail);
}

/** Wilson score interval, so a proportion near 0 or 1 is not mis-stated. */
function wilson(k, n) {
  if (n === 0) return [0, 1];
  const z = 1.96;
  const p = k / n;
  const denom = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const spread = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [(centre - spread) / denom, (centre + spread) / denom];
}

const norm = (s) => String(s ?? '').replace(/\s+/g, ' ').trim();
const head = (s, n = 60) => norm(s).slice(0, n);

function contentWords(s) {
  return new Set(
    (String(s ?? '').toLowerCase().match(/[a-z][a-z0-9']*/g) ?? []).filter((w) => w.length >= 4)
  );
}

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

function index(dir, meta) {
  const mr = `${dir}/MR_diagnostics.json`;
  const ss = `${dir}/Single-session_diagnostics.json`;
  if (!existsSync(mr) || !existsSync(ss)) return null;
  const rows = [...load(mr).map((d) => ['MR', d]), ...load(ss).map((d) => [d.capability, d])];
  const out = new Map();
  for (const [cap, d] of rows) {
    const inst = meta.get(d.question_id);
    if (!inst) continue;
    const retrieved = norm(d.decision?.retrieved ?? '');
    let total = 0;
    let present = 0;
    let carriedPresent = false;
    for (const sid of inst.answer_session_ids ?? []) {
      for (const t of turnsOf(inst, sid)) {
        if (!t) continue;
        total += 1;
        const isPresent = retrieved.includes(head(t));
        if (isPresent) present += 1;
        if (carriesGold(t, d.ground_truth) && isPresent) carriedPresent = true;
      }
    }
    out.set(d.question_id, {
      cap,
      correct: Boolean(d.correct),
      present,
      total,
      carriedPresent,
      frac: present / Math.max(1, total),
    });
  }
  return out;
}

const meta = new Map(load(LME).map((x) => [x.question_id, x]));
const before = index(beforeDir, meta);
const after = index(afterDir, meta);
if (before === null || after === null) {
  console.error('FAIL: missing diagnostics in one of the run dirs');
  process.exit(1);
}
const shared = [...before.keys()].filter((id) => after.has(id));
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

console.log(`before: ${beforeDir}`);
console.log(`after : ${afterDir}`);
console.log(`n = ${shared.length} paired questions`);
console.log('');

// ---------------------------------------------------------------- accuracy
const bCorrect = shared.filter((id) => before.get(id).correct).length;
const aCorrect = shared.filter((id) => after.get(id).correct).length;
const gained = shared.filter((id) => !before.get(id).correct && after.get(id).correct);
const lost = shared.filter((id) => before.get(id).correct && !after.get(id).correct);
const [bl, bu] = wilson(bCorrect, shared.length);
const [al, au] = wilson(aCorrect, shared.length);

console.log('=== 1. accuracy ===');
console.log(
  `before ${bCorrect}/${shared.length} = ${((bCorrect / shared.length) * 100).toFixed(2)}%  (95% CI ${(bl * 100).toFixed(2)}-${(bu * 100).toFixed(2)}%)`
);
console.log(
  `after  ${aCorrect}/${shared.length} = ${((aCorrect / shared.length) * 100).toFixed(2)}%  (95% CI ${(al * 100).toFixed(2)}-${(au * 100).toFixed(2)}%)`
);
console.log(
  `delta  ${aCorrect - bCorrect >= 0 ? '+' : ''}${aCorrect - bCorrect} questions = ${(((aCorrect - bCorrect) / shared.length) * 100).toFixed(2)} pp`
);
console.log(`discordant pairs: ${gained.length} gained, ${lost.length} lost`);
const pAcc = mcnemar(lost.length, gained.length);
console.log(`exact McNemar two-sided p = ${pAcc.toFixed(4)}`);
console.log(
  pAcc < 0.05
    ? '  -> the accuracy delta is significant at 0.05.'
    : '  -> NOT significant: the accuracy delta is within paired-noise range.'
);
console.log('');

// ------------------------------------------------------- admitted fraction
console.log('=== 2. admitted fraction of the answer session (the mechanism claim) ===');
console.log('| group | n | before | after | delta |');
for (const [label, sel] of [
  ['all', () => true],
  ['correct (before)', (r) => r.correct],
  ['fail (before)', (r) => !r.correct],
  ['answering turn absent (before)', (r) => !r.carriedPresent],
]) {
  const ids = shared.filter((id) => sel(before.get(id)));
  const b = mean(ids.map((id) => before.get(id).frac));
  const a = mean(ids.map((id) => after.get(id).frac));
  console.log(
    `| ${label.padEnd(30)} | ${String(ids.length).padStart(3)} | ${(b * 100).toFixed(1)}% | ${(a * 100).toFixed(1)}% | ${a - b >= 0 ? '+' : ''}${((a - b) * 100).toFixed(1)} pp |`
  );
}

// Per-question movement: admission is deterministic, so this should be large
// and one-directional. A Wilcoxon-style sign test on the per-question deltas
// answers "did admission improve" without assuming the deltas are normal.
const deltas = shared.map((id) => after.get(id).frac - before.get(id).frac);
const up = deltas.filter((d) => d > 1e-9).length;
const down = deltas.filter((d) => d < -1e-9).length;
const flat = deltas.length - up - down;
const st = signTest(down, up);
console.log('');
console.log(`per-question admission change: ${up} up, ${down} down, ${flat} unchanged`);
console.log(`exact two-sided sign test p = ${st.twoSidedP.toExponential(3)}`);
console.log(
  st.twoSidedP < 0.05
    ? '  -> admission moved, and moved one-directionally: the mechanism fired.'
    : '  -> admission did NOT move as a whole: the mechanism did not fire and any accuracy delta is unrelated to it.'
);
console.log(`mean per-question change = ${(mean(deltas) * 100).toFixed(2)} pp of the answer session`);
console.log('');

// ------------------------------------------------------------- the contrast
console.log('=== 3. did the §5 gap close? (the falsifiable prediction) ===');
const gapBefore =
  mean(shared.filter((id) => before.get(id).correct).map((id) => before.get(id).frac)) -
  mean(shared.filter((id) => !before.get(id).correct).map((id) => before.get(id).frac));
const gapAfter =
  mean(shared.filter((id) => after.get(id).correct).map((id) => after.get(id).frac)) -
  mean(shared.filter((id) => !after.get(id).correct).map((id) => after.get(id).frac));
console.log(`gap before = ${(gapBefore * 100).toFixed(1)} pp, gap after = ${(gapAfter * 100).toFixed(1)} pp`);
console.log('Caveat that must travel with this number: the "correct"/"fail" partition is');
console.log('recomputed after the change, so a group whose membership changed also changed');
console.log('the statistic. Compare gaps within a FIXED partition as well, below.');
console.log('');
const fixedGapBefore =
  mean(shared.filter((id) => before.get(id).correct).map((id) => before.get(id).frac)) -
  mean(shared.filter((id) => !before.get(id).correct).map((id) => before.get(id).frac));
const fixedGapAfter =
  mean(shared.filter((id) => before.get(id).correct).map((id) => after.get(id).frac)) -
  mean(shared.filter((id) => !before.get(id).correct).map((id) => after.get(id).frac));
console.log(
  `within the FIXED before-partition: gap ${(fixedGapBefore * 100).toFixed(1)} pp -> ${(fixedGapAfter * 100).toFixed(1)} pp`
);
console.log('');

// ------------------------------------------------------------ per capability
console.log('=== 4. per capability ===');
console.log('| cap | n | before | after | delta (pp) | gained | lost | McNemar p |');
for (const c of ['IE', 'MR', 'KU', 'TR', 'ABS']) {
  const ids = shared.filter((id) => before.get(id).cap === c);
  if (ids.length === 0) continue;
  const b = ids.filter((id) => before.get(id).correct).length;
  const a = ids.filter((id) => after.get(id).correct).length;
  const g = ids.filter((id) => !before.get(id).correct && after.get(id).correct).length;
  const l = ids.filter((id) => before.get(id).correct && !after.get(id).correct).length;
  const p = mcnemar(l, g);
  const bp = (b / ids.length) * 100;
  const ap = (a / ids.length) * 100;
  console.log(
    `| ${c} | ${ids.length} | ${bp.toFixed(2)}% | ${ap.toFixed(2)}% | ${ap - bp >= 0 ? '+' : ''}${(ap - bp).toFixed(2)} | ${g} | ${l} | ${p.toFixed(4)} |`
  );
}
console.log('');
console.log('NOTE: with five capabilities tested, one at p<0.05 is expected under the null');
console.log('by multiplicity alone; treat a single marginal cell as a hypothesis, not a result.');
