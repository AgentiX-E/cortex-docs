/**
 * RECONCILE the two reachability tests, because they disagree and the
 * disagreement is the finding.
 *
 *   Test A (shingle, p0_recall_vs_decision.mjs): does the TEXT of a labelled
 *          answer session survive into `decision.retrieved`?  -> ALL-EVIDENCE on
 *          32 of 37 TR failures, including 71017277.
 *   Test B (gold value, p20_reask_evidence.mjs): does the GOLD STRING appear? ->
 *          ABSENT on 71017277.
 *
 * Both are correct and they answer different questions. A retrieves the session;
 * B asks whether the answer is expressible from it. When A=true and B=false the
 * retrieval reached the right CLUSTER but missed the turn carrying the value --
 * i.e. the failure is turn-level recall inside a reached session, not a routing
 * failure. That distinction decides the fix, so it is worth separating.
 *
 * Test B is deliberately strict: for short golds like "my aunt" it demands the
 * literal phrase. That is the right standard for a generated answer, so a
 * B-miss is a real inability to answer, not a formatting artefact.
 */

import { readFileSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const RUN = '/workspace/analysis/ab_retry/run_34915402976';
const LME = '/tmp/lme-data/lme.json';

const allRows = [
  ...load(`${RUN}/MR_diagnostics.json`).map((d) => ['MR', d]),
  ...load(`${RUN}/Single-session_diagnostics.json`).map((d) => [d.capability, d]),
];
const lme = load(LME);
const meta = new Map(lme.map((x) => [x.question_id, x]));

const norm = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\s+/g, ' ')
    .trim();

/** Test B: is the gold value literally available to be copied? */
function goldAvailable(blob, gold) {
  const b = norm(blob);
  const g = norm(gold);
  if (g === '') return null;
  if (b.includes(g)) return 'exact';
  const gn = Number(g.replace(/[^0-9.\-]/g, ''));
  if (!Number.isNaN(gn) && g.length <= 6 && /\d/.test(g)) {
    const nums = b.match(/-?\d+(?:\.\d+)?/g) ?? [];
    if (nums.some((n) => Number(n) === gn)) return 'numeric';
  }
  for (let len = Math.min(40, g.length); len >= 12; len--) {
    if (b.includes(g.slice(0, len))) return `prefix${len}`;
  }
  return null;
}

/** Test A: does an answer SESSION's turn text survive? (30-char shingles, sampled) */
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
function sessionsReached(d, inst, retrieved) {
  const ids = inst?.answer_session_ids ?? d.answer_session_ids ?? [];
  const idsAll = inst?.haystack_session_ids ?? [];
  const sessions = inst?.haystack_sessions ?? [];
  let reached = 0;
  for (const id of ids) {
    const k = idsAll.indexOf(id);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    if (texts.some((t) => t.length > 0 && turnPresent(t, retrieved))) reached++;
  }
  return { reached, of: ids.length };
}

const CAPS = ['TR', 'IE', 'MR', 'KU', 'ABS'];
const summary = {};
for (const c of CAPS) summary[c] = { wrong: 0, aMiss: 0, bMiss: 0, bothMiss: 0, bothHit: 0 };

console.log('| id | cap | A:session | B:gold | verdict |');
const verdicts = [];
for (const [cap, d] of allRows) {
  if (d.correct) continue;
  const inst = meta.get(d.question_id);
  const retrieved = String(d.decision?.retrieved ?? '');
  const { reached, of } = sessionsReached(d, inst, retrieved);
  const a = of > 0 && reached === of;
  const b = goldAvailable(retrieved, d.ground_truth) !== null;
  let v;
  if (a && b) v = 'answered-wrong (DECISION)';
  else if (a && !b) v = 'session-reached, value-missing (TURN RECALL)';
  else if (!a && b) v = 'value-verbatim-but-session-incomplete (ODD)';
  else v = 'evidence-absent (SESSION RECALL)';
  if (of === 0) v = 'no-answer-session-metadata';
  verdicts.push({ id: d.question_id, cap, a, b, v, reached, of });

  const s = summary[cap];
  s.wrong++;
  if (!a) s.aMiss++;
  if (!b) s.bMiss++;
  if (!a && !b) s.bothMiss++;
  if (a && b) s.bothHit++;
}

// Only print the TR rows in full -- that is where the mass is.
console.log('--- TR failures in detail ---');
for (const r of verdicts.filter((v) => v.cap === 'TR')) {
  console.log(
    `| ${r.id.padEnd(14)} | TR | ${r.reached}/${r.of}${r.a ? ' ALL' : '    '} | ${r.b ? 'hit ' : 'MISS'} | ${r.v} |`
  );
}

console.log('');
console.log('=== per capability: failure decomposition ===');
console.log('| cap | wrong | A: session not fully reached | B: gold value missing | both missing | both present (pure DECISION) |');
for (const c of CAPS) {
  const s = summary[c];
  console.log(
    `| ${c} | ${s.wrong} | ${s.aMiss} | ${s.bMiss} | ${s.bothMiss} | ${s.bothHit} |`
  );
}

console.log('');
console.log('=== global verdict distribution across all 74 failures ===');
const byVerdict = {};
for (const r of verdicts) byVerdict[r.v] = (byVerdict[r.v] ?? 0) + 1;
for (const [k, v] of Object.entries(byVerdict).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${String(v).padStart(3)}  ${k}`);
}

const tr = verdicts.filter((r) => r.cap === 'TR');
const trTurnRecall = tr.filter((r) => r.a && !r.b).length;
const trDecision = tr.filter((r) => r.a && r.b).length;
const trSessionRecall = tr.filter((r) => !r.a && !r.b).length;
console.log('');
console.log(`TR failures: ${tr.length}`);
console.log(`  session-reached/value-missing (TURN RECALL) : ${trTurnRecall}`);
console.log(`  both-present               (DECISION)       : ${trDecision}`);
console.log(`  evidence-absent            (SESSION RECALL) : ${trSessionRecall}`);
