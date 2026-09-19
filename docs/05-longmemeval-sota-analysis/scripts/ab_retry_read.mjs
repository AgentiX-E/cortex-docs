/**
 * Extract and interpret the abstention-retry ablation reading.
 *
 * The point of this script is to keep the interpretation honest. The ablation
 * emits two very different quantities:
 *
 *   - `retryFires` is DETERMINISTIC. It counts how often the retry actually
 *     re-queried a bare abstention. One run of the dataset gives the same count
 *     as a hundred, so a single run is a complete measurement of it.
 *   - `delta` is NOT. At one run it is a single draw from a distribution whose
 *     model-side noise floor is ~10.7 pp on the MR subset (measured across the
 *     8-run panel in analysis/ab_rrf), against an expected effect of ~1.2 pp.
 *     Reading a gain or a loss from it at R=1 would be reading noise.
 *
 * So this script prints the fire counts as findings and refuses to interpret
 * the delta, rather than reporting both as if they carried equal weight.
 *
 * Usage: node analysis/scripts/ab_retry_read.mjs <dir-containing-benchmark-json>
 */
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.argv[2];
if (!dir) {
  throw new Error('usage: node ab_retry_read.mjs <run-directory>');
}

const reportPath = join(dir, 'benchmark-mr-retry-ablation-report.json');
if (!existsSync(reportPath)) {
  throw new Error(`missing ${reportPath}`);
}
const r = JSON.parse(readFileSync(reportPath, 'utf8'));

const fires = r.retryFires;
const ab = r.ablation;

const pct = (x) => `${(x * 100).toFixed(2)}%`;
const sign = (x) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(2)} pp`;

console.log('=== MR abstention-retry ablation ===');
console.log(`dataset   : ${r.dataset} (${r.questionCount} questions)`);
console.log(`control   : ${r.baseline.name}`);
console.log(`treatment : ${r.feature.name}`);
console.log('');
console.log('--- retry fires (deterministic; one run is a complete measurement) ---');
console.log(`control fires   : ${fires.controlFires}   <- MUST be 0`);
console.log(`treatment fires : ${fires.treatmentFires}`);
console.log(`MR questions    : ${fires.questions}`);
const rate = fires.questions === 0 ? 0 : fires.treatmentFires / fires.questions;
console.log(`fire rate       : ${(rate * 100).toFixed(2)}% of MR questions`);
console.log('');

console.log('--- config disarmament ---');
const controlAcc = ab.baselineAggregate.avg;
const treatAcc = ab.featureAggregate.avg;
console.log(`control accuracy   : ${pct(controlAcc)}`);
console.log(`treatment accuracy : ${pct(treatAcc)}`);
console.log(`delta              : ${sign(ab.delta)}`);
console.log(`McNemar p          : ${ab.mcnemarPValue.toExponential(3)}`);
console.log(
  `discordant         : control-correct/treat-wrong=${ab.discordant.baselineCorrectFeatureIncorrect}` +
    ` control-wrong/treat-correct=${ab.discordant.baselineIncorrectFeatureCorrect}`,
);
console.log('');

console.log('--- verdict ---');
if (fires.controlFires !== 0) {
  console.log('INVALID EXPERIMENT.');
  console.log(
    `The control arm disabled the retry but fired ${fires.controlFires} times, so the flag is`,
  );
  console.log('not reaching the retry and the two arms are not the comparison claimed. Stop here.');
} else if (fires.treatmentFires === 0) {
  console.log('VALID BUT INERT.');
  console.log('Disarmament held (control fired 0), but the treatment never had an opportunity.');
  console.log('The delta below measures nothing: it is the output of a working feature on data it');
  console.log('cannot act on, not evidence the feature fails.');
} else {
  console.log('WIRING CONFIRMED.');
  console.log(`Disarmament held (control 0) and the treatment fired ${fires.treatmentFires} times.`);
  console.log(
    `Opportunity size is ${fires.treatmentFires} of ${fires.questions} MR questions (${(rate * 100).toFixed(2)}%).`,
  );
  console.log('');
  const recoveryCeiling = fires.treatmentFires / fires.questions;
  console.log(`Upper bound on the delta: ${(recoveryCeiling * 100).toFixed(2)} pp, reached only if`);
  console.log('EVERY fired retry recovers a correct answer that the control got wrong.');
  console.log(
    `Observed delta is ${sign(ab.delta)}, i.e. ${(ab.delta / (recoveryCeiling || 1)).toFixed(1)}x the`,
  );
  console.log('opportunity-adjusted ceiling.');
}

// The delta gets its own warning because it is the number a reader is most
// likely to quote out of context, and at R=1 it is entirely a noise draw.
console.log('');
console.log('--- caveat on the delta ---');
console.log('Read the fire count, not the delta.');
console.log('Across the 8-run reference panel, MR accuracy ranged 71.90-81.82% (mean 79.13%,');
console.log('spread 9.92 pp) with an identical configuration -- the model is not reproducible');
console.log('across calls even at temperature 0. The retry is expected to move MR accuracy by');
console.log('~1.2 pp. A single run cannot separate 1.2 pp from a ~10 pp noise floor: the');
console.log('variance dwarfs the effect, so the sign of this delta is not a finding.');
console.log('Paired runs at R=8 would give 97.7% power; R=1 gives 0.4%.');
