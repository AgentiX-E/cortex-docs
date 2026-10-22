/**
 * Narrow the "session reached, answering turn missing" population to a concrete,
 * checkable defect before proposing any change.
 *
 * The aggregate (45 of 74 failures) is a symptom. A fix needs a mechanism. The
 * running hypothesis is that the answering turn is not UNIQUE: the same content
 * appears in several turns (a user turn and the assistant's paraphrase, or the
 * user restating it a session later), and retrieval admits the wrong member of
 * that cluster. If so the failure is not "the ranker is imperfect" -- it is that
 * ranking is done on TEXT, and two turns carrying the same fact are only
 * equivalent after normalisation the scorer never sees.
 *
 * This asks the concrete question: for each failure where the answer session was
 * reached but the carrying turn was not, does an ADMITTED turn in the prompt
 * state the same fact in different words? That is checkable by looking for the
 * gold value's co-arguments rather than the gold string itself.
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

// ------------------------------------------------------------------ turn utils

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\s+/g, ' ')
    .trim();

const SHINGLE = 30;
const SAMPLES = 24;
function turnPresent(turnText, retrieved) {
  const t = turnText.replace(/\s+/g, ' ');
  if (t.length < SHINGLE) return retrieved.includes(t);
  const step = Math.max(1, Math.floor((t.length - SHINGLE) / SAMPLES));
  for (let i = 0; i < t.length - SHINGLE; i += step) {
    if (retrieved.includes(t.slice(i, i + SHINGLE))) return true;
  }
  return false;
}

/** Content words of a string, minus stopwords, for overlap comparison. */
const STOP = new Set(
  'a an the and or but if then than that this these those i you he she it we they me him her us them my your his its our their is are was were be been being do does did have has had of to in on at for with about from by as so not no yes what when where who how why which did do can could would should will shall may might must'.split(
    ' '
  )
);
function contentWords(s) {
  return new Set(
    (norm(s).match(/[a-z][a-z0-9']*/g) ?? []).filter((w) => w.length >= 3 && !STOP.has(w))
  );
}

const jaccard = (a, b) => {
  let inter = 0;
  for (const w of a) if (b.has(w)) inter++;
  return inter / (a.size + b.size - inter);
};

// ---------------------------------------------------------------- the analysis

/** Answer turn(s) = turns of an answer session that carry the gold value. */
function answerTurns(inst, gold) {
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const g = norm(gold);
  const kw = [...contentWords(gold)];
  const out = [];
  for (const sid of inst.answer_session_ids ?? []) {
    const k = idsAll.indexOf(sid);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    texts.forEach((t, i) => {
      const n = norm(t);
      const hasValue = g !== '' && n.includes(g);
      const kwHits = kw.filter((w) => n.includes(w)).length;
      // A turn "carries" the answer if it states the gold verbatim, or if the
      // gold is short and most of its content words appear (the model can read
      // the value off it).
      const carries = hasValue || (kw.length > 0 && kwHits / kw.length >= 0.75);
      if (carries && t.length > 0) out.push({ sid, i, text: t, hasValue, kwHits });
    });
  }
  return out;
}

const rows = [];
for (const [cap, d] of allRows) {
  if (d.correct) continue;
  const inst = meta.get(d.question_id);
  if (!inst) continue;
  const retrieved = String(d.decision?.retrieved ?? '');
  const carried = answerTurns(inst, d.ground_truth);
  if (carried.length === 0) continue; // gold not locatable in the dataset turns
  const carriedInPrompt = carried.filter((c) => turnPresent(c.text, retrieved));
  const carriedMissing = carried.filter((c) => !turnPresent(c.text, retrieved));
  if (carriedInPrompt.length > 0) continue; // the value IS in the prompt -> decision failure
  // => every turn that states the answer is absent from the prompt, yet the
  //    session was reached. This is the population to explain.
  const admitted = retrieved.split('\n').filter((l) => l.trim().length > 0);
  rows.push({
    id: d.question_id,
    cap,
    gold: d.ground_truth,
    abstained: !!d.decision?.abstained,
    carriedMissing,
    admittedCount: admitted.length,
    blob: retrieved.length,
  });
}

console.log(`failures where EVERY turn stating the answer is absent from the prompt: ${rows.length}`);
console.log('');

for (const r of rows) {
  const c = r.carriedMissing[0];
  console.log('='.repeat(100));
  console.log(`${r.id}  [${r.cap}]  abstained=${r.abstained}  blob=${r.blob}`);
  console.log(`gold: ${String(r.gold).slice(0, 90)}`);
  console.log(`missing answer turn (${c.text.length} chars), session ${c.sid}, verbatim-gold=${c.hasValue} kwHits=${c.kwHits}:`);
  console.log(`  ${c.text.replace(/\s+/g, ' ').slice(0, 260)}`);
  if (r.carriedMissing.length > 1) {
    console.log(`  (+${r.carriedMissing.length - 1} more turns also state it)`);
  }
}

// Do the MISSING turns have a near-duplicate that IS in the prompt? That would
// prove a cluster/duplication effect rather than a plain ranking miss.
console.log('');
console.log('=== is the missing turn near-duplicated by an admitted turn? ===');
let dup = 0;
const dupExamples = [];
for (const r of rows) {
  const inst = meta.get(r.id);
  const retrieved = String(
    (allRows.find(([, d]) => d.question_id === r.id)?.[1].decision ?? {}).retrieved ?? ''
  );
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const allTurns = [];
  for (let s = 0; s < sessions.length; s++) {
    const turns = sessions[s] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    texts.forEach((t, i) => allTurns.push({ s, i, text: t }));
  }
  const missing = r.carriedMissing[0];
  const mw = contentWords(missing.text);
  let best = 0;
  let bestTurn = null;
  for (const t of allTurns) {
    if (!turnPresent(t.text, retrieved)) continue;
    const j = jaccard(mw, contentWords(t.text));
    if (j > best) {
      best = j;
      bestTurn = t;
    }
  }
  if (best >= 0.5) {
    dup++;
    dupExamples.push({ id: r.id, j: best, turn: bestTurn.text.slice(0, 200) });
  }
}
console.log(`${dup} of ${rows.length} missing answer turns have an admitted near-duplicate (Jaccard>=0.5)`);
for (const e of dupExamples.slice(0, 8)) {
  console.log(`  ${e.id}  J=${e.j.toFixed(2)}  "${e.turn.replace(/\s+/g, ' ').slice(0, 170)}"`);
}
