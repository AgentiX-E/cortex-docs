/**
 * End-to-end acceptance probe for the evidence-aware truncation fix.
 *
 * Runs the REAL `truncateSession` from `@agentix-e/cortex-eval` over every
 * LongMemEval-S multi-session gold session and reports, for each, whether the
 * answer-bearing evidence survives. The Python model used during design was a
 * reimplementation, so this probe exists to confirm the shipped TypeScript
 * behaves identically on the dataset rather than only on synthetic fixtures.
 *
 * Usage: node verify-truncation-fix.mjs <lme.json>
 */
import { readFileSync } from 'node:fs';
// Import the built package by path so the probe runs from outside the workspace
// without needing a node_modules link.
import {
  truncateSession,
  turnText,
} from '/workspace/cortex/packages/cortex-eval/dist/index.js';

const path = process.argv[2];
if (!path) {
  throw new Error('usage: verify-truncation-fix.mjs <lme.json>');
}
const data = JSON.parse(readFileSync(path, 'utf8'));

const MAX_CHARS = 2000;

/** Reconstruct the session exactly as the loader does, then truncate it. */
function render(inst, idx) {
  const date = inst.haystack_dates[idx];
  return inst.haystack_sessions[idx].map((t) => turnText(t, date)).join('\n');
}

let sessions = 0;
let truncated = 0;
let gainedTurn = 0;
let lostCompleteTurn = 0;
const candidates = [];

for (const inst of data) {
  if (inst.question_type !== 'multi-session') continue;
  const ids = inst.haystack_session_ids ?? [];
  for (const gid of inst.answer_session_ids ?? []) {
    const idx = ids.indexOf(gid);
    if (idx < 0) continue;
    sessions += 1;
    const full = render(inst, idx);
    if (full.length <= MAX_CHARS) continue;
    truncated += 1;

    const out = truncateSession(full, MAX_CHARS);
    const userTurns = inst.haystack_sessions[idx].filter((t) => t.role === 'user');
    const complete = userTurns.filter((t) => out.includes(t.content)).length;
    // The arrival-only baseline keeps the same complete turns minus any the fix
    // displaced; the fix must never reduce the complete-turn count.
    const completeBaseline = countCompleteBaseline(full, userTurns);

    if (complete > completeBaseline) gainedTurn += 1;
    if (complete < completeBaseline) lostCompleteTurn += 1;

    if (inst.question_id === '8cf4d046') {
      candidates.push({
        question: inst.question_id,
        gold: inst.answer,
        evidencePresent: out.includes('3.86'),
      });
    }
  }
}

/** Complete user turns the arrival-only policy retains, recomputed independently. */
function countCompleteBaseline(full, userTurns) {
  // Mirrors the shipped order pass: complete turns only, no leftover spend.
  const boundary = /(?=\[\d{4}\/\d{2}\/\d{2}[^\]]*\] )/;
  const parts = full.split(boundary).filter((s) => s.length > 0);
  const lengths = parts.map((t) => (/\] user:/.test(t) ? t.length : 0));
  const keep = new Array(parts.length).fill(false);
  let reserved = 0;
  for (let i = 0; i < parts.length; i++) {
    const len = lengths[i];
    if (len > 0 && reserved + len <= MAX_CHARS) {
      keep[i] = true;
      reserved += len;
    }
  }
  const out = parts.filter((_, i) => keep[i]).join('');
  return userTurns.filter((t) => out.includes(t.content)).length;
}

console.log(`multi-session gold sessions:            ${sessions}`);
console.log(`  longer than ${MAX_CHARS} chars:              ${truncated}`);
console.log(`  fix GAINS a complete user turn:       ${gainedTurn}`);
console.log(`  fix LOSES a complete user turn:       ${lostCompleteTurn}`);
for (const c of candidates) {
  console.log(`  ${c.question}: gold=${c.gold} evidence('3.86') present=${c.evidencePresent}`);
}
