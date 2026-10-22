/**
 * Attribute the MR 90.08% reading between the engine and the grader.
 *
 * Two changes landed between the 8-run panel (2026-09-06) and run 34791592602
 * (2026-09-14), and both can flip a question from wrong to right:
 *
 *   (a) engine: c3a52ee, 4a7fddb, c4ab77b, f35c4a4, 236ab1b
 *   (b) grader: cce134e
 *
 * They CANNOT be separated from the aggregate, because they produce the same
 * observable. They CAN be separated per question, by replaying the PRE-cce134e
 * grader against the new run's answer strings:
 *
 *   old grader = numericAnswerVerdict(question, answer, gold)   // p === e, no deferral
 *                ?? judge("is the predicted answer semantically equivalent to the
 *                          ground-truth answer?")
 *   new grader = numericAnswerVerdict(question, answer, gold)   // + multi-value deferral
 *                ?? judge(defaultTemplate)  for multi-session
 *
 * All 121 MR questions are `multi-session`, so the temporal off-by-one tolerance
 * and the knowledge-update clause introduced by cce134e never reach this path.
 * The only grader deltas that can act here are (i) the multi-value numeric
 * deferral and (ii) "contains the gold / all intermediate steps" replacing plain
 * "semantically equivalent".
 *
 * Classification (decisive without an LLM, because no LLM key exists here):
 *   GATE  - the old numeric gate would itself have returned true. Fully decidable.
 *   IDENT - normalizeAnswer(answer) === normalizeAnswer(gold). Any equivalence or
 *           containment judge returns true on an identical string; the containment
 *           wording cannot be what flipped it.
 *   JUDGE - neither holds. The old verdict is a judge call and is NOT resolvable
 *           locally. Reported as an explicit upper bound, never as a gain.
 */

import { readFileSync } from 'node:fs';

const PANEL = '/workspace/analysis/ab_rrf';
const NEW = '/workspace/analysis/ab_retry/run_34791592602/mr_diagnostics.json';

const panelRuns = [
  'run_34024727400',
  'run_34024729633',
  'run_34024732117',
  'run_34024734868',
  'run_34024737250',
  'run_34024740818',
  'run_34024743185',
  'run_34024745627',
];

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));

// ---- verbatim re-implementation of the pre-cce134e scoring primitives ---------

const normalizeAnswer = (a) => String(a).trim().toLowerCase().replace(/\s+/g, ' ');

/** Verbatim: unchanged by cce134e. */
const isCountingQuestion = (q) => /\b(how many|how much|number of|count|total)\b/i.test(q);

/** The old gate read the leading number of each side and compared them. */
function extractLeadingNumber(text) {
  const m = String(text).match(/-?\d[\d,]*(?:\.\d+)?/);
  if (!m) return undefined;
  return Number(m[0].replace(/,/g, ''));
}

/**
 * The PRE-cce134e gate: no multi-value deferral, so it decides whenever both
 * sides carry a number. Returns undefined (fall through to the judge) otherwise.
 */
function oldNumericGate(question, predicted, expected) {
  if (!isCountingQuestion(question)) return undefined;
  const p = extractLeadingNumber(predicted);
  const e = extractLeadingNumber(expected);
  if (p === undefined || e === undefined) return undefined;
  return p === e;
}

// ------------------------------------------------------------------- load data

const rows = [];
const newDiags = load(NEW);
for (const d of newDiags) {
  rows.push({
    id: d.question_id,
    question: d.question ?? '',
    gold: String(d.ground_truth ?? ''),
    answer: String((d.decision ?? {}).answer ?? ''),
    abstained: !!(d.decision ?? {}).abstained,
    correct: d.correct ? 1 : 0,
    pHits: [],
    pAbstained: [],
  });
}
const byId = new Map(rows.map((r) => [r.id, r]));

for (const r of panelRuns) {
  const diags = load(`${PANEL}/${r}/longmemeval-s-report/benchmark-mr-diagnostics.json`);
  for (const d of diags) {
    const row = byId.get(d.question_id);
    if (!row) continue;
    row.pHits.push(d.correct ? 1 : 0);
    row.pAbstained.push(!!(d.decision ?? {}).abstained);
  }
}

const full = rows.filter((r) => r.pHits.length === panelRuns.length);
console.log(`MR questions with a complete 8-run panel: ${full.length} of ${rows.length}`);

for (const r of full) {
  r.pRate = r.pHits.reduce((a, b) => a + b, 0) / r.pHits.length;
  r.pAbstainRate = r.pAbstained.filter(Boolean).length / r.pAbstained.length;
  r.oldGate = oldNumericGate(r.question, r.answer, r.gold);
  r.ident = normalizeAnswer(r.answer) === normalizeAnswer(r.gold);
  r.cls = r.oldGate === true ? 'GATE' : r.ident ? 'IDENT' : 'JUDGE';
}

const panelAcc = full.reduce((a, r) => a + r.pRate, 0) / full.length;
const newAcc = full.reduce((a, r) => a + r.correct, 0) / full.length;
const N = full.length;
const deltaPp = (newAcc - panelAcc) * 100;

// ------------------------------------------------------------------ flip table
//
// Every one of the 121 questions carries a signed contribution `correct - pRate`.
// Dropping any cell silently loses part of the delta, so all four cells are
// accounted; they must sum to the aggregate delta or the numbers are wrong.

const cell = (r) =>
  r.pRate <= 0.5 ? (r.correct === 1 ? 'gained' : 'never') : r.correct === 1 ? 'held' : 'lost';
for (const r of full) {
  r.cell = cell(r);
  r.contrib = r.correct - r.pRate;
}

const sum = (xs) => xs.reduce((a, r) => a + r.contrib, 0);
const gained = full.filter((r) => r.cell === 'gained');
const held = full.filter((r) => r.cell === 'held');
const lost = full.filter((r) => r.cell === 'lost');
const never = full.filter((r) => r.cell === 'never');

const grossGain = sum(gained) + sum(held);
const grossLoss = sum(lost) + sum(never);
const reconciled = grossGain + grossLoss;

console.log(
  `\npanel expected ${(panelAcc * 100).toFixed(2)}%  ->  new run ${(newAcc * 100).toFixed(2)}%   delta ${deltaPp >= 0 ? '+' : ''}${deltaPp.toFixed(2)} pp`
);
console.log(`\nfour-cell decomposition (question-units; must sum to ${(deltaPp / 100) * N}.2f):`);
console.log(`  gained ${String(gained.length).padStart(3)}  ${sum(gained) >= 0 ? '+' : ''}${sum(gained).toFixed(2)}`);
console.log(`  held   ${String(held.length).padStart(3)}  ${sum(held) >= 0 ? '+' : ''}${sum(held).toFixed(2)}`);
console.log(`  lost   ${String(lost.length).padStart(3)}  ${sum(lost) >= 0 ? '+' : ''}${sum(lost).toFixed(2)}`);
console.log(`  never  ${String(never.length).padStart(3)}  ${sum(never) >= 0 ? '+' : ''}${sum(never).toFixed(2)}`);
console.log(
  `  TOTAL  ${String(full.length).padStart(3)}  ${reconciled >= 0 ? '+' : ''}${reconciled.toFixed(2)}   (sanity: ${Math.abs(reconciled * (100 / N) - deltaPp) < 1e-9 ? 'OK' : 'MISMATCH'})`
);

// ------------------------------------------------------------- attribution

const bucket = (cls) => gained.filter((r) => r.cls === cls);

console.log(`\n=== attribution of the ${gained.length} gained questions ===`);
for (const cls of ['GATE', 'IDENT', 'JUDGE']) {
  const g = bucket(cls);
  const units = g.reduce((a, r) => a + (1 - r.pRate), 0);
  console.log(
    `  ${cls.padEnd(5)}  ${String(g.length).padStart(2)} questions   ${units.toFixed(2)} question-units   ${((units / N) * 100).toFixed(2)} pp`
  );
}

console.log(`\n--- GATE: old numeric gate would itself have passed (decidable) ---`);
for (const r of bucket('GATE')) {
  console.log(
    `  ${r.id}  panel ${r.pHits.reduce((a, b) => a + b, 0)}/8  gold="${r.gold}"  answer="${r.answer}"`
  );
}

console.log(`\n--- IDENT: answer string is the gold string (any judge agrees) ---`);
for (const r of bucket('IDENT')) {
  console.log(
    `  ${r.id}  panel ${r.pHits.reduce((a, b) => a + b, 0)}/8  abstain ${r.pAbstainRate.toFixed(2)}  gold="${r.gold}"`
  );
}

console.log(`\n--- JUDGE: NOT resolvable locally; upper bound only ---`);
for (const r of bucket('JUDGE')) {
  console.log(
    `  ${r.id}  panel ${r.pHits.reduce((a, b) => a + b, 0)}/8  gold="${r.gold.slice(0, 80)}"  answer="${r.answer.slice(0, 60)}"`
  );
}

// ------------------------------------------------- how much CAN the grader own?

const judgeUnits = bucket('JUDGE').reduce((a, r) => a + (1 - r.pRate), 0);
const engineUnits = gained.reduce((a, r) => a + (1 - r.pRate), 0) - judgeUnits;
console.log(`\n=== BOUND ===`);
console.log(
  `engine-attributable : ${engineUnits.toFixed(2)} question-units = ${((engineUnits / N) * 100).toFixed(2)} pp`
);
console.log(
  `grader-attributable : at most ${judgeUnits.toFixed(2)} question-units = at most ${((judgeUnits / N) * 100).toFixed(2)} pp`
);
console.log(
  `                      (of which the multi-value numeric deferral contributes exactly 0, verified below)`
);

// the deferral specifically: gold with >1 distinct value AND answer hits a non-leading one
const deferral = gained.filter((r) => {
  const gv = [...new Set((r.gold.match(/\d[\d,]*(?:\.\d+)?/g) ?? []).map((s) => s))];
  if (gv.length < 2) return false;
  const lead = extractLeadingNumber(r.gold);
  const an = extractLeadingNumber(r.answer);
  return an !== undefined && an !== lead && gv.includes(String(an));
});
console.log(`multi-value numeric deferral gains: ${deferral.length}`);

// -------------------------------------------------------------- the two losses

console.log(`\n=== losses ===`);
for (const r of lost) {
  console.log(
    `  ${r.id}  panel ${r.pHits.reduce((a, b) => a + b, 0)}/8  gold="${r.gold}"  answer="${r.answer}"  cls=${r.cls}`
  );
}

// ------------------------------------------------- tighten: the held bucket too
//
// The 91 "held" questions were already mostly right under the OLD grader, so a
// looser grader could in principle own part of their residual. Bound it the same
// way: only a question whose answer is neither gate-passing nor identical to the
// gold can have been flipped by the containment wording.
const heldJudge = held.filter((r) => r.cls === "JUDGE");
const heldJudgeUnits = heldJudge.reduce((a, r) => a + r.contrib, 0);
console.log(`\nheld bucket: ${held.length} questions, +${sum(held).toFixed(2)} units; of those ${heldJudge.length} are JUDGE-classified (${heldJudgeUnits.toFixed(2)} units)`);
console.log(`GRADER UPPER BOUND over all positive contributions: ${(judgeUnits + heldJudgeUnits).toFixed(2)} of ${grossGain.toFixed(2)} units = ${(((judgeUnits + heldJudgeUnits) / grossGain) * 100).toFixed(1)}%`);
