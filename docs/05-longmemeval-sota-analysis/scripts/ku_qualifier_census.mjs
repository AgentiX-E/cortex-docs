/**
 * Knowledge-update (KU) abstention census, split by the time qualifier the
 * production classifier assigns.
 *
 * Hypothesis under test: `buildKnowledgeUpdatePrompt` commits the model to a
 * two-step contract whose Step 2 has a branch for "previous", a branch for
 * "current" and a branch for "still/same/Yes-No", but NO branch for a question
 * that carries no time qualifier at all. Those questions are classified
 * `'other'` by `classifyKnowledgeUpdateQualifier`, which also makes them skip
 * the bitemporal path in `answerKnowledgeUpdate`, so they reach the incomplete
 * Step 2 with no escape hatch except the abstain token.
 *
 * If that is right, the abstention rate for `'other'` should be markedly higher
 * than for `'previous'`/`'current'`.
 *
 * The classifier is imported from the BUILT `fact-store.js`, never
 * reimplemented, so the split cannot drift from production.
 */
import { readFileSync } from 'node:fs';
import { classifyKnowledgeUpdateQualifier } from '/workspace/cortex/packages/cortex-eval/dist/fact-store.js';

const ROOT = '/workspace/analysis/ab_tr_two_event/treatment';
const RUNS = ['run_33897747158', 'run_33897760408', 'run_33897768498', 'run_33902273327'];

const aggregate = {};
const perRun = [];

for (const run of RUNS) {
  const records = JSON.parse(
    readFileSync(`${ROOT}/${run}/benchmark-single-session-diagnostics.json`, 'utf8'),
  ).filter((r) => r.capability === 'KU');
  const stats = {};
  for (const r of records) {
    const q = classifyKnowledgeUpdateQualifier(r.question);
    const s = (stats[q] ??= { total: 0, abstained: 0, abstainedWithGold: 0 });
    s.total += 1;
    if (r.decision?.abstained === true) {
      s.abstained += 1;
      const gold = String(r.ground_truth ?? '').trim();
      if (gold !== '') {
        const toks = gold.split(/[^A-Za-z0-9]+/).filter(Boolean);
        const re =
          toks.length > 0
            ? new RegExp(toks.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[^A-Za-z0-9]{0,4}'), 'i')
            : null;
        if (re && re.test(String(r.decision.retrieved ?? ''))) s.abstainedWithGold += 1;
      }
    }
  }
  perRun.push({ run, stats });
  for (const [q, s] of Object.entries(stats)) {
    const a = (aggregate[q] ??= { total: 0, abstained: 0, abstainedWithGold: 0 });
    a.total += s.total;
    a.abstained += s.abstained;
    a.abstainedWithGold += s.abstainedWithGold;
  }
}

console.log('=== KU ABSTENTION BY TIME QUALIFIER (4 runs pooled) ===');
console.log('qualifier    N(run-avg)  abstained/run  abst-rate   of which gold-in-context');
for (const q of ['previous', 'current', 'other']) {
  const a = aggregate[q];
  if (!a) continue;
  const n = a.total / RUNS.length;
  const ab = a.abstained / RUNS.length;
  console.log(
    `${q.padEnd(11)}  ${n.toFixed(1).padStart(6)}     ${ab.toFixed(2).padStart(8)}     ` +
      `${((100 * a.abstained) / a.total).toFixed(2).padStart(6)}%    ${(a.abstainedWithGold / RUNS.length).toFixed(1)}/${ab.toFixed(1)}`,
  );
}

console.log('\n=== PER RUN ===');
for (const { run, stats } of perRun) {
  console.log(
    run,
    Object.entries(stats)
      .sort()
      .map(([q, s]) => `${q}: ${s.abstained}/${s.total}`)
      .join('  '),
  );
}

// Two-proportion check: is 'other' different from the pooled previous/current?
const o = aggregate.other ?? { total: 0, abstained: 0 };
const p = {
  total: (aggregate.previous?.total ?? 0) + (aggregate.current?.total ?? 0),
  abstained: (aggregate.previous?.abstained ?? 0) + (aggregate.current?.abstained ?? 0),
};
const p1 = o.abstained / o.total;
const p2 = p.abstained / p.total;
const pooled = (o.abstained + p.abstained) / (o.total + p.total);
const se = Math.sqrt(pooled * (1 - pooled) * (1 / o.total + 1 / p.total));
const z = (p1 - p2) / se;
console.log(
  `\nother: ${o.abstained}/${o.total} = ${(100 * p1).toFixed(2)}%   ` +
    `previous+current: ${p.abstained}/${p.total} = ${(100 * p2).toFixed(2)}%   z = ${z.toFixed(3)}`,
);
