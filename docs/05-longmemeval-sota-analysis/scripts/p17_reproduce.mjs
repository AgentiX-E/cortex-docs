#!/usr/bin/env node
/**
 * Reproduce every headline number in verdicts/p17-abstention-retry-yield.md.
 * Reads only the checked-in ab_rrf artifacts; makes no API calls.
 *
 * Usage: node analysis/scripts/p17_reproduce.mjs <analysisDir>
 */
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const root = process.argv[2] ?? '.';
const TOKEN = 'UNANSWERABLE';

const runDirs = readdirSync(join(root, 'ab_rrf'), { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => d.name)
  .sort();

const panels = {};
for (const run of runDirs) {
  const p = join(root, 'ab_rrf', run, 'longmemeval-s-report', 'benchmark-mr-diagnostics.json');
  const rows = JSON.parse(readFileSync(p, 'utf8'));
  panels[run] = new Map(rows.map((r) => [r.question_id, r]));
}
const runs = Object.keys(panels);

const isBare = (rec) => {
  const raw = rec.decision?.llmRaw;
  return typeof raw === 'string' && raw.trim().replace(/"/g, '').toUpperCase() === TOKEN;
};
const fp = (rec) =>
  createHash('sha256')
    .update(`${rec.decision.question}\u0000${rec.decision.retrieved ?? ''}`)
    .digest('hex')
    .slice(0, 12);

// --- panel integrity ---
const sizes = new Set(runs.map((r) => panels[r].size));
const idSets = new Set(runs.map((r) => [...panels[r].keys()].sort().join(',')));
console.log('runs:', runs.length);
console.log('questions per run:', [...sizes].join(','));
console.log('identical id sets:', idSets.size === 1);

// --- per-run accuracy ---
const accs = runs.map((r) => [...panels[r].values()].filter((x) => x.correct).length / panels[r].size);
console.log(
  `accuracy min=${(Math.min(...accs) * 100).toFixed(2)}% max=${(Math.max(...accs) * 100).toFixed(2)}% ` +
    `mean=${((accs.reduce((a, b) => a + b, 0) / accs.length) * 100).toFixed(2)}% ` +
    `spread=${((Math.max(...accs) - Math.min(...accs)) * 100).toFixed(2)}pp`,
);

// --- stability ---
const qids = [...panels[runs[0]].keys()];
let sc = 0, sw = 0, fl = 0;
for (const q of qids) {
  const v = runs.map((r) => panels[r].get(q).correct);
  if (v.every(Boolean)) sc++;
  else if (!v.some(Boolean)) sw++;
  else fl++;
}
console.log(`stable-correct=${sc} stable-wrong=${sw} flaky=${fl}`);

// --- flip classification ---
let bareQuestions = 0, flipOnIdentical = 0;
for (const q of qids) {
  const bareRuns = runs.filter((r) => isBare(panels[r].get(q)));
  if (bareRuns.length === 0) continue;
  bareQuestions++;
  const groups = new Map();
  for (const r of runs) {
    const rec = panels[r].get(q);
    const f = fp(rec);
    const g = groups.get(f) ?? { bare: 0, correct: 0 };
    if (isBare(rec)) g.bare++;
    if (rec.correct) g.correct++;
    groups.set(f, g);
  }
  if ([...groups.values()].some((g) => g.bare > 0 && g.correct > 0)) flipOnIdentical++;
}
console.log(`bare-abstention questions=${bareQuestions} flip-on-identical-prompt=${flipOnIdentical}`);

// --- subpopulations ---
let A = 0, B = 0, C = 0, cEvents = 0;
for (const q of qids) {
  const bare = runs.filter((r) => isBare(panels[r].get(q))).length;
  const corr = runs.filter((r) => panels[r].get(q).correct).length;
  if (bare === 0) continue;
  if (corr > 0 && corr < runs.length) A++;
  else if (corr === runs.length) B++;
  else {
    C++;
    cEvents += bare;
  }
}
console.log(`A(certifiable)=${A} B(never-lost)=${B} C(impossible)=${C} bareEventsInC=${cEvents}`);

// --- group histograms for the estimators ---
const hist = new Map();
for (const q of qids) {
  for (const r of runs) {
    const rec = panels[r].get(q);
    if (!rec.decision) continue;
    const key = `${q}|${fp(rec)}`;
    const h = hist.get(key) ?? { bare: 0, ans: 0, corr: 0 };
    if (isBare(rec)) h.bare++;
    else {
      h.ans++;
      if (rec.correct) h.corr++;
    }
    hist.set(key, h);
  }
}

const totalBare = [...hist.values()].reduce((a, h) => a + h.bare, 0);
const mle = [...hist.values()].reduce((a, h) => {
  if (h.bare === 0 || h.ans === 0) return a;
  return a + h.bare * (h.ans / (h.ans + h.bare)) * (h.corr / h.ans);
}, 0);
const laplace = [...hist.values()].reduce((a, h) => {
  if (h.bare === 0) return a;
  const th = (h.ans + 1) / (h.ans + h.bare + 2);
  const pc = h.ans > 0 ? h.corr / h.ans : 0;
  return a + h.bare * th * pc;
}, 0);
const naive = [...hist.values()].reduce((a, h) => {
  if (h.bare === 0 || h.ans === 0) return a;
  return a + h.bare * (h.corr / h.ans);
}, 0);

const NQ = panels[runs[0]].size;
console.log(`total bare events=${totalBare}`);
console.log(`M0 naive pooled = ${((naive / NQ) * 100).toFixed(2)} pp  (INVALID)`);
console.log(`M1 MLE          = ${((mle / NQ) * 100).toFixed(2)} pp  (INVALID, in-sample)`);
console.log(`M2 Laplace      = ${((laplace / NQ) * 100).toFixed(2)} pp  (in-sample)`);

// --- mechanism simulation: 4 fit + 4 held-out, seeded ---
function mulberry32(a) {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const fitRuns = new Set(runs.slice(0, 4));
const evalRuns = new Set(runs.slice(4));
const fit = new Map();
for (const q of qids) {
  for (const r of runs) {
    if (!fitRuns.has(r)) continue;
    const rec = panels[r].get(q);
    if (!rec.decision) continue;
    const key = `${q}|${fp(rec)}`;
    const h = fit.get(key) ?? { bare: 0, correct: 0, wrong: 0 };
    if (isBare(rec)) h.bare++;
    else if (rec.correct) h.correct++;
    else h.wrong++;
    fit.set(key, h);
  }
}
const heldOutBare = [];
for (const q of qids) {
  for (const r of runs) {
    if (!evalRuns.has(r)) continue;
    const rec = panels[r].get(q);
    if (rec.decision && isBare(rec)) heldOutBare.push(`${q}|${fp(rec)}`);
  }
}
const rand = mulberry32(12345);
const gains = [];
for (let it = 0; it < 400; it++) {
  let g = 0;
  for (const key of heldOutBare) {
    const h = fit.get(key);
    if (!h) continue;
    const tot = h.bare + h.correct + h.wrong;
    if (tot === 0) continue;
    const u = rand() * tot;
    if (u >= h.bare && u < h.bare + h.correct) g++;
  }
  gains.push(g);
}
gains.sort((a, b) => a - b);
const mean = gains.reduce((a, b) => a + b, 0) / gains.length;
console.log(
  `SIM (4+4 holdout) per eval run = ${mean.toFixed(2)} recovered ` +
    `= ${((mean / NQ) * 100).toFixed(2)} pp  ` +
    `90% PI [${gains[Math.floor(0.05 * gains.length)]}, ${gains[Math.floor(0.95 * gains.length)]}]`,
);
console.log(`held-out bare events total = ${heldOutBare.length}`);
