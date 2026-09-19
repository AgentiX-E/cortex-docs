/**
 * Offline ABSTAIN_THRESHOLD sensitivity audit.
 *
 * Answers the question "what does moving the abstention threshold from 0.5 to
 * X do to the score?" WITHOUT spending a benchmark run, by joining two arrays
 * that are already persisted in the uploaded artifact:
 *
 *   1. `top1Score` per question, from `benchmark-single-session-diagnostics.json`
 *      (the retrieval signal that the threshold is compared against);
 *   2. `correct` per question, from the same file (the exact-match/judge verdict
 *      that the run already paid for).
 *
 * The join is exact for the population where `correct` does NOT depend on the
 * threshold, and the argument for that is structural, not empirical:
 * `judgeScorer` grades `question.expected === null` questions by `answer ===
 * null` alone (metrics.ts:218). An abstention question can therefore only be
 * correct when the answer is null, and a null answer is produced by exactly two
 * paths -- `retrieved === ''` (which does not consult the threshold) and
 * `top1Score < threshold` (which does). So:
 *
 *   - for `_abs` rows, `correct === true`  =>  the threshold admitted the
 *     abstention, and any threshold >= current keeps it correct;
 *   - for `_abs` rows, `correct === false` =>  the threshold cleared the
 *     question and the model answered; a threshold high enough to catch this
 *     row would flip it to correct, so the ceiling is a COUNT, not a delta;
 *   - for non-`_abs` rows the gold is a string, so the true answer requires an
 *     answer and `correct` is almost always threshold-independent; the rows
 *     where raising the threshold abstains away a previously-correct answer are
 *     exactly the rows with `top1Score < X` that are `correct === true`.
 *
 * What this CANNOT measure, and must not pretend to: what the model WOULD have
 * answered on a row it did not abstain on. A raised threshold changes the
 * context the model sees (the abstention path uses its own admission budget),
 * so the counterfactual answer is not recoverable offline. That is the ceiling
 * calculation in `p35-abstain-threshold-identifiability.md`.
 *
 * Usage:
 *   node /workspace/analysis/abstain-threshold-audit.mjs <diagnostics.json>
 */
import { readFileSync } from 'node:fs';

const path = process.argv[2];
if (!path) {
  console.error('usage: node abstain-threshold-audit.mjs <benchmark-single-session-diagnostics.json>');
  process.exit(2);
}

const rows = JSON.parse(readFileSync(path, 'utf8'));
if (!Array.isArray(rows)) {
  console.error(`expected a JSON array, got ${typeof rows}`);
  process.exit(2);
}

const scored = rows
  .filter((r) => r && r.decision && typeof r.decision.top1Score === 'number')
  .map((r) => ({
    id: r.question_id,
    capability: r.capability,
    isAbs: String(r.question_id).endsWith('_abs'),
    score: r.decision.top1Score,
    correct: r.correct === true,
    abstained: r.decision.abstained === true,
    reason: r.decision.reason,
    question: r.question,
  }));

console.log(`rows with a scored decision: ${scored.length} / ${rows.length}`);
console.log(`unscored (no decision trace): ${rows.length - scored.length}`);

const byReason = {};
for (const r of scored) byReason[r.reason] = (byReason[r.reason] ?? 0) + 1;
console.log('decision reasons:', JSON.stringify(byReason));

const scores = scored.map((r) => r.score).sort((a, b) => a - b);
const quantile = (q) => scores[Math.min(scores.length - 1, Math.floor(q * scores.length))];
console.log(
  `top1Score quantiles: p10=${quantile(0.1).toFixed(3)} p25=${quantile(0.25).toFixed(3)} ` +
    `p50=${quantile(0.5).toFixed(3)} p75=${quantile(0.75).toFixed(3)} p90=${quantile(0.9).toFixed(3)} ` +
    `max=${scores[scores.length - 1].toFixed(3)}`,
);

const abs = scored.filter((r) => r.isAbs);
const nonAbs = scored.filter((r) => !r.isAbs);
console.log(
  `\nABS rows: ${abs.length} (correct ${abs.filter((r) => r.correct).length}, ` +
    `abstained ${abs.filter((r) => r.abstained).length})`,
);
console.log(
  `non-ABS rows: ${nonAbs.length} (correct ${nonAbs.filter((r) => r.correct).length}, ` +
    `abstained ${nonAbs.filter((r) => r.abstained).length})`,
);

// A row's verdict under a hypothetical threshold, when that is determinable.
//
// Determined cases:
//   - abstention question already correct  -> stays correct for any t >= current
//   - abstention question not correct      -> becomes correct if t > score
//   - non-abstention question already wrong -> stays wrong (an abstention on a
//     string-gold question is graded false by judgeScorer)
//   - non-abstention question already correct AND would abstain (score < t)
//     -> becomes wrong
// Indeterminate: a non-abstention question whose verdict flips the other way
// because a raised threshold changed the retrieved context. Counted separately.
function project(t) {
  let absGain = 0;
  let nonAbsLoss = 0;
  let nonAbsGainIndeterminate = 0;
  for (const r of abs) {
    if (!r.correct && r.score < t) absGain++;
  }
  for (const r of nonAbs) {
    if (r.correct && r.score < t) nonAbsLoss++;
  }
  for (const r of nonAbs) {
    if (!r.correct && r.score < t) nonAbsGainIndeterminate++;
  }
  return { absGain, nonAbsLoss, nonAbsGainIndeterminate };
}

console.log('\n     t   absGain(+1 each)  nonAbsLoss(-1 each)  net(determined)  indet(nonAbs newly abstaining)');
for (const t of [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0]) {
  const { absGain, nonAbsLoss, nonAbsGainIndeterminate } = project(t);
  console.log(
    `${t.toFixed(2).padStart(6)}   ${String(absGain).padStart(15)}   ` +
      `${String(nonAbsLoss).padStart(17)}   ${String(absGain - nonAbsLoss).padStart(14)}   ` +
      `${String(nonAbsGainIndeterminate).padStart(28)}`,
  );
}

console.log('\nABS rows, sorted by top1Score (score | correct | abstained | reason | id):');
for (const r of [...abs].sort((a, b) => a.score - b.score)) {
  console.log(
    `  ${r.score.toFixed(3).padStart(7)} | ${String(r.correct).padStart(5)} | ` +
      `${String(r.abstained).padStart(5)} | ${r.reason.padEnd(10)} | ${r.id}`,
  );
}

const raising = nonAbs.filter((r) => r.correct && r.score < 1.0);
console.log(
  `\nnon-ABS rows that a threshold of 1.0 would abstain away (currently correct): ${raising.length}`,
);
for (const r of raising) {
  console.log(`  ${r.score.toFixed(3).padStart(7)} | ${r.id} | ${r.question.slice(0, 70)}`);
}
