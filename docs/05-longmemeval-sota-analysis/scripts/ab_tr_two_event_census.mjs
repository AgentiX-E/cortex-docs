/**
 * Census for the TR two-event temporal A/B (iteration #145).
 *
 *   control   = tr-two-event-control (db92e62): `relative` measures to question date
 *   treatment = master              (d793db4): two-event `relative` measures between events
 *
 * Every question of every capability is emitted, not just TR, because the
 * acceptance criteria include guardrails OUTSIDE the affected population.
 *
 * Classification and the two-event predicate both come from the SHIPPED build in
 * `dist/`, so the analysis cannot drift from the engine it measures. The
 * predicate is imported from the TREATMENT build (master); it is new in this
 * iteration and does not exist in the control, but it is pure text matching, so
 * using it to label both arms labels the same questions on both sides.
 *
 * Usage: node ab_tr_two_event_census.mjs [root]
 *        -> writes <root>/census.json
 *
 * `root` is overridable so the script can be smoke-tested against an earlier
 * A/B directory before the current runs finish.
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import {
  classifyTemporalQuestion,
  hasSecondEventReference,
} from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';

const ROOT = process.argv[2] ?? '/workspace/analysis/ab_tr_two_event';

/**
 * Per-question decisions live in two dumps: the single-session one covers
 * IE / TR / KU, and MR has its own. The MR records carry `capability: null`,
 * so the capability is supplied here rather than read from the record.
 *
 * ABS (30 questions) has NO per-question dump, so it is only available at
 * run level from the report and is analysed there.
 */
const SOURCES = [
  { file: 'benchmark-single-session-diagnostics.json', forced: null },
  { file: 'benchmark-mr-diagnostics.json', forced: 'MR' },
];

/** Run-level production metrics, straight from the report. */
function readReport(dir) {
  try {
    const r = JSON.parse(readFileSync(join(dir, 'benchmark-report.json'), 'utf8'));
    const m = r.baseline?.metrics ?? {};
    return {
      accuracy: m.accuracy ?? null,
      abstentionRate: m.abstentionRate ?? null,
      perCapability: m.perCapability ?? {},
    };
  } catch {
    return null;
  }
}

/** arm -> run dirs, sorted so every array below is in a stable order. */
const arms = {};
const reports = { control: [], treatment: [] };
for (const arm of ['control', 'treatment']) {
  arms[arm] = readdirSync(join(ROOT, arm), { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort();
  for (const run of arms[arm]) {
    reports[arm].push(readReport(join(ROOT, arm, run)));
  }
}

/**
 * question_id -> { capability, question, questionDate, gold, kind, twoEvent,
 *                  perArm: { control: [answers], treatment: [answers] }, ... }
 */
const per = new Map();

for (const [arm, runs] of Object.entries(arms)) {
  for (const run of runs) {
    for (const { file, forced } of SOURCES) {
      let records;
      try {
        records = JSON.parse(readFileSync(join(ROOT, arm, run, file), 'utf8'));
      } catch {
        console.warn(`skip ${arm}/${run}: no ${file}`);
        continue;
      }
      for (const r of records) {
        const dec = r.decision ?? {};
        const capability = forced ?? r.capability;
        if (!per.has(r.question_id)) {
          const isTr = capability === 'TR';
          const kind = isTr ? classifyTemporalQuestion(r.question) : null;
          per.set(r.question_id, {
            question_id: r.question_id,
            capability,
            question: r.question,
            questionDate: r.question_date ?? '',
            gold: r.ground_truth,
            kind,
            // A `relative` question that names a second event is the population
            // the fix targets. Every other question is false here, so the rest
            // of the corpus forms the unaffected control population.
            twoEvent: isTr && kind === 'relative' && hasSecondEventReference(r.question),
            answers: { control: [], treatment: [] },
            abstained: { control: [], treatment: [] },
          });
        }
        const e = per.get(r.question_id);
        e.answers[arm].push(dec.answer === undefined || dec.answer === null ? null : String(dec.answer));
        e.abstained[arm].push(Boolean(dec.abstained));
      }
    }
  }
}

const out = {
  root: ROOT,
  runs: arms,
  reports,
  questions: [...per.values()],
};
const dest = join(ROOT, 'census.json');
writeFileSync(dest, JSON.stringify(out, null, 2));

const nTr = out.questions.filter((q) => q.capability === 'TR').length;
const nTwo = out.questions.filter((q) => q.twoEvent).length;
const byCap = {};
for (const q of out.questions) byCap[q.capability] = (byCap[q.capability] ?? 0) + 1;
console.log(`${dest}`);
console.log(`  control runs:   ${arms.control.join(', ')}`);
console.log(`  treatment runs: ${arms.treatment.join(', ')}`);
console.log(`  per-question: ${out.questions.length} total, ${nTr} TR, ${nTwo} two-event relative`);
console.log(`  by capability: ${JSON.stringify(byCap)}  (ABS has no per-question dump)`);
for (const arm of ['control', 'treatment']) {
  const accs = reports[arm].map((r) => (r ? (r.accuracy * 100).toFixed(2) : 'n/a'));
  console.log(`  ${arm} run-level accuracy: ${accs.join(', ')}`);
}
