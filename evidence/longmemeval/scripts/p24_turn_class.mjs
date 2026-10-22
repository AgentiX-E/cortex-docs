#!/usr/bin/env node
/**
 * Which turns inside a partially admitted evidence session carry the answer?
 *
 * P23 §5 changed the objective: moving questions from 50-99% coverage to 100% is
 * no longer obviously right, because the conditional accuracy of full coverage
 * FELL when a fix pushed harder questions into it. So the question is no longer
 * *how many* turns of a session are admitted but *which*.
 *
 * This script is the measurement instrument. It takes the MR diagnostics rows
 * (the only ones that carry evidence session content) and, for each question,
 * classifies the admitted turns of its answer session by role and position, then
 * asks which classes separate correct from incorrect.
 *
 * The classes it distinguishes, all derivable without an LLM:
 *   - user vs assistant turns (the answer to a memory question is usually stated
 *     by the user, so admitting an assistant turn may be pure noise)
 *   - distance from the evidence-bearing turn, when the diagnostics identify it
 *   - whether the turn's text overlaps the ground-truth answer
 *
 * Output is a set of conditional accuracies with counts, and a Wilson interval
 * on each, so a difference is only read when the intervals separate.
 *
 * No network. Diagnostics only.
 */

import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const dir = process.argv[2];
if (!dir) {
  console.error('usage: node p24_turn_class.mjs <runDir>');
  process.exit(2);
}

const rows = JSON.parse(readFileSync(`${dir}/MR_diagnostics.json`, 'utf8'));
console.log(`MR rows with evidence content: ${rows.length}`);

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();

const shingles = (s) => {
  const t = norm(s);
  const out = new Set();
  for (let i = 0; i + 5 <= t.length; i++) {
    out.add(createHash('sha1').update(t.slice(i, i + 5)).digest('hex'));
  }
  return out;
};

const overlap = (a, b) => {
  if (a.size === 0) return 0;
  let hit = 0;
  for (const s of a) if (b.has(s)) hit++;
  return hit / a.size;
};

/**
 * How much of a turn came from a reference text.
 *
 * The direction matters and is easy to get backwards. Asking "what fraction of
 * the session is in this turn" is structurally near zero -- a session is ~12,000
 * shingles and a turn is a small slice of it -- so it reports 0 for every turn
 * and looks like a finding. The useful question is the reverse: of the text in
 * THIS TURN, how much appears in the reference.
 */
const coverageOfTurn = (turnShingles, referenceShingles) =>
  overlap(turnShingles, referenceShingles);

/**
 * Thresholds, calibrated against the measured distribution rather than guessed.
 *
 * Over the 121 MR questions the per-turn statistics are:
 *   evidence coverage: p50 0.560, p75 0.710, p90 1.000  (bimodal and clean)
 *   answer   coverage: p50 0.000, p95 0.013, max 0.323  (structurally tiny)
 *
 * The asymmetry is expected: a ground-truth answer is a short phrase, so a
 * verbose turn can never be mostly answer. A 0.25 cut on answer overlap selects
 * 1 turn in 9,028 and measures nothing, so "states the answer" is a substring
 * test on the normalised phrase instead. Evidence coverage uses 0.5, just below
 * the p50, so "evidence-bearing" means "at least half this turn is drawn from the
 * evidence session".
 */
const EVIDENCE_TURN_THRESHOLD = 0.5;

/** True when the expected answer appears verbatim in the turn. */
const statesAnswer = (turnText, expected) => {
  const e = norm(expected);
  if (e === '') return false;
  return norm(turnText).includes(e);
};

/** Wilson score interval, matching the eval package's own method. */
function wilson(successes, n, z = 1.96) {
  if (n === 0) return [NaN, NaN];
  const p = successes / n;
  const d = 1 + (z * z) / n;
  const c = p + (z * z) / (2 * n);
  const m = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [(c - m) / d, (c + m) / d];
}

const prompt = (row) =>
  Array.isArray(row.decision?.retrieved)
    ? row.decision.retrieved.join('\n')
    : String(row.decision?.retrieved ?? '');

/**
 * Split a rendered prompt back into turns.
 *
 * Two renderings are in use and BOTH must be handled, because a pattern that
 * matches only one returns `role: 'unknown'` for every turn of the other and
 * silently measures nothing:
 *   - the single-session path: `[YYYY/MM/DD] user: ...`
 *   - the multi-session path:  `[YYYY/MM/DD (Ddd) HH:MM] user: ...`
 * so the date part is deliberately loose and the weekday/time suffix is allowed.
 */
function turnsOf(text) {
  if (text.includes('"role":"')) {
    const out = [];
    const re = /\{"date":"[^"]*","role":"(user|assistant)","content":"((?:[^"\\]|\\.)*)"/g;
    let m;
    while ((m = re.exec(text)) !== null) out.push({ role: m[1], content: m[2] });
    return out;
  }
  const parts = text.split(/(?=\[\d{4}\/\d{2}\/\d{2})/).filter((t) => t.trim() !== '');
  return parts.map((t) => {
    const m = t.match(/^\[[^\]]*\]\s*(user|assistant):\s*([\s\S]*)$/);
    return m ? { role: m[1], content: m[2] } : { role: 'unknown', content: t };
  });
}

const evidenceText = (row) => {
  const c = row.answer_sessions_content;
  return Array.isArray(c) ? c.join('\n\n') : String(c ?? '');
};

const stats = [];
for (const row of rows) {
  const text = prompt(row);
  const turns = turnsOf(text);
  if (turns.length === 0) continue;
  const ev = shingles(evidenceText(row));
  const expected = row.ground_truth;
  // Per-turn overlap with the evidence session, oriented as "of this turn, how
  // much is drawn from the reference", plus a verbatim test for the answer.
  const per = turns.map((t) => {
    const s = shingles(t.content);
    return {
      role: t.role,
      statesAnswer: statesAnswer(t.content, expected),
      evidenceOverlap: coverageOfTurn(s, ev),
      chars: t.content.length,
    };
  });
  stats.push({
    id: row.question_id,
    correct: row.correct === true,
    n: turns.length,
    userTurns: per.filter((p) => p.role === 'user').length,
    assistantTurns: per.filter((p) => p.role === 'assistant').length,
    unknownTurns: per.filter((p) => p.role === 'unknown').length,
    /** Turns that state the expected answer verbatim. */
    answerBearing: per.filter((p) => p.statesAnswer).length,
    /** Turns at least half drawn from the evidence session. */
    evidenceBearing: per.filter((p) => p.evidenceOverlap >= EVIDENCE_TURN_THRESHOLD).length,
  });
}

/**
 * A turn fragment with no role line. The observed cases are all character-budget
 * truncation artefacts -- `[2023/05/25 (`, `[2023/05/30` -- where the date header
 * itself was cut mid-token. They are real content, so they are classified as
 * their own bucket rather than discarded, but they carry no role and are
 * therefore excluded from the role-based comparisons below.
 */
const UNKNOWN = 'unknown';

console.log(`questions measured: ${stats.length}`);
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);

// A parser that matches nothing yields zero for every role count, which reads as
// a finding about the data rather than a bug in the instrument, so the unparsed
// share is reported unconditionally. A small share is truncation noise; a large
// one means the instrument is broken and the numbers below must not be read.
const unparsed = stats.reduce((a, s) => a + s.unknownTurns, 0);
const totalTurns = stats.reduce((a, s) => a + s.n, 0);
const unparsedShare = unparsed / totalTurns;
console.log(
  `turn parse: ${totalTurns} turns, ${unparsed} without a role line (${(100 * unparsedShare).toFixed(1)}%)`,
);
if (unparsedShare > 0.02) {
  console.error(
    `\nERROR: ${(100 * unparsedShare).toFixed(1)}% of turns did not parse. Above 2% this is a broken` +
      `\nparser, not truncation noise. The role counts below are not trustworthy.`,
  );
  process.exit(1);
}

const ok = stats.filter((s) => s.correct);
const bad = stats.filter((s) => !s.correct);
console.log(`correct ${ok.length}  incorrect ${bad.length}\n`);

console.log('class              correct (mean)   incorrect (mean)');
for (const key of [
  'n',
  'userTurns',
  'assistantTurns',
  'answerBearing',
  'evidenceBearing',
]) {
  console.log(
    `${key.padEnd(18)} ${mean(ok.map((s) => s[key])).toFixed(3).padStart(14)} ${mean(bad.map((s) => s[key])).toFixed(3).padStart(18)}`,
  );
}

// The discriminating test: does admitting at least one turn that carries the
// expected answer predict correctness? This is the sharpest available proxy for
// "the evidence turn was admitted", and it is what "which turns" reduces to.
console.log('\n=== conditional accuracy on answer-bearing admission ===');
for (const [name, pred] of [
  ['has an answer-bearing turn', (s) => s.answerBearing > 0],
  ['has none', (s) => s.answerBearing === 0],
  ['has >=2 answer-bearing', (s) => s.answerBearing >= 2],
]) {
  const g = stats.filter(pred);
  if (g.length === 0) {
    console.log(`  ${name.padEnd(26)} n=   0`);
    continue;
  }
  const c = g.filter((s) => s.correct).length;
  const [lo, hi] = wilson(c, g.length);
  console.log(
    `  ${name.padEnd(26)} n=${String(g.length).padStart(3)}  acc=${((100 * c) / g.length).toFixed(1)}%  ` +
      `95% CI [${(100 * lo).toFixed(1)}, ${(100 * hi).toFixed(1)}]`,
  );
}

// Assistant-share, since assistant turns are the suspected noise class here.
console.log('\n=== conditional accuracy by assistant share of admitted turns ===');
for (const [name, pred] of [
  ['none admitted', (s) => s.assistantTurns === 0],
  ['some (<50%)', (s) => s.assistantTurns > 0 && s.assistantTurns / s.n < 0.5],
  ['majority (>=50%)', (s) => s.assistantTurns / s.n >= 0.5],
]) {
  const g = stats.filter(pred);
  if (g.length === 0) {
    console.log(`  ${name.padEnd(18)} n=   0`);
    continue;
  }
  const c = g.filter((s) => s.correct).length;
  const [lo, hi] = wilson(c, g.length);
  console.log(
    `  ${name.padEnd(18)} n=${String(g.length).padStart(3)}  acc=${((100 * c) / g.length).toFixed(1)}%  ` +
      `95% CI [${(100 * lo).toFixed(1)}, ${(100 * hi).toFixed(1)}]`,
  );
}
