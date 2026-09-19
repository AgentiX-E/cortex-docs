/**
 * Split the "answering turn missing" failures by whether its SESSION contributes
 * anything to the prompt at all. The two need opposite fixes.
 *
 *   REACHED-BUT-PARTIAL  -- some turns of the answer session are in the prompt,
 *       the answering turn is not. The session ranked well; turn selection inside
 *       it did not.
 *   SESSION-NOT-REACHED  -- no turn of the answer session is in the prompt. The
 *       session lost to a competitor, so turn selection was never the problem.
 *
 * An earlier probe (`p21_reconcile_reachability`) reported a single number for
 * "session reached" using `answer_session_ids`, which conflates these: it asked
 * whether ANY answer turn's text was present, so a session contributing one
 * incidental turn counted as reached. Separating them is what decides which
 * component to change.
 *
 * Membership uses a 60-char head fragment rather than the 30-char shingled test,
 * to keep "session contributed something" a low bar and make the split
 * conservative in the direction of REACHED-BUT-PARTIAL.
 */

import { readFileSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const RUN = '/workspace/analysis/ab_retry/run_34915402976';
const LME = '/tmp/lme-data/lme.json';

const allRows = [
  ...load(`${RUN}/MR_diagnostics.json`).map((d) => ['MR', d]),
  ...load(`${RUN}/Single-session_diagnostics.json`).map((d) => [d.capability, d]),
];
const meta = new Map(load(LME).map((x) => [x.question_id, x]));

const norm = (s) => String(s ?? '').replace(/\s+/g, ' ').trim();
const head = (s, n = 60) => norm(s).slice(0, n);

function turnsOf(inst, sid) {
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const k = idsAll.indexOf(sid);
  if (k < 0) return [];
  const turns = sessions[k] ?? [];
  return Array.isArray(turns)
    ? turns.map((u) => String(u?.content ?? ''))
    : Object.values(turns).map((u) => String(u?.content ?? ''));
}

function contentWords(s) {
  return new Set(
    (String(s ?? '').toLowerCase().match(/[a-z][a-z0-9']*/g) ?? []).filter((w) => w.length >= 4)
  );
}

/** Does a turn state the gold value (verbatim, or >=75% of its content words)? */
function carriesGold(turn, gold) {
  const n = turn.toLowerCase();
  const g = String(gold).toLowerCase().trim();
  if (g !== '' && n.includes(g)) return true;
  const kw = [...contentWords(gold)];
  if (kw.length === 0) return false;
  return kw.filter((w) => n.includes(w)).length / kw.length >= 0.75;
}

const rows = [];
for (const [cap, d] of allRows) {
  const inst = meta.get(d.question_id);
  if (!inst) continue;
  const retrieved = norm(d.decision?.retrieved ?? '');
  const answerIds = inst.answer_session_ids ?? [];

  let carriesTurns = 0;
  let sessionTurnsPresent = 0;
  let sessionTurnsTotal = 0;
  let anySessionTouched = false;
  let carriedPresent = false;

  for (const sid of answerIds) {
    const texts = turnsOf(inst, sid);
    let touched = false;
    for (const t of texts) {
      if (!t) continue;
      sessionTurnsTotal++;
      const h = head(t);
      const isPresent = h.length > 0 && retrieved.includes(h);
      if (isPresent) {
        sessionTurnsPresent++;
        touched = true;
      }
      if (carriesGold(t, d.ground_truth)) {
        carriesTurns++;
        if (isPresent) carriedPresent = true;
      }
    }
    if (touched) anySessionTouched = true;
  }
  if (carriesTurns === 0 || sessionTurnsTotal === 0) continue;

  rows.push({
    id: d.question_id,
    cap,
    correct: !!d.correct,
    abstained: !!(d.decision?.abstained),
    anySessionTouched,
    carriedPresent,
    sessionTurnsPresent,
    sessionTurnsTotal,
    carriesTurns,
  });
}

const missing = rows.filter((r) => !r.carriedPresent);
const reachedPartial = missing.filter((r) => r.anySessionTouched);
const notReached = missing.filter((r) => !r.anySessionTouched);

console.log('=== failures whose answering turn is absent from the prompt ===');
console.log(`total: ${missing.length}`);
console.log(`  REACHED-BUT-PARTIAL (session contributed >=1 turn): ${reachedPartial.length}`);
console.log(`  SESSION-NOT-REACHED (session contributed nothing) : ${notReached.length}`);

console.log('');
console.log('| id | cap | session turns in prompt | abstained |');
for (const r of missing) {
  console.log(
    `| ${r.id.padEnd(14)} | ${r.cap.padEnd(3)} | ${r.sessionTurnsPresent}/${r.sessionTurnsTotal} | ${r.abstained} |`
  );
}

console.log('');
console.log('=== per capability ===');
const caps = ['MR', 'TR', 'IE', 'KU', 'ABS'];
console.log('| cap | failures w/ answering turn absent | reached-but-partial | not-reached |');
for (const c of caps) {
  const g = missing.filter((r) => r.cap === c);
  if (g.length === 0) continue;
  console.log(
    `| ${c} | ${g.length} | ${g.filter((r) => r.anySessionTouched).length} | ${g.filter((r) => !r.anySessionTouched).length} |`
  );
}

// Contrast class: on questions that were answered CORRECTLY, how much of the
// answer session made it into the prompt? If correct answers routinely have the
// full session and failures have a fragment, partial admission is the signal.
console.log('');
console.log('=== contrast: fraction of the answer session admitted ===');
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
for (const [label, g] of [
  ['CORRECT', rows.filter((r) => r.correct)],
  ['FAIL, answering turn present', rows.filter((r) => !r.correct && r.carriedPresent)],
  ['FAIL, answering turn absent', missing],
]) {
  console.log(
    `  ${label.padEnd(30)} n=${String(g.length).padStart(3)}  mean session fraction admitted = ${(mean(g.map((r) => r.sessionTurnsPresent / Math.max(1, r.sessionTurnsTotal))) * 100).toFixed(1)}%`
  );
}
