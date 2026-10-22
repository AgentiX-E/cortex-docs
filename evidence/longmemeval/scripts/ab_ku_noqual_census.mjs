/**
 * KU no-qualifier A/B census: per-question abstention and correctness, split by
 * the time qualifier the production classifier assigns.
 *
 * PRIMARY ENDPOINT (mechanism)
 *   KU abstention rate on questions classified `other`.
 *   Baseline 14.89%. This is denoised by construction: it counts a decision the
 *   prompt directly controls, not an accuracy outcome that also depends on
 *   retrieval and on the judge.
 *
 * CO-PRIMARY
 *   KU accuracy. Baseline 53.0/72 = 73.6%.
 *
 * WHY OVERALL ACCURACY IS NOT THE PRIMARY
 *   Expected movement is ~7 recovered abstentions per run out of 500, i.e.
 *   ~+0.7pp even at a 50% recovery rate. The between-window drift measured for
 *   byte-identical code is ~1.7-2.1pp, so overall accuracy cannot resolve this
 *   change. It is reported as a noise-floored descriptive estimate with a
 *   Wilson 95% interval, never as the decision variable.
 *
 * GUARDS
 *   IE / MR / TR / ABS must be structurally unchanged: `buildKnowledgeUpdatePrompt`
 *   is reachable only from `answerKnowledgeUpdate`, which `benchmark.ts` calls
 *   only when `questionType === 'knowledge-update'`.
 *
 * The classifier is imported from the BUILT `fact-store.js` so the split cannot
 * drift from production.
 */
import { readFileSync, existsSync } from 'node:fs';
import { classifyKnowledgeUpdateQualifier } from '/workspace/cortex/packages/cortex-eval/dist/fact-store.js';

const ROOT = process.argv[2] ?? '/workspace/analysis/ab_ku_noqual';
const ARMS = ['control', 'treatment'];
const RUNS = process.argv[3]
  ? [process.argv[3]]
  : JSON.parse(
      readFileSync(`${ROOT}/run_index.json`, 'utf8'),
    );

function loadArm(arm) {
  const out = [];
  for (const run of RUNS) {
    const dir = `${ROOT}/${arm}/${run}`;
    if (!existsSync(dir)) continue;
    const single = JSON.parse(readFileSync(`${dir}/benchmark-single-session-diagnostics.json`, 'utf8'));
    const mr = JSON.parse(readFileSync(`${dir}/benchmark-mr-diagnostics.json`, 'utf8')).map((r) => ({
      ...r,
      capability: 'MR',
    }));
    const report = JSON.parse(readFileSync(`${dir}/benchmark-report.json`, 'utf8'));
    out.push({ run, records: [...single, ...mr], report });
  }
  return out;
}

/** Wilson score interval, 95%. */
function wilson(k, n) {
  if (n === 0) return [0, 0];
  const z = 1.959964;
  const p = k / n;
  const d = 1 + (z * z) / n;
  const c = p + (z * z) / (2 * n);
  const s = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [(c - s) / d, (c + s) / d];
}

const summary = {};

for (const arm of ARMS) {
  const runs = loadArm(arm);
  if (runs.length === 0) continue;
  const agg = {};
  let overallK = 0;
  let overallN = 0;
  const perRun = [];
  for (const { run, records, report } of runs) {
    const stats = {};
    for (const r of records) {
      const cap = r.capability ?? '?';
      const s = (stats[cap] ??= { total: 0, abstained: 0 });
      s.total += 1;
      if (r.decision?.abstained === true) s.abstained += 1;
      if (cap === 'KU') {
        const q = classifyKnowledgeUpdateQualifier(r.question);
        const t = (stats[`KU:${q}`] ??= { total: 0, abstained: 0 });
        t.total += 1;
        if (r.decision?.abstained === true) t.abstained += 1;
      }
    }
    const feature = report.feature?.metrics;
    if (feature) {
      overallK += feature.correct;
      overallN += feature.total;
    }
    perRun.push({ run, stats, overall: feature ? feature.correct : null });
  }
  summary[arm] = { runs: perRun, agg, overallK, overallN, n: runs.length };
}

console.log('=== KU NO-QUALIFIER A/B ===\n');
for (const arm of ARMS) {
  const s = summary[arm];
  if (!s) continue;
  console.log(`--- ${arm} (${s.n} runs) ---`);
  // Pooled per-qualifier KU abstention.
  const pooled = {};
  for (const pr of s.runs) {
    for (const [k, v] of Object.entries(pr.stats)) {
      const t = (pooled[k] ??= { total: 0, abstained: 0 });
      t.total += v.total;
      t.abstained += v.abstained;
    }
  }
  for (const k of ['KU:previous', 'KU:current', 'KU:other', 'IE', 'MR', 'TR', 'ABS']) {
    const v = pooled[k];
    if (!v) continue;
    const [lo, hi] = wilson(v.abstained, v.total);
    console.log(
      `  ${k.padEnd(12)} abstained ${String(v.abstained).padStart(4)}/${String(v.total).padStart(4)}` +
        `  rate ${((100 * v.abstained) / v.total).toFixed(2).padStart(6)}%` +
        `  [${(100 * lo).toFixed(2)}, ${(100 * hi).toFixed(2)}]`,
    );
  }
  const [olo, ohi] = wilson(s.overallK, s.overallN);
  console.log(
    `  OVERALL       correct  ${s.overallK}/${s.overallN}  acc ${((100 * s.overallK) / s.overallN).toFixed(2)}%` +
      `  [${(100 * olo).toFixed(2)}, ${(100 * ohi).toFixed(2)}]`,
  );
  console.log(
    '  per-run overall: ' + s.runs.map((r) => r.overall).join(', ') +
      '   per-run KU:other abstained: ' +
      s.runs.map((r) => `${r.stats['KU:other']?.abstained ?? 0}/${r.stats['KU:other']?.total ?? 0}`).join(', '),
  );
  console.log('');
}

if (summary.control && summary.treatment) {
  const get = (arm) => {
    const pooled = {};
    for (const pr of summary[arm].runs) {
      for (const [k, v] of Object.entries(pr.stats)) {
        const t = (pooled[k] ??= { total: 0, abstained: 0 });
        t.total += v.total;
        t.abstained += v.abstained;
      }
    }
    return pooled;
  };
  const c = get('control');
  const t = get('treatment');
  console.log('=== DELTA (treatment - control), pooled ===');
  for (const k of ['KU:previous', 'KU:current', 'KU:other', 'IE', 'MR', 'TR', 'ABS']) {
    if (!c[k] || !t[k]) continue;
    const rc = c[k].abstained / c[k].total;
    const rt = t[k].abstained / t[k].total;
    console.log(
      `  ${k.padEnd(12)} ${(100 * rc).toFixed(2).padStart(6)}% -> ${(100 * rt).toFixed(2).padStart(6)}%` +
        `  delta ${(100 * (rt - rc)).toFixed(2).padStart(7)}pp`,
    );
  }
  const accC = summary.control.overallK / summary.control.overallN;
  const accT = summary.treatment.overallK / summary.treatment.overallN;
  console.log(
    `  OVERALL acc   ${(100 * accC).toFixed(2)}% -> ${(100 * accT).toFixed(2)}%` +
      `  delta ${(100 * (accT - accC)).toFixed(2)}pp`,
  );
}
