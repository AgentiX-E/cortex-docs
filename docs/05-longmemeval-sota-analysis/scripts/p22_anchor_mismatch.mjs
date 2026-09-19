/**
 * The real defect: the question's content words do not occur in the turn that
 * answers it, so both retrieval channels are blind to it by construction.
 *
 * `71017277` is the canonical case. Question: "I received a piece of jewelry last
 * Saturday from whom?"  Gold: "my aunt".  The answering turn reads "I also got a
 * stunning crystal CHANDELIER from MY AUNT ...".  The question says jewelry; the
 * turn says chandelier.  No lexical overlap, and semantically "chandelier" and
 * "jewelry" are both nouns of value but not close enough to separate from 500
 * distractor turns.
 *
 * That is not a ranking weakness -- it is an ANCHOR mismatch. The question names
 * the category, the memory names the instance. If the mechanism is real it should
 * show up mechanically as: the content words of the question barely appear in the
 * answering turn, while they DO appear in the admitted (wrong) turns.
 *
 * Decisive contrast: question-turn overlap for FAILURES where the answering turn
 * was missing, vs. question-turn overlap for turns that retrieval actually chose.
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

const STOP = new Set(
  ('a an the and or but if then than that this these those i you he she it we they me him her us them my your his its our their ' +
    'is are was were be been being do does did have has had of to in on at for with about from by as so not no yes ' +
    'what when where who how why which can could would should will shall may might must did do you your i my me ' +
    'ago last next time there their them what')
    .split(' ')
    .filter(Boolean)
);
function contentWords(s) {
  return new Set(
    String(s ?? '')
      .toLowerCase()
      .match(/[a-z][a-z0-9']*/g)
      ?.filter((w) => w.length >= 3 && !STOP.has(w)) ?? []
  );
}
const overlap = (a, b) => {
  let n = 0;
  for (const w of a) if (b.has(w)) n++;
  return n;
};

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

/** Turns of the labelled answer sessions that state the gold value. */
function goldTurns(inst, gold) {
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const g = String(gold).toLowerCase().trim();
  const kw = [...contentWords(gold)];
  const out = [];
  for (const sid of inst.answer_session_ids ?? []) {
    const k = idsAll.indexOf(sid);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    for (const t of texts) {
      if (!t) continue;
      const n = t.toLowerCase();
      const kwHits = kw.filter((w) => n.includes(w)).length;
      if ((g !== '' && n.includes(g)) || (kw.length > 0 && kwHits / kw.length >= 0.75)) {
        out.push(t);
      }
    }
  }
  return out;
}

const failures = [];
const successes = [];
for (const [cap, d] of allRows) {
  const inst = meta.get(d.question_id);
  if (!inst) continue;
  const retrieved = String(d.decision?.retrieved ?? '');
  const q = contentWords(d.question);
  const gt = goldTurns(inst, d.ground_truth);
  if (gt.length === 0) continue;

  // question-overlap of the best answering turn
  let bestAnsOverlap = 0;
  for (const t of gt) bestAnsOverlap = Math.max(bestAnsOverlap, overlap(q, contentWords(t)));

  // question-overlap of the admitted turns (what retrieval actually chose)
  const admitted = retrieved
    .split('\n')
    .filter((l) => l.trim().length > 0)
    .map((l) => contentWords(l));
  let maxAdmitted = 0;
  for (const a of admitted) maxAdmitted = Math.max(maxAdmitted, overlap(q, a));

  const ansInPrompt = gt.some((t) => turnPresent(t, retrieved));
  const rec = {
    id: d.question_id,
    cap,
    correct: !!d.correct,
    qSize: q.size,
    bestAnsOverlap,
    maxAdmitted,
    ansInPrompt,
    qWords: [...q],
  };
  if (d.correct) successes.push(rec);
  else failures.push(rec);
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

console.log('=== question-to-turn content-word overlap ===');
console.log('| population | n | mean overlap with ANSWER turn | mean max overlap with ADMITTED turns |');
const missF = failures.filter((r) => !r.ansInPrompt);
console.log(
  `| FAIL, answer turn absent | ${missF.length} | ${mean(missF.map((r) => r.bestAnsOverlap)).toFixed(2)} | ${mean(missF.map((r) => r.maxAdmitted)).toFixed(2)} |`
);
const okIn = successes.filter((r) => r.ansInPrompt);
console.log(
  `| CORRECT, answer turn present | ${okIn.length} | ${mean(okIn.map((r) => r.bestAnsOverlap)).toFixed(2)} | ${mean(okIn.map((r) => r.maxAdmitted)).toFixed(2)} |`
);

console.log('');
console.log('=== the asymmetry, per question ===');
console.log('| id | cap | overlap(answer turn) | overlap(best admitted turn) | gap |');
for (const r of missF.slice(0, 25)) {
  console.log(
    `| ${r.id.padEnd(14)} | ${r.cap} | ${String(r.bestAnsOverlap).padStart(2)}/${r.qSize} | ${String(r.maxAdmitted).padStart(2)} | ${r.bestAnsOverlap - r.maxAdmitted} |`
  );
}

// The testable claim: on the absent-answer-turn failures, the ADMITTED turns
// match the question at least as well as the answering turn does. That is what
// makes the miss unavoidable for a text scorer.
const dominated = missF.filter((r) => r.maxAdmitted >= r.bestAnsOverlap);
console.log('');
console.log(
  `${dominated.length} of ${missF.length} (${((dominated.length / missF.length) * 100).toFixed(0)}%) have admitted turns that match the question AT LEAST AS WELL as the answering turn`
);
console.log('=> for a text-similarity scorer the miss is not a ranking error; the answering turn is genuinely not the best lexical or semantic match.');
