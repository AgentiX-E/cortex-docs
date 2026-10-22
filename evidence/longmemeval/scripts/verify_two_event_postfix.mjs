/**
 * Post-fix verification for iteration #145 (TR two-event temporal bug).
 *
 * This script is the bridge between the offline unit tests and the production
 * A/B. It re-runs the SAME fixtures through the NEWLY BUILT `dist/`, so the
 * claim "the fix works" is made against the shipped artifact rather than
 * against the TypeScript source that Vitest transpiles on the fly.
 *
 * Three assertions, all deterministic (no LLM, no network, no sampling):
 *
 *   1. TWO-EVENT FIXTURES  — each of the 5 reconstructed production failures
 *      must now return the GOLD value. Before the fix every one of them
 *      returned the `observed` value (measured to the question date).
 *   2. SINGLE-EVENT REGRESSION GUARD — all 19 single-event relative questions
 *      must return exactly what they returned before the fix (the gold in 18
 *      cases, one known-unrelated failure). `hasSecondEventReference` must
 *      return false for every one of them, which is the mechanism that keeps
 *      them on the question-date path.
 *   3. DETECTION CENSUS — `hasSecondEventReference` must return true for all 6
 *      two-event questions of LongMemEval-S, including the one (baking class)
 *      whose dates could not be reconstructed offline.
 *
 * Usage: node verify_two_event_postfix.mjs
 */
import { computeTemporalAnswer, hasSecondEventReference } from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';
import { TWO_EVENT, SINGLE_EVENT } from './tr_fixtures.mjs';

/** The 6th two-event question. Its `when` clause is a modifier rather than a
 *  second operand, so the dates cannot be reconstructed from answer + gold and
 *  the fixture is excluded from the value assertions. Detection is asserted. */
const UNRECONSTRUCTED = [
  "How many days ago did I attend a baking class at a local culinary school when I made my friend's birthday cake?",
];

let failures = 0;

console.log('=== 1. two-event fixtures: must now return the GOLD ===');
for (const c of TWO_EVENT) {
  const got = computeTemporalAnswer(c.question, 'relative', c.questionDate, c.events);
  const ok = got === c.gold;
  if (!ok) failures += 1;
  console.log(
    `  ${ok ? 'PASS' : 'FAIL'}  ${c.label.padEnd(12)} ` +
      `before=${c.observed.padStart(3)}  gold=${c.gold.padStart(3)}  now=${String(got).padStart(3)}`,
  );
}

console.log('\n=== 2. single-event regression guard: must be unchanged ===');
let regressions = 0;
for (const [question, questionDate, eventDate, gold] of SINGLE_EVENT) {
  const detected = hasSecondEventReference(question);
  const got = computeTemporalAnswer(question, 'relative', questionDate, [
    { name: 'the event', date: eventDate },
  ]);
  if (detected) {
    regressions += 1;
    failures += 1;
    console.log(`  FAIL  MISROUTED: ${question.slice(0, 62)}…`);
    continue;
  }
  const ok = got === gold;
  if (!ok) {
    regressions += 1;
    failures += 1;
  }
  console.log(
    `  ${ok ? 'PASS' : 'FAIL'}  gold=${String(gold).padStart(3)}  now=${String(got).padStart(3)}  ` +
      `whenClause=${detected}  ${question.slice(0, 52)}`,
  );
}
console.log(`  -> ${SINGLE_EVENT.length - regressions}/${SINGLE_EVENT.length} unchanged`);

console.log('\n=== 3. detection census on the full LongMemEval-S two-event population ===');
const allTwoEvent = [...TWO_EVENT.map((c) => c.question), ...UNRECONSTRUCTED];
for (const q of allTwoEvent) {
  const ok = hasSecondEventReference(q);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  detected=${ok}  ${q.slice(0, 70)}`);
}

console.log(
  `\n${failures === 0 ? 'POST-FIX VERIFICATION: ALL PASS' : `POST-FIX VERIFICATION: ${failures} FAILURE(S)`}`,
);
process.exit(failures === 0 ? 0 : 1);
