#!/usr/bin/env node
/**
 * Characterise the "full coverage but still wrong" cell.
 *
 * Coverage here is the P21 definition, deliberately reused so the bands match:
 *
 *   coverage = (# turns of the answer session present in the prompt) / (total
 *               turns of the answer session)
 *
 * It is a TURN-COUNT ratio, not a character or shingle ratio. The distinction
 * matters: the shingle ratio of a session into a 45-turn prompt tops out around
 * 0.48 across all 121 MR questions, so using it would report "no question ever
 * reaches full coverage" and silently contradict the coverage bands in P21/P23.
 * Two different questions, two different metrics; this script uses the one the
 * bands were built on.
 *
 * For each question in the full-coverage band this reports whether the answer is
 * PRESENT in the prompt (a verbatim substring test) and whether the model gave
 * it back. That separates the two explanations the P23 §5 ceiling left open:
 *
 *   - "answer present but buried"  -> the turn is admitted but the model does not
 *     use it, which is a prompt/attention problem
 *   - "answer present but reasoned away" -> the model saw it and reasoned to a
 *     different value, which is an instruction problem
 *
 * No network. Reads the dataset for session boundaries plus the diagnostics.
 */

import { readFileSync } from 'node:fs';

const runDir = process.argv[2];
const dataPath = process.argv[3] ?? '/tmp/lme-data/lme.json';
if (!runDir) {
  console.error('usage: node p24_full_coverage_wrong.mjs <runDir> [dataset.json]');
  process.exit(2);
}

const dsRaw = JSON.parse(readFileSync(dataPath, 'utf8'));
const dsById = new Map(dsRaw.map((r) => [r.question_id, r]));

// The single-session diagnostics carry every capability except MR, and the MR
// rows carry the evidence content. Read both and key by question id.
const rows = [
  ...JSON.parse(readFileSync(`${runDir}/Single-session_diagnostics.json`, 'utf8')),
  ...JSON.parse(readFileSync(`${runDir}/MR_diagnostics.json`, 'utf8')),
];
console.log(`rows: ${rows.length}`);

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();

/** The prompt payload as one string. */
const promptText = (row) =>
  Array.isArray(row.decision?.retrieved)
    ? row.decision.retrieved.join('\n')
    : String(row.decision?.retrieved ?? '');

/**
 * Turn-level coverage of the answer session, matching p21_turn_coverage.mjs.
 *
 * A session turn counts as present when its normalised text appears in the
 * prompt. The first 60 characters are enough to identify a turn and avoid
 * spurious exact matches on very short turns.
 */
function turnCoverage(row) {
  const inst = dsById.get(row.question_id);
  if (!inst) return null;
  const sessions = inst.haystack_sessions ?? [];
  const ids = inst.haystack_session_ids ?? [];
  const answerIds = new Set(inst.answer_session_ids ?? []);
  const prompt = norm(promptText(row));

  // The loader renders a turn as `<text> [date]`, so match on the text prefix.
  let present = 0;
  let total = 0;
  for (let k = 0; k < sessions.length; k++) {
    if (!answerIds.has(ids[k])) continue;
    for (const turn of sessions[k] ?? []) {
      const text = norm(turn.content ?? turn);
      if (text === '') continue;
      total++;
      if (prompt.includes(text.slice(0, 60))) present++;
    }
  }
  if (total === 0) return null;
  return { coverage: present / total, present, total };
}

const measured = [];
for (const row of rows) {
  const c = turnCoverage(row);
  if (!c) continue;
  measured.push({ row, ...c });
}
console.log(`with a computable answer-session coverage: ${measured.length}\n`);

const bands = [
  ['0%', (v) => v === 0],
  ['1-49%', (v) => v > 0 && v < 0.5],
  ['50-99%', (v) => v >= 0.5 && v < 1],
  ['100%', (v) => v >= 1],
];

console.log('| coverage | n | correct | accuracy |');
console.log('|---|---|---|---|');
for (const [name, pred] of bands) {
  const g = measured.filter((m) => pred(m.coverage));
  if (g.length === 0) {
    console.log(`| ${name} | 0 | - | - |`);
    continue;
  }
  const c = g.filter((m) => m.row.correct === true).length;
  console.log(`| ${name} | ${g.length} | ${c} | ${((100 * c) / g.length).toFixed(1)}% |`);
}

// ---- the cell itself -----------------------------------------------------
const fullButWrong = measured.filter((m) => m.coverage >= 1 && m.row.correct !== true);
console.log(`\n=== full coverage AND wrong: ${fullButWrong.length} ===`);

const hasAnswer = (row) => {
  const gt = norm(row.ground_truth);
  if (gt === '') return false;
  return norm(promptText(row)).includes(gt);
};

let present = 0;
let absent = 0;
for (const m of fullButWrong) {
  const inPrompt = hasAnswer(m.row);
  if (inPrompt) present++;
  else absent++;
  const gt = String(m.row.ground_truth ?? '');
  // Long ground truths are paragraph answers; a verbatim test is only meaningful
  // for the short ones, so the length is reported alongside.
  console.log(
    `${inPrompt ? 'PRESENT' : 'ABSENT '}  ${m.row.question_id.padEnd(20)} ` +
      `cov=${m.coverage.toFixed(2)} (${m.present}/${m.total} turns)  promptChars=${promptText(m.row).length}  gtChars=${gt.length}`,
  );
  console.log(`   Q:   ${String(m.row.question).slice(0, 110)}`);
  console.log(`   GT:  ${gt.slice(0, 110)}`);
  console.log(`   ANS: ${String(m.row.decision?.answer ?? '').slice(0, 110)}`);
}

console.log(
  `\nanswer text present in the prompt: ${present}/${fullButWrong.length}` +
    `   absent: ${absent}/${fullButWrong.length}`,
);
console.log(
  '=> present means the evidence was admitted and the model did not use it (attention/volume);' +
    '\n   absent means the verbatim test failed, which for a long ground truth is expected and' +
    '\n   is not evidence of a missing turn.',
);

// Long-vs-short ground truth: the verbatim test is only decisive for short ones.
const short = fullButWrong.filter((m) => String(m.row.ground_truth ?? '').length <= 60);
console.log(`\nof the ${fullButWrong.length}, ${short.length} have a ground truth short enough for the verbatim test to be decisive`);
for (const m of short) {
  console.log(
    `  ${m.row.question_id}  ${hasAnswer(m.row) ? 'PRESENT' : 'ABSENT'}  ` +
      `gt="${String(m.row.ground_truth).slice(0, 40)}"  ans="${String(m.row.decision?.answer ?? '').slice(0, 40)}"`,
  );
}
