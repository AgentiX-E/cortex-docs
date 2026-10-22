/**
 * Root-cause the two MR regressions in run 34791592602.
 *
 * Both were 8/8 correct across the whole panel and are now wrong. A regression
 * under a LOOSER grader cannot be a grading artifact, so these are unambiguously
 * engine regressions, and they are the only place where the new engine is
 * demonstrably worse than the panel.
 *
 *   d851d5ba  gold "$3,750"  ->  "$8,750"   (delta +$5,000)
 *   6d550036  gold "2"       ->  "3"        (delta +1 item)
 *
 * Hypothesis: the vocabulary bridge (c4ab77b) now retrieves a distractor session
 * that the aggregation ledger sums in. Test it by finding, in the new run's
 * retrieved evidence, the number that closes the gap, and checking whether that
 * number lives in a session the dataset labels as evidence.
 */

import { readFileSync } from 'node:fs';

const NEW = '/workspace/analysis/ab_retry/run_34791592602/mr_diagnostics.json';
const LME = '/tmp/lme-data/lme.json';

const diags = JSON.parse(readFileSync(NEW, 'utf-8'));
const lme = JSON.parse(readFileSync(LME, 'utf-8'));
const byId = new Map(lme.map((x) => [x.question_id, x]));

const targets = ['d851d5ba', '6d550036'];

for (const t of targets) {
  const d = diags.find((x) => x.question_id === t);
  if (!d) {
    console.log(`${t}: not found`);
    continue;
  }
  const inst = byId.get(t) ?? {};
  const answerIds = new Set(d.answer_session_ids ?? inst.answer_session_ids ?? []);
  console.log(`\n${'='.repeat(78)}\n${t}`);
  console.log(`question : ${d.question}`);
  console.log(`gold     : ${d.ground_truth}`);
  console.log(`answer   : ${d.decision?.answer}`);
  console.log(`labelled answer sessions (${answerIds.size}): ${[...answerIds].join(', ')}`);

  // which sessions in the haystack carry the gap-closing number?
  const gapNum = t === 'd851d5ba' ? '5,000' : null;
  const retrieved = String(d.decision?.retrieved ?? '');
  console.log(`retrieved length: ${retrieved.length}`);

  if (gapNum) {
    const idx = [];
    let i = retrieved.indexOf(gapNum);
    while (i !== -1) {
      idx.push(i);
      i = retrieved.indexOf(gapNum, i + 1);
    }
    console.log(`"${gapNum}" occurs ${idx.length} time(s) in retrieved`);
    for (const p of idx.slice(0, 3)) {
      console.log(`  ...${retrieved.slice(Math.max(0, p - 220), p + 120).replace(/\n/g, ' ')}...`);
    }
  }

  // scan every haystack session for the gap number and report membership
  const hay = inst.haystack_sessions ?? inst.haystack ?? [];
  const sessions = Array.isArray(hay) ? hay : [];
  console.log(`haystack sessions: ${sessions.length}`);
  for (const s of sessions) {
    const sid = s.session_id ?? s.id ?? '?';
    const text = Array.isArray(s.turns)
      ? s.turns.map((u) => `${u.role ?? ''}: ${u.content ?? ''}`).join(' ')
      : JSON.stringify(s);
    const has = gapNum ? text.includes(gapNum) : false;
    if (has) {
      console.log(
        `  session ${sid}  labelled=${answerIds.has(sid)}  carries "${gapNum}"  date=${s.date ?? '?'}`
      );
      const p = text.indexOf(gapNum);
      console.log(`     ...${text.slice(Math.max(0, p - 160), p + 100).replace(/\n/g, ' ')}...`);
    }
  }
}
