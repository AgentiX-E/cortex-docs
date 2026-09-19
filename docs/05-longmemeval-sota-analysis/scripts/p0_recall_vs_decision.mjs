/**
 * Split every failure into RECALL (the labelled evidence never reached the
 * prompt) versus DECISION (the evidence was in the prompt and the model still
 * got it wrong or abstained).
 *
 * The two need opposite fixes and mixing them produces confident nonsense, so
 * the split is done with a mechanical membership test: the retrieved context is
 * rendered with a `[YYYY/MM/DD (Day) HH:MM]` stamp per turn, and the dataset
 * records which sessions carry the answer. If none of an answer session's dates
 * appear in the retrieved string, the session was not retrieved.
 *
 * Caveat, stated because it bounds the result: a date stamp appearing proves only
 * that SOME turn from that date is present, not the answer turn itself. The test
 * is therefore an upper bound on recall and a lower bound on decision failures.
 */

import { readFileSync } from 'node:fs';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const LME = '/tmp/lme-data/lme.json';
const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));

const all = [...load(`${BASE}/MR_diagnostics.json`), ...load(`${BASE}/Single-session_diagnostics.json`)];
const lme = load(LME);
const meta = new Map(lme.map((x) => [x.question_id, x]));

const capOf = (d) => d.capability ?? (String(d.question_id).endsWith("_abs") ? "ABS" : (meta.get(d.question_id)?.question_type === "multi-session" ? "MR" : "?"));

/** id -> date, from the dataset's parallel haystack_session_ids / haystack_dates. */
function sessionDates(inst) {
  const out = new Map();
  const ids = inst.haystack_session_ids ?? [];
  const dates = inst.haystack_dates ?? [];
  for (let i = 0; i < ids.length; i++) out.set(ids[i], dayOf(dates[i]));
  return out;
}

/** The dataset renders a session date as `YYYY/MM/DD (Day) HH:MM`; keep the day. */
function dayOf(s) {
  const m = String(s ?? '').match(/\d{4}\/\d{2}\/\d{2}/);
  return m ? m[0] : null;
}

function dateStamps(text) {
  return new Set((text.match(/\d{4}\/\d{2}\/\d{2}/g) ?? []));
}

/**
 * Strict turn-level membership: does the actual TEXT of an answer turn appear in
 * the retrieved context?
 *
 * The date-stamp test above is only a coarse filter -- a date proves some turn
 * from that day is present, not the answer turn. This one samples fixed-length
 * shingles across each answer turn and asks whether any of them survived into
 * the prompt. Retrieval truncates long turns (marking the cut `[truncated]`), so
 * a single shingle at the head would under-report; sampling across the turn is
 * what makes the test tolerant of a middle truncation while still requiring real
 * content, not just a date.
 */
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

const rows = [];
for (const d of all) {
  const inst = meta.get(d.question_id);
  const ids = d.answer_session_ids ?? inst?.answer_session_ids ?? [];
  const idsAll = inst?.haystack_session_ids ?? [];
  const sessions = inst?.haystack_sessions ?? [];
  const retrieved = String((d.decision ?? {}).retrieved ?? '');
  const present = dateStamps(retrieved);
  const dates = sessionDates(inst ?? {});
  const needed = ids.map((i) => dates.get(i)).filter(Boolean);

  // strict: how many answer SESSIONS have at least one turn whose text is present
  let strict = 0;
  for (const id of ids) {
    const k = idsAll.indexOf(id);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    if (texts.some((t) => t.length > 0 && turnPresent(t, retrieved))) strict++;
  }
  const hit = needed.filter((dt) => present.has(dt));
  rows.push({
    id: d.question_id,
    cap: capOf(d),
    correct: !!d.correct,
    abstained: !!(d.decision ?? {}).abstained,
    gold: String(d.ground_truth ?? ''),
    answer: String((d.decision ?? {}).answer ?? ''),
    needed: needed.length,
    hit: hit.length,
    strict,
    nIds: ids.length,
    covered: needed.length > 0 && hit.length === needed.length,
    partial: hit.length > 0 && hit.length < needed.length,
    none: hit.length === 0,
  });
}

console.log(`records ${rows.length}; with usable answer-session dates: ${rows.filter((r) => r.needed > 0).length}`);

const wrong = rows.filter((r) => !r.correct);
console.log(`\n=== ${wrong.length} failures, split by evidence reachability ===`);
const table = {};
for (const r of wrong) {
  const k = r.needed === 0 ? 'unknown' : r.covered ? 'ALL-EVIDENCE' : r.partial ? 'PARTIAL' : 'NO-EVIDENCE';
  (table[k] ??= []).push(r);
}
for (const k of ['NO-EVIDENCE', 'PARTIAL', 'ALL-EVIDENCE', 'unknown']) {
  const g = table[k] ?? [];
  console.log(`  ${k.padEnd(13)} ${String(g.length).padStart(3)}`);
}

console.log(`\nper capability (failures only)`);
const caps = ['IE', 'MR', 'KU', 'TR', 'ABS'];
console.log('  cap   wrong   no-ev   partial   all-ev');
for (const c of caps) {
  const g = wrong.filter((r) => r.cap === c);
  console.log(
    `  ${c.padEnd(4)}  ${String(g.length).padStart(4)}   ${String(g.filter((r) => r.none).length).padStart(5)}   ${String(g.filter((r) => r.partial).length).padStart(7)}   ${String(g.filter((r) => r.covered).length).padStart(6)}`
  );
}

const trWrong = wrong.filter((r) => r.cap === 'TR');
console.log(`\n=== the ${trWrong.length} TR failures by reachability ===`);
for (const k of ['NO-EVIDENCE', 'PARTIAL', 'ALL-EVIDENCE', 'unknown']) {
  const g = trWrong.filter((r) =>
    k === 'unknown' ? r.needed === 0 : k === 'NO-EVIDENCE' ? r.none : k === 'PARTIAL' ? r.partial : r.covered
  );
  console.log(`\n-- ${k} (${g.length}) --`);
  for (const r of g) {
    console.log(
      `   ${r.id}  abst=${r.abstained ? 'Y' : 'n'}  ev ${r.hit}/${r.needed}  gold="${r.gold.slice(0, 40)}"  got="${r.answer.slice(0, 34)}"`
    );
  }
}

// MR regressions for reference
console.log(`\n=== MR failures by reachability ===`);
const mrWrong = wrong.filter((r) => r.cap === 'MR');
for (const r of mrWrong) {
  const k = r.needed === 0 ? 'unknown' : r.covered ? 'ALL-EVIDENCE' : r.partial ? 'PARTIAL' : 'NO-EVIDENCE';
  console.log(
    `   ${r.id}  ${k.padEnd(13)} abst=${r.abstained ? 'Y' : 'n'}  ev ${r.hit}/${r.needed}  gold="${r.gold.slice(0, 32)}"  got="${r.answer.slice(0, 32)}"`
  );
}

// ------------------------------------------------------------ strict re-split
const strictTable = { NONE: [], SOME: [], ALL: [] };
for (const r of wrong) {
  const k = r.nIds === 0 ? 'ALL' : r.strict === 0 ? 'NONE' : r.strict === r.nIds ? 'ALL' : 'SOME';
  strictTable[k].push(r);
}
console.log(`\n\nSTRICT (turn-text) split of the ${wrong.length} failures`);
for (const k of ['NONE', 'SOME', 'ALL']) {
  console.log(`  ${k.padEnd(5)} ${String(strictTable[k].length).padStart(3)}`);
}
console.log('\n  cap   wrong   none   some    all');
for (const c of caps) {
  const g = wrong.filter((r) => r.cap === c);
  const f = (k) => g.filter((r) => strictTable[k].includes(r)).length;
  console.log(
    `  ${c.padEnd(4)}  ${String(g.length).padStart(4)}   ${String(f('NONE')).padStart(4)}   ${String(f('SOME')).padStart(4)}   ${String(f('ALL')).padStart(4)}`
  );
}
console.log('\n-- TR: no answer text reached the prompt --');
for (const r of strictTable.NONE.filter((r) => r.cap === 'TR')) {
  console.log(
    `   ${r.id}  abst=${r.abstained ? 'Y' : 'n'}  gold="${r.gold.slice(0, 46)}"  got="${r.answer.slice(0, 30)}"`
  );
}
console.log('\n-- TR: partial answer text --');
for (const r of strictTable.SOME.filter((r) => r.cap === 'TR')) {
  console.log(
    `   ${r.id}  ${r.strict}/${r.nIds}  abst=${r.abstained ? 'Y' : 'n'}  gold="${r.gold.slice(0, 40)}"  got="${r.answer.slice(0, 30)}"`
  );
}
