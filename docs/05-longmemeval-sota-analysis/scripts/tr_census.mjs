/**
 * Emit a per-question census of the TR (temporal-reasoning) capability.
 *
 * The benchmark dumps per-question decisions for every single-session
 * capability, but the TR ablation report only prints aggregates, so the TR
 * errors could never be attributed to a mechanism. This reads the dumped
 * decisions and classifies each question with the SHIPPED
 * `classifyTemporalQuestion` rather than a re-implementation, so the analysis
 * can never drift from the engine it is measuring.
 *
 * Usage: node tr_census.mjs [root] [arm]   -> writes <root>/tr_census_<arm>.json
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { classifyTemporalQuestion } from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';

const ROOT = process.argv[2] ?? '/workspace/analysis/ab_turn';
const ARM = process.argv[3] ?? 'treatment';
const FILE = 'benchmark-single-session-diagnostics.json';

const dir = join(ROOT, ARM);
const runs = readdirSync(dir, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => d.name)
  .sort();

/** question_id -> { question, questionDate, gold, kind, answers: string[] } */
const per = new Map();
for (const run of runs) {
  const p = join(dir, run, FILE);
  let records;
  try {
    records = JSON.parse(readFileSync(p, 'utf8'));
  } catch {
    continue;
  }
  for (const r of records) {
    if (r.capability !== 'TR') continue;
    const dec = r.decision ?? {};
    if (!per.has(r.question_id)) {
      per.set(r.question_id, {
        question_id: r.question_id,
        question: r.question,
        questionDate: r.question_date ?? '',
        gold: r.ground_truth,
        kind: classifyTemporalQuestion(r.question),
        top1Score: dec.top1Score ?? 0,
        abstained: [],
        answers: [],
      });
    }
    const e = per.get(r.question_id);
    e.answers.push(dec.answer === undefined || dec.answer === null ? null : String(dec.answer));
    e.abstained.push(Boolean(dec.abstained));
  }
}

const out = {
  arm: ARM,
  runs,
  questions: [...per.values()],
};
const dest = join(ROOT, `tr_census_${ARM}.json`);
writeFileSync(dest, JSON.stringify(out, null, 2));
console.log(`${dest}: ${out.questions.length} TR questions x ${runs.length} runs`);
