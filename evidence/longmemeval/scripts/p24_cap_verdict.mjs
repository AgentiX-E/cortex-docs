#!/usr/bin/env node
/**
 * Adjudicate the P24 pre-registration (abstention admission cap).
 *
 * The pre-registration in `verdicts/p24-abstention-admission-cap-prereg.md` named
 * four predictions and three falsification conditions BEFORE run 35019792901
 * completed. This script evaluates them against the artifacts, and it is written
 * so that a failed prediction is as visible as a passed one:
 *
 *   P1  ABS accuracy >= 26/30  (recover the 2 net questions lost by 4955d8e)
 *   P2  mean admitted TURNS on ABS <= 30
 *   P3  the 45-60 turn band is no longer populated
 *   P4  no regression on IE / MR / KU / TR beyond run-to-run noise
 *
 * "Admitted turns" is measured on the abstention path's own prompt, not on the
 * answer-session coverage used by P21/P23. Those are different quantities and
 * conflating them is what produced the retracted P23 §3 claim:
 *
 *   - P21/P23 coverage  = turns of the ANSWER session present / answer session size
 *   - P24 admitted turns = distinct turns actually rendered into the prompt
 *
 * The second has no dependency on `answer_session_ids` (which ABS rows do not
 * carry) and is the quantity the cap bounds, so it is the right one here.
 *
 * No network, no API calls. Diagnostics only.
 *
 * Usage: node p24_cap_verdict.mjs <afterDir> <baselineDir> <regressionDir>
 */

import { readFileSync, existsSync } from 'node:fs';

const AFTER = process.argv[2];
const BASELINE = process.argv[3];
const REGRESSION = process.argv[4];

/**
 * Distinct turns rendered in a prompt.
 *
 * There is no reliable line-level delimiter. A turn's continuation lines are
 * indented but otherwise identical to a fresh header, so both a per-line count
 * (48 -> 45) and a "new turn whenever a header appears" state machine (48 -> 45,
 * only 4 distinct timestamps) collapse multi-turn sessions to their session
 * count. Two attempts, two wrong answers, both agreeing with the hypothesis they
 * were written to support.
 *
 * What actually separates turns is the session's own timestamp: every turn in a
 * session shares it, so the count of DISTINCT headers is the number of distinct
 * (session) timestamps present, not the number of turns. Counting turns from the
 * prompt is therefore not possible.
 *
 * The robust measurement is the one the prompt is really made of: characters.
 * This function returns the distinct-header count as a *session* count (honest
 * about what it is) plus the character total, and callers must use characters.
 */
const TURN_HEADER = /^\[([^\]]*)\]\s*(user|assistant):/gm;

function admittedTurns(prompt) {
  const text = String(prompt ?? '');
  if (text === '') return { sessions: 0, chars: 0 };
  const stamps = new Set();
  for (const m of text.matchAll(TURN_HEADER)) stamps.add(m[1]);
  return { sessions: stamps.size, chars: text.length };
}

const loadAbs = (dir) => {
  const p = `${dir}/Single-session_diagnostics.json`;
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, 'utf8')).filter((r) => r.capability === 'ABS');
};

const DIRS = {
  'baseline 34915402976 (pre-4955d8e)': BASELINE,
  'regression 35004814319 (4955d8e)': REGRESSION,
  'treatment 35019792901 (0b0069a)': AFTER,
};

const data = {};
for (const [name, dir] of Object.entries(DIRS)) {
  if (!dir) continue;
  const rows = loadAbs(dir);
  if (rows === null) {
    console.error(`FAIL: ${dir} has no Single-session_diagnostics.json`);
    process.exit(1);
  }
  data[name] = new Map(rows.map((r) => [r.question_id, r]));
}

const TREAT = 'treatment 35019792901 (0b0069a)';
const BASE = 'baseline 34915402976 (pre-4955d8e)';
const REGR = 'regression 35004814319 (4955d8e)';

const treat = data[TREAT];
const base = data[BASE];
const regr = data[REGR];

const correct = (m) => [...m.values()].filter((r) => r.correct === true).length;
const nTot = (m) => m.size;

// ---------------------------------------------------------------------------
console.log('=== P1: ABS accuracy ===\n');
console.log('| run | ABS correct | rate |');
for (const name of [BASE, REGR, TREAT]) {
  if (!data[name]) continue;
  console.log(`| ${name} | ${correct(data[name])}/${nTot(data[name])} | ${((100 * correct(data[name])) / nTot(data[name])).toFixed(1)}% |`);
}
const baseN = correct(base);
const regrN = correct(regr);
const treatN = correct(treat);
console.log('');
console.log(`P1 target: >= 26/30.  treatment = ${treatN}/30  -> ${treatN >= 26 ? 'PASS' : treatN === regrN ? 'FAIL (unchanged from regression)' : 'FAIL (below the pre-registered threshold)'}`);
console.log(`  baseline ${baseN}  regression ${regrN}  treatment ${treatN}   (treatment - regression = ${treatN - regrN >= 0 ? '+' : ''}${treatN - regrN})`);

// ---------------------------------------------------------------------------
console.log('\n=== P2/P3 (corrected): prompt SIZE, the quantity that actually separates ===\n');
const adm = {};
for (const name of [BASE, REGR, TREAT]) {
  if (!data[name]) continue;
  adm[name] = [...data[name].values()].map((r) => {
    const a = admittedTurns(r.decision?.retrieved);
    return { id: r.question_id, ...a, abst: r.decision?.abstained === true, correct: r.correct === true };
  });
  const cs = adm[name].map((x) => x.chars);
  const mean = cs.reduce((a, b) => a + b, 0) / cs.length;
  console.log(
    `${name.padEnd(34)} mean chars ${mean.toFixed(0).padStart(6)}  min ${String(Math.min(...cs)).padStart(5)}  ` +
      `max ${String(Math.max(...cs)).padStart(5)}  distinct sessions ${adm[name].reduce((a, x) => a + x.sessions, 0)}`,
  );
}
console.log('');
console.log('The turn count is NOT recoverable from the prompt: a multi-turn session shares');
console.log('one timestamp, and continuation lines are indistinguishable from headers.');
console.log('Two counters were written for it and both returned the session count. The');
console.log('measurement below is the one the data supports.');

const KNEE = 32000;
console.log(`\n--- the knee at ${KNEE} chars, per run ---`);
console.log('| run | <=knee n | abstain | acc | >knee n | abstain | acc |');
for (const name of [BASE, REGR, TREAT]) {
  if (!data[name]) continue;
  const lo = adm[name].filter((x) => x.chars <= KNEE);
  const hi = adm[name].filter((x) => x.chars > KNEE);
  const pc = (g, f) => (g.length ? (100 * g.filter(f).length) / g.length : NaN);
  const f1 = (x) => x.abst;
  const f2 = (x) => x.correct;
  const fmt = (g, f) => (g.length ? `${pc(g, f).toFixed(1)}%` : 'n/a');
  console.log(
    `| ${name} | ${lo.length} | ${fmt(lo, f1)} | ${fmt(lo, f2)} | ${hi.length} | ${fmt(hi, f1)} | ${fmt(hi, f2)} |`,
  );
}

console.log('\n--- pooled across runs: is "oversize" the failure axis? ---');
const pooled = [BASE, REGR, TREAT].filter((n) => data[n]).flatMap((n) => adm[n]);
const ov = pooled.filter((x) => x.chars > KNEE);
const un = pooled.filter((x) => x.chars <= KNEE);
console.log(`oversize >${KNEE}:  n=${ov.length}  correct ${ov.filter((x) => x.correct).length}  abstained ${ov.filter((x) => x.abst).length}`);
console.log(`within <=${KNEE}:  n=${un.length}  correct ${un.filter((x) => x.correct).length}  abstained ${un.filter((x) => x.abst).length}`);

// ---------------------------------------------------------------------------
console.log('\n=== P4: the other four capabilities (scope guard) ===\n');
const loadAll = (dir) => {
  const mr = JSON.parse(readFileSync(`${dir}/MR_diagnostics.json`, 'utf8')).map((r) => ['MR', r]);
  const ss = JSON.parse(readFileSync(`${dir}/Single-session_diagnostics.json`, 'utf8')).map((r) => [r.capability, r]);
  return [...mr, ...ss];
};
const allRuns = {};
for (const [name, dir] of Object.entries(DIRS)) {
  if (!dir) continue;
  allRuns[name] = new Map(loadAll(dir).map(([cap, r]) => [r.question_id, { cap, ...r }]));
}

console.log('| cap | n | baseline | regression | treatment | treat-regr | gained | lost | McNemar p |');
for (const cap of ['IE', 'MR', 'KU', 'TR', 'ABS']) {
  const ids = [...allRuns[TREAT].keys()].filter((id) => allRuns[TREAT].get(id).cap === cap);
  const b = ids.filter((id) => allRuns[BASE].get(id)?.correct).length;
  const r = ids.filter((id) => allRuns[REGR].get(id)?.correct).length;
  const t = ids.filter((id) => allRuns[TREAT].get(id)?.correct).length;
  const g = ids.filter((id) => !allRuns[REGR].get(id)?.correct && allRuns[TREAT].get(id)?.correct).length;
  const l = ids.filter((id) => allRuns[REGR].get(id)?.correct && !allRuns[TREAT].get(id)?.correct).length;
  let p = 1;
  const nd = g + l;
  if (nd > 0) {
    const k = Math.max(g, l);
    let tail = 0;
    for (let i = k; i <= nd; i++) {
      let c = 1;
      for (let j = 0; j < i; j++) c = (c * (nd - j)) / (j + 1);
      tail += c * Math.pow(0.5, nd);
    }
    p = Math.min(1, 2 * tail);
  }
  console.log(
    `| ${cap} | ${ids.length} | ${b} | ${r} | ${t} | ${t - r >= 0 ? '+' : ''}${t - r} | ${g} | ${l} | ${p.toFixed(4)} |`,
  );
}
console.log('');
console.log('P4 target: IE/MR/KU/TR unchanged beyond run-to-run noise.');
console.log('NOTE: with five cells tested, one at p<0.05 is expected under the null by');
console.log('multiplicity alone; a single marginal cell is a hypothesis, not a result.');

// ---------------------------------------------------------------------------
console.log('\n=== overall, for completeness ===');
const idsAll = [...allRuns[TREAT].keys()];
const oB = idsAll.filter((id) => allRuns[BASE].get(id)?.correct).length;
const oR = idsAll.filter((id) => allRuns[REGR].get(id)?.correct).length;
const oT = idsAll.filter((id) => allRuns[TREAT].get(id)?.correct).length;
console.log(`baseline ${oB}/500 = ${((100 * oB) / 500).toFixed(2)}%`);
console.log(`regression ${oR}/500 = ${((100 * oR) / 500).toFixed(2)}%`);
console.log(`treatment ${oT}/500 = ${((100 * oT) / 500).toFixed(2)}%`);
