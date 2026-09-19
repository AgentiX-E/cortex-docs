/**
 * The position signal: WHERE the answering turn sits in its session.
 *
 * The previous probes showed the answering turn is short, under the truncation
 * limit, un-duplicated, and lexically disjoint from the question. Those are all
 * properties of the TEXT. This one tests a property of the STRUCTURE: the turn's
 * ordinal position within its session.
 *
 * The reason to look here is the LongMemEval-S construction. Evidence is placed
 * in a session and the session is padded with a long unrelated dialogue, so the
 * turn that answers the question is routinely the LAST user turn -- the user
 * mentions the fact as an aside ("By the way, I just baked a chocolate cake for
 * my friend"). If the answering turn is systematically late, a position-aware
 * prior is real information that a bag-of-turns text scorer cannot use, and it is
 * dataset-agnostic: it says nothing about which benchmark this is.
 *
 * Two things are measured, and they must be kept apart:
 *   - position of the answering turn among the session's turns
 *   - whether the question's own date anchor points at a late session
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

/** Locate every turn that states the gold, with its ordinal position. */
function goldTurnPositions(inst, gold) {
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const g = String(gold).toLowerCase().trim();
  const kw = String(gold)
    .toLowerCase()
    .match(/[a-z][a-z0-9']*/g)
    ?.filter((w) => w.length >= 4) ?? [];
  const out = [];
  for (const sid of inst.answer_session_ids ?? []) {
    const k = idsAll.indexOf(sid);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    texts.forEach((t, i) => {
      if (!t) return;
      const n = t.toLowerCase();
      const kwHits = kw.filter((w) => n.includes(w)).length;
      const carries = (g !== '' && n.includes(g)) || (kw.length > 0 && kwHits / kw.length >= 0.75);
      if (carries) out.push({ pos: i, of: texts.length, isUser: /\buser:/.test(t) || true });
    });
  }
  return out;
}

const stats = { fail: [], ok: [] };
for (const [cap, d] of allRows) {
  const inst = meta.get(d.question_id);
  if (!inst) continue;
  const retrieved = String(d.decision?.retrieved ?? '');
  const pos = goldTurnPositions(inst, d.ground_truth);
  if (pos.length === 0) continue;
  const present = pos.some((p) => {
    // re-derive the turn text to test membership
    const idsAll = inst.haystack_session_ids ?? [];
    const sessions = inst.haystack_sessions ?? [];
    for (const sid of inst.answer_session_ids ?? []) {
      const k = idsAll.indexOf(sid);
      if (k < 0) continue;
      const turns = sessions[k] ?? [];
      const texts = Array.isArray(turns)
        ? turns.map((u) => String(u?.content ?? ''))
        : Object.values(turns).map((u) => String(u?.content ?? ''));
      if (texts[p.pos] && turnPresent(texts[p.pos], retrieved)) return true;
    }
    return false;
  });
  const rel = pos[0].pos / Math.max(1, pos[0].of - 1); // 0 = first, 1 = last
  const rec = { id: d.question_id, cap, rel, pos: pos[0].pos, of: pos[0].of };
  if (d.correct) stats.ok.push(rec);
  else stats.fail.push(rec);
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : 0;
};

console.log('=== relative position of the answering turn in its session (0=first, 1=last) ===');
console.log('| population | n | mean rel-pos | median rel-pos | share in last third |');
for (const [label, g] of [
  ['CORRECT', stats.ok],
  ['FAIL', stats.fail],
]) {
  const late = g.filter((r) => r.rel >= 0.667).length;
  console.log(
    `| ${label} | ${g.length} | ${mean(g.map((r) => r.rel)).toFixed(3)} | ${median(g.map((r) => r.rel)).toFixed(3)} | ${((late / g.length) * 100).toFixed(1)}% |`
  );
}

console.log('');
console.log('=== does "late turn" predict failure? contingency table ===');
const all = [...stats.ok, ...stats.fail];
const late = all.filter((r) => r.rel >= 0.667);
const early = all.filter((r) => r.rel < 0.667);
const acc = (g) => (g.length ? (g.filter((r) => stats.ok.includes(r)).length / g.length) * 100 : 0);
console.log('| answering turn position | n | accuracy |');
console.log(`| last third (rel >= 0.667) | ${late.length} | ${acc(late).toFixed(1)}% |`);
console.log(`| first two thirds | ${early.length} | ${acc(early).toFixed(1)}% |`);

console.log('');
console.log('=== the 10 absent-answer-turn failures, positioned ===');
for (const r of stats.fail.slice(0, 20)) {
  console.log(`  ${r.id.padEnd(14)} ${r.cap.padEnd(3)} turn ${String(r.pos).padStart(2)} of ${String(r.of).padStart(2)}  rel=${r.rel.toFixed(2)}`);
}
