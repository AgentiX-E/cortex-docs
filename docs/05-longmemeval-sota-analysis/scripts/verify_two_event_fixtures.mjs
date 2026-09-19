/**
 * Verify the offline fixtures for iteration #145 against the SHIPPED engine.
 *
 * The two-event `relative` fixtures are reconstructed from production data:
 *   answer = elapsed(A -> questionDate)  =>  A = questionDate - answer
 *   gold   = elapsed(A -> B)             =>  B = A + gold
 * The single-event fixtures are reconstructed from the GOLD (not from the
 * observed answer), because one of them is answered incorrectly for an
 * unrelated reason (event extraction) and must pin the CORRECT behaviour.
 *
 * Every fixture is then run through the real `computeTemporalAnswer` so the
 * numbers written into the unit tests are produced by the code under test, not
 * by hand arithmetic.
 *
 * Usage: node verify_two_event_fixtures.mjs
 */
import { computeTemporalAnswer } from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';
import { TWO_EVENT, SINGLE_EVENT } from './tr_fixtures.mjs';


let failures = 0;

console.log('=== single-event regression fixtures (must reproduce the gold today) ===');
for (const [question, questionDate, eventDate, gold] of SINGLE_EVENT) {
  const got = computeTemporalAnswer(question, 'relative', questionDate, [
    { name: 'the event', date: eventDate },
  ]);
  const ok = got === gold;
  if (!ok) failures++;
  console.log(
    `  ${ok ? 'OK ' : 'FAIL'} gold=${gold.padEnd(3)} got=${String(got).padEnd(4)} ${question.slice(0, 66)}`,
  );
}

console.log('\n=== two-event fixtures (must FAIL before the fix: they reproduce the bug) ===');
for (const c of TWO_EVENT) {
  const got = computeTemporalAnswer(c.question, 'relative', c.questionDate, c.events);
  // Before the fix the engine measures to the question date, so it must return
  // the value observed in production. That is the RED state the tests assert.
  const reproduces = got === c.observed;
  if (!reproduces) failures++;
  console.log(
    `  ${reproduces ? 'OK ' : 'FAIL'} observed=${c.observed.padEnd(3)} got=${String(got).padEnd(4)} ` +
      `gold=${c.gold.padEnd(3)} ${c.label}`,
  );
  // Sanity: the FIRST event must be exactly `observed` away from the question
  // date, which is what makes the reconstruction faithful.
  const firstOnly = computeTemporalAnswer(c.question, 'relative', c.questionDate, [c.events[0]]);
  if (firstOnly !== c.observed) {
    console.log(`       WARN: first event alone gives ${firstOnly}, expected ${c.observed}`);
  }
}

console.log(`\n${failures === 0 ? 'ALL FIXTURES VERIFIED' : `${failures} FIXTURE(S) MISMATCH`}`);
