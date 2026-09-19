/**
 * Attribute the MR 90.08% reading between two candidate causes that both landed
 * after the 8-run panel of 2026-09-06:
 *
 *   (a) engine fixes  c4ab77b / f35c4a4 / 236ab1b   (2026-09-13)
 *   (b) grader change cce134e                        (2026-09-12)
 *
 * The two produce the same observable -- a question flipping from wrong to right --
 * so they cannot be separated from the aggregate alone. This script separates them
 * where the separation is DECIDABLE WITHOUT AN LLM JUDGE, and explicitly refuses
 * to guess where it is not.
 *
 * Decidable without a judge:
 *   cce134e changed the deterministic numeric pre-gate. Before, it compared the
 *   prediction against the LEADING number of the gold only; a gold stating two
 *   acceptable values ("11 days (or 12 days ...)") therefore rejected a prediction
 *   of the second value without ever reaching a judge. Now such a gold defers to
 *   the judge. A question whose gold states >= 2 distinct values and whose new
 *   answer matches a NON-LEADING value is a grader gain, fully attributable.
 *
 *   cce134e also swapped the judge prompt. For multi-session that change is
 *   "contains the gold OR carries all intermediate steps" vs plain "semantically
 *   equivalent". That is NOT decidable without running the judge, so every flip
 *   that cannot be pinned on the numeric gate is reported as UNRESOLVED.
 */

import { readFileSync } from 'node:fs';

const PANEL = '/workspace/analysis/ab_rrf';
const NEW = '/workspace/analysis/ab_retry/run_34791592602/mr_diagnostics.json';
const LME = '/tmp/lme-data/lme.json';

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

// ---------------------------------------------------------------- dataset side

const lme = load(LME);
const byId = new Map();
for (const inst of lme) {
  byId.set(inst.question_id, inst);
}

// ------------------------------------------------------------------ panel side

/** question_id -> array of 0/1, one per panel run, in panelRuns order */
const panel = new Map();
for (const r of panelRuns) {
  const diags = load(`${PANEL}/${r}/longmemeval-s-report/benchmark-mr-diagnostics.json`);
  for (const d of diags) {
    if (!panel.has(d.question_id)) panel.set(d.question_id, []);
    panel.get(d.question_id).push(d.correct ? 1 : 0);
  }
}

// --------------------------------------------------------------------- new run

const newDiags = load(NEW);
const newById = new Map();
for (const d of newDiags) newById.set(d.question_id, d);

const ids = [...newById.keys()].filter((id) => panel.has(id));

console.log(`MR questions: new run ${newById.size}, panel ${panel.size}, intersection ${ids.length}`);

// --------------------------------------------------------------- the flip table

const rows = ids.map((id) => {
  const hits = panel.get(id);
  const pHits = hits.reduce((a, b) => a + b, 0);
  const inst = byId.get(id) ?? {};
  const nd = newById.get(id);
  const dec = nd.decision ?? {};
  return {
    id,
    type: inst.question_type ?? '?',
    qtype: nd.question_type ?? inst.question_type ?? '?',
    gold: String(nd.ground_truth ?? inst.answer ?? ''),
    pHits,
    pRate: pHits / hits.length,
    nCorrect: nd.correct ? 1 : 0,
    nAnswer: String(dec.answer ?? ''),
    nAbstained: !!dec.abstained,
    nRaw: String(dec.llmRaw ?? ''),
    pAbstained: null, // filled below
  };
});

// panel abstention flag: was the panel's dominant outcome an abstention?
for (const r of panelRuns) {
  const diags = load(`${PANEL}/${r}/longmemeval-s-report/benchmark-mr-diagnostics.json`);
  for (const d of diags) {
    const row = rows.find((x) => x.id === d.question_id);
    if (!row) continue;
    if (row.pAbstained === null) row.pAbstained = [];
    row.pAbstained.push(!!(d.decision ?? {}).abstained);
  }
}

const panelAcc = rows.reduce((a, r) => a + r.pRate, 0) / rows.length;
const newAcc = rows.reduce((a, r) => a + r.nCorrect, 0) / rows.length;
const delta = (newAcc - panelAcc) * 100;

console.log(
  `panel expected accuracy ${(panelAcc * 100).toFixed(2)}%  new run ${(newAcc * 100).toFixed(2)}%  delta ${delta >= 0 ? '+' : ''}${delta.toFixed(2)} pp`
);

// ------------------------------------------------------- numeric gate replay

const THOUSANDS_SEP = /^\d{1,3}(,\d{3})+$/;
const DECIMAL = /^\d+\.\d+$/;

/** Distinct numeric values stated in a gold, honouring the separators cce134e kept. */
function goldValues(gold) {
  const out = [];
  const re = /\d[\d,]*(?:\.\d+)?/g;
  let m;
  while ((m = re.exec(gold)) !== null) {
    const tok = m[0];
    if (THOUSANDS_SEP.test(tok) || DECIMAL.test(tok)) {
      out.push(tok);
      continue;
    }
    out.push(tok);
  }
  return [...new Set(out)];
}

function answerNumbers(ans) {
  return [...new Set((ans.match(/\d[\d,]*(?:\.\d+)?/g) ?? []))];
}

const multiValueGold = rows.filter((r) => goldValues(r.gold).length >= 2);

console.log(`\ngold states >= 2 distinct numeric values: ${multiValueGold.length} of ${rows.length}`);

// A flip is GRADER-caused if the gold is multi-value and the new answer matches a
// non-leading gold value: the pre-cce134e gate compared against the leading value
// only and would have failed it deterministically.
const graderGains = [];
const graderSuspect = [];
for (const r of rows) {
  if (r.nCorrect !== 1) continue;
  const gv = goldValues(r.gold);
  if (gv.length < 2) continue;
  const an = answerNumbers(r.nAnswer);
  if (an.length === 0) {
    graderSuspect.push(r);
    continue;
  }
  const leading = gv[0];
  const matchesLeading = an.includes(leading);
  const matchesAny = an.some((v) => gv.includes(v));
  if (matchesAny && !matchesLeading) graderGains.push({ ...r, goldValues: gv, answerNumbers: an });
  else if (!matchesAny) graderSuspect.push({ ...r, goldValues: gv, answerNumbers: an });
}

console.log(
  `\nATTRIBUTABLE TO THE GRADER (multi-value gold, new answer hits a non-leading value): ${graderGains.length}`
);
for (const r of graderGains) {
  console.log(
    `  ${r.id}  panel ${r.pHits}/8  gold="${r.gold.slice(0, 70)}"  values=[${r.goldValues.join(' | ')}]  answer="${r.nAnswer.slice(0, 60)}"  nums=[${r.answerNumbers.join(' | ')}]`
  );
}

// ------------------------------------------------------------ mechanism split

const gained = rows.filter((r) => r.pRate <= 0.5 && r.nCorrect === 1);
const held = rows.filter((r) => r.pRate > 0.5 && r.nCorrect === 1);
const lost = rows.filter((r) => r.pRate > 0.5 && r.nCorrect === 0);
const never = rows.filter((r) => r.pRate <= 0.5 && r.nCorrect === 0);

const panelAbstainMajority = (r) =>
  Array.isArray(r.pAbstained) && r.pAbstained.filter(Boolean).length >= 5;

const abstainToAnswer = gained.filter((r) => panelAbstainMajority(r) && !r.nAbstained);

console.log(`\n--- flip table ---`);
console.log(
  `gained (panel <=4/8 -> correct): ${gained.length}   of which panel mostly abstained: ${abstainToAnswer.length}`
);
console.log(`held   (panel >=5/8 -> correct): ${held.length}`);
console.log(`lost   (panel >=5/8 -> wrong)  : ${lost.length}`);
console.log(`never  (panel <=4/8 -> wrong)  : ${never.length}`);

console.log(`\n--- abstention -> answer (engine-attributable, judge-independent) ---`);
for (const r of abstainToAnswer) {
  console.log(
    `  ${r.id}  panel ${r.pHits}/8 abstained ${r.pAbstained.filter(Boolean).length}/8  gold="${r.gold.slice(0, 50)}"  new="${r.nAnswer.slice(0, 70)}"`
  );
}

console.log(`\n--- lost ---`);
for (const r of lost) {
  console.log(
    `  ${r.id}  panel ${r.pHits}/8  type=${r.qtype}  gold="${r.gold.slice(0, 60)}"  new="${r.nAnswer.slice(0, 70)}"`
  );
}

console.log(`\n--- question type mix of the gained set ---`);
const mix = {};
for (const r of gained) mix[r.qtype] = (mix[r.qtype] ?? 0) + 1;
console.log(mix);

// ------------------------------------------------------------------ verdict

const graderIds = new Set(graderGains.map((r) => r.id));
const engineIds = new Set(abstainToAnswer.map((r) => r.id));
const unresolved = gained.filter((r) => !graderIds.has(r.id) && !engineIds.has(r.id));

console.log(`\n=== ATTRIBUTION ===`);
console.log(`total delta                : ${delta >= 0 ? '+' : ''}${delta.toFixed(2)} pp`);
console.log(`  grader-decidable         : ${graderGains.length} questions`);
console.log(`  engine-decidable         : ${abstainToAnswer.length} questions`);
console.log(`  UNRESOLVED (needs judge) : ${unresolved.length} questions`);
for (const r of unresolved) {
  console.log(
    `     ${r.id}  panel ${r.pHits}/8  type=${r.qtype}  gold="${r.gold.slice(0, 45)}"  new="${r.nAnswer.slice(0, 55)}"`
  );
}
