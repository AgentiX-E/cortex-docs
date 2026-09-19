/**
 * Per-question comparison of the retry fix against its own baseline.
 *
 * Same 500 questions, same model, same temperature, so this is a paired
 * comparison and every difference is attributable. The headline went the wrong
 * way (85.20% -> 83.80%), so this locates WHERE it went wrong, and specifically
 * whether the retry is responsible or whether the two runs disagree for reasons
 * the change cannot explain.
 *
 * The retry only fires on a bare abstention, so its causal footprint is bounded:
 * a question that neither run abstained on CANNOT have been changed by it, and
 * any flip there is run-to-run variance. That gives a hard test rather than a
 * narrative.
 */

import { readFileSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const RUNS = {
  base: '/workspace/analysis/ab_retry/run_34791592602',
  fix: '/workspace/analysis/ab_retry/run_34915402976',
};

/**
 * `MR_diagnostics.json` rows carry no `capability` field — only the 379
 * single-session rows do (150 IE / 127 TR / 72 KU / 30 ABS). So the 121 MR rows
 * used to fall through to the `'multi-session'` placeholder and never matched the
 * `'MR'` bucket, which is why the MR row of the first table printed `NaN%`.
 * The file the row came from IS the capability; index() now records it.
 */
function index(dir) {
  const fromMr = load(`${dir}/MR_diagnostics.json`).map((d) => ['MR', d]);
  const fromSs = load(`${dir}/Single-session_diagnostics.json`).map((d) => [d.capability, d]);
  const m = new Map();
  for (const [capability, d] of [...fromMr, ...fromSs]) m.set(d.question_id, { capability, d });
  return m;
}

const B = index(RUNS.base);
const F = index(RUNS.fix);
const ids = [...new Set([...B.keys(), ...F.keys()])].sort();

const acc = (m) => {
  let n = 0;
  let ok = 0;
  for (const id of ids) {
    const e = m.get(id);
    if (!e) continue;
    n++;
    if (e.d.correct) ok++;
  }
  return { n, ok, acc: (ok / n) * 100 };
};

const a = acc(B);
const b = acc(F);
console.log(`baseline ${a.ok}/${a.n} = ${a.acc.toFixed(2)}%`);
console.log(`fixed    ${b.ok}/${b.n} = ${b.acc.toFixed(2)}%`);
console.log(`delta    ${b.ok - a.ok} questions = ${(b.acc - a.acc).toFixed(2)} pp`);

// ------------------------------------------------------------- per capability

console.log('\n| cap | n | base | fix | Δq |');
const caps = ['IE', 'MR', 'KU', 'TR', 'ABS'];
let checkBase = 0;
let checkFix = 0;
for (const c of caps) {
  const sel = ids.filter((id) => (B.get(id)?.capability ?? F.get(id)?.capability) === c);
  const bk = sel.filter((id) => B.get(id)?.d.correct).length;
  const fk = sel.filter((id) => F.get(id)?.d.correct).length;
  checkBase += bk;
  checkFix += fk;
  console.log(
    `| ${c} | ${sel.length} | ${((bk / sel.length) * 100).toFixed(2)}% | ${((fk / sel.length) * 100).toFixed(2)}% | ${fk - bk >= 0 ? '+' : ''}${fk - bk} |`
  );
}
// The per-capability rows must reconcile to the headline, or one of the two is
// wrong. Cheap to assert, and the first version of this script shipped a table
// that silently did not.
console.log(`rows reconcile: base ${checkBase}/${a.ok}, fix ${checkFix}/${b.ok}`);

// --------------------------------------------------- the retry's causal footprint

const fired = [...F.values()].filter((e) => (e.d.decision ?? {}).retryFired === true);
console.log(`\n=== the ${fired.length} questions where the retry actually re-queried ===`);
let firedGain = 0;
let firedLoss = 0;
for (const e of fired) {
  const d = e.d;
  const was = B.get(d.question_id)?.d;
  const before = was?.correct ?? false;
  const now = d.correct;
  if (now && !before) firedGain++;
  if (!now && before) firedLoss++;
  const decl = (d.decision ?? {}).abstained ? 'still-declines' : `answered`;
  console.log(
    `  ${d.question_id.padEnd(14)} ${e.capability.padEnd(5)} ${before ? 'ok ' : 'BAD'} -> ${now ? 'ok ' : 'BAD'}  ${decl}`
  );
}
console.log(`\nretry-fired questions: gained ${firedGain}, lost ${firedLoss}`);

// --------------------------------------------- flips the retry CANNOT explain

console.log('\n=== flips outside the retry footprint (variance or another cause) ===');
const bothAnswered = [];
for (const id of ids) {
  const be = B.get(id);
  const fe = F.get(id);
  if (!be || !fe) continue;
  const bAbst = !!(be.d.decision ?? {}).abstained;
  const fAbst = !!(fe.d.decision ?? {}).abstained;
  const fFired = (fe.d.decision ?? {}).retryFired === true;
  if (bAbst || fAbst || fFired) continue; // inside the footprint
  if (be.d.correct !== fe.d.correct) bothAnswered.push({ id, cap: fe.capability, b: be.d, f: fe.d });
}
let vGain = 0;
let vLoss = 0;
for (const r of bothAnswered) {
  if (r.f.correct) vGain++;
  else vLoss++;
  console.log(
    `  ${r.id.padEnd(14)} ${r.cap.padEnd(5)} ${r.b.correct ? 'ok ' : 'BAD'} -> ${r.f.correct ? 'ok ' : 'BAD'}  gold="${String(r.f.ground_truth).slice(0, 30)}"`
  );
}
console.log(`\nneither run abstained, no fire: gained ${vGain}, lost ${vLoss}`);

// ------------------------------------------------------ abstention accounting

console.log('\n=== abstentions ===');
for (const [tag, m] of [['base', B], ['fix', F]]) {
  const ab = [...m.values()].filter((e) => (e.d.decision ?? {}).abstained);
  const wrong = ab.filter((e) => !e.d.correct).length;
  const bycap = {};
  for (const e of ab) bycap[e.capability] = (bycap[e.capability] ?? 0) + 1;
  console.log(`  ${tag}: ${ab.length} total, ${wrong} wrong  ${JSON.stringify(bycap)}`);
}
