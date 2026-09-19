/**
 * Why did a re-ask that repairs 10 of 11 MR abstentions repair 0 of 22 here?
 *
 * The retry's premise is that a bare abstention is a *skip* — the model had the
 * evidence and declined to spend the tokens — so re-asking converts it. That
 * premise came from MR. If it fails to transfer, the re-ask output should look
 * qualitatively different from the first pass: either byte-identical (a
 * deterministic decline) or a differently-worded decline (a stable judgement).
 *
 * This prints, for every fired question, the first-pass raw and the re-ask raw
 * side by side plus a coarse structural verdict. Reading the text is the point:
 * a summary statistic cannot tell a skip from a judgement.
 */

import { readFileSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const DIR = '/workspace/analysis/ab_retry/run_34915402976';
const all = [...load(`${DIR}/MR_diagnostics.json`), ...load(`${DIR}/Single-session_diagnostics.json`)];
const capOf = (d) => d.capability ?? 'MR';

const fired = all.filter((d) => (d.decision ?? {}).retryFired === true);
console.log(`fired on ${fired.length} questions`);

// What did the retry actually store? If there is no second-pass text at all the
// instrumentation is the problem, not the model.
console.log('decision keys present:', Object.keys(fired[0]?.decision ?? {}).join(', '));
console.log('');

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();

let identical = 0;
let declined = 0;
for (const d of fired) {
  const dec = d.decision ?? {};
  const first = String(dec.llmRaw ?? '');
  // There is no separate second-pass field: the retry writes its answer back into
  // `llmRaw`, so the diagnostics keep only the winning response. That is enough
  // for this probe -- the point is whether the FINAL text is a bare decline -- but
  // it does mean the first-pass text is not recoverable from the artifact, so no
  // "did the re-ask change the wording" comparison is possible here.
  const second = String(dec.retryRaw ?? '');
  const same = second !== '' && norm(first) === norm(second);
  if (same) identical++;
  if (dec.abstained) declined++;
  console.log('='.repeat(96));
  console.log(`${d.question_id}  [${capOf(d)}]  correct=${d.correct}  abstained=${dec.abstained}`);
  console.log(`Q   : ${String(d.question).slice(0, 150)}`);
  console.log(`gold: ${String(d.ground_truth).slice(0, 90)}`);
  console.log(`-- llmRaw (${first.length} chars) --`);
  console.log(first.slice(0, 600));
  if (second !== '') {
    console.log(`-- retryRaw (${second.length} chars) --`);
    console.log(second.slice(0, 600));
  }
}
console.log('');
console.log(`identical re-ask text: ${identical}/${fired.length}`);
console.log(`abstained after re-ask: ${declined}/${fired.length}`);
