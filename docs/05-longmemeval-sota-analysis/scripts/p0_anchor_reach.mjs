/**
 * Does enabling `extendedTimeRange` actually reach the failing TR questions?
 *
 * The main benchmark's baseline and feature arms never set
 * `temporalEngineOptions`, so they run on DEFAULT_ENGINE_OPTIONS
 * (`extendedTimeRange: false`). Under that configuration `resolveTimeRange`
 * returns null for every weekday-anchored question ("last Saturday") because the
 * weekday path is gated on the flag, and it widens every numeric offset by a flat
 * +/- 7 days. EXTENDED_ENGINE_OPTIONS exists but is only wired into the
 * `tr-extended-engine` ablation arm.
 *
 * That ablation measured +0.79 pp (one question), so the promotion is not
 * obviously worth doing. This script measures it a second, cheaper way: for each
 * relative-time-anchored TR question, resolve the window under both option sets
 * and ask whether the window CONTAINS the date of a session the dataset labels as
 * carrying the answer. A window that does not contain the evidence cannot help
 * the model find it, whatever the prompt does with the window afterwards.
 *
 * This is a necessary-condition test, not a sufficiency one: a window that
 * contains the evidence is not guaranteed to fix the question, but a window that
 * misses it cannot.
 */

import { readFileSync } from 'node:fs';
import {
  resolveTimeRange,
  EXTENDED_ENGINE_OPTIONS,
  classifyTemporalQuestion,
} from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const all = [...load(`${BASE}/MR_diagnostics.json`), ...load(`${BASE}/Single-session_diagnostics.json`)];
const tr = all.filter((d) => d.capability === 'TR');
const lme = load('/tmp/lme-data/lme.json');
const meta = new Map(lme.map((x) => [x.question_id, x]));

const RELATIVE =
  /\b(last|past|previous|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month|year|weekend)\b|\b(\d+|a\s+few|a\s+couple|several|two|three|four|five|six)\s+(day|days|week|weeks|month|months|year|years)\s+ago\b|\byesterday\b|\ba\s+couple\s+of\s+days\b/i;

const rel = tr.filter((d) => RELATIVE.test(d.question ?? ''));
const dayOf = (s) => (String(s ?? '').match(/\d{4}\/\d{2}\/\d{2}/) ?? [])[0] ?? null;

console.log(`relative-anchored TR questions: ${rel.length}\n`);
console.log(
  'id             kind         qDate       goldSessionDates                              DEFAULT window                EXTENDED window               hits'
);

let defHit = 0;
let extHit = 0;
let wrongDefHit = 0;
let wrongExtHit = 0;
const rows = [];

for (const d of rel) {
  const inst = meta.get(d.question_id);
  const qDate = dayOf(d.question_date ?? inst?.question_date ?? '');
  const ids = inst?.answer_session_ids ?? [];
  const idsAll = inst?.haystack_session_ids ?? [];
  const dates = inst?.haystack_dates ?? [];
  const goldDates = [...new Set(ids.map((i) => dayOf(dates[idsAll.indexOf(i)] ?? '')).filter(Boolean))];
  const def = qDate ? resolveTimeRange(d.question, qDate) : null;
  const ext = qDate ? resolveTimeRange(d.question, qDate, EXTENDED_ENGINE_OPTIONS) : null;
  const inWin = (w) =>
    w !== null && goldDates.some((g) => g >= w.start && g <= w.end);
  const dh = inWin(def);
  const eh = inWin(ext);
  if (dh) defHit++;
  if (eh) extHit++;
  if (!d.correct) {
    if (dh) wrongDefHit++;
    if (eh) wrongExtHit++;
  }
  rows.push({ d, qDate, goldDates, def, ext, dh, eh });
  const kind = classifyTemporalQuestion(d.question ?? '');
  console.log(
    `${d.question_id.padEnd(14)} ${kind.padEnd(12)} ${String(qDate).padEnd(11)} ${goldDates.join(',').padEnd(45).slice(0, 45)} ${(def ? `${def.start}..${def.end}` : 'null').padEnd(30)} ${(ext ? `${ext.start}..${ext.end}` : 'null').padEnd(30)} ${d.correct ? 'ok  ' : 'FAIL'} ${dh ? 'D' : '-'}${eh ? 'E' : '-'}`
  );
}

const wrong = rel.filter((d) => !d.correct);
console.log(`\nall relative-anchored  : ${rel.length}  DEFAULT hits ${defHit}  EXTENDED hits ${extHit}`);
console.log(
  `of the ${wrong.length} FAILING ones: DEFAULT window contains evidence ${wrongDefHit}, EXTENDED ${wrongExtHit}`
);
console.log(
  `\nquestions where EXTENDED reaches the evidence but DEFAULT does not: ${rows.filter((r) => r.eh && !r.dh).length}`
);
for (const r of rows.filter((r) => r.eh && !r.dh)) {
  console.log(`   ${r.d.question_id}  correct=${r.d.correct}  ext=${r.ext.start}..${r.ext.end}  gold=${r.goldDates.join(',')}`);
}
console.log(
  `\nquestions where NEITHER reaches the evidence: ${rows.filter((r) => !r.eh && !r.dh).length}`
);
for (const r of rows.filter((r) => !r.eh && !r.dh)) {
  console.log(
    `   ${r.d.question_id}  correct=${r.d.correct}  q=${String(r.d.question).slice(0, 62)}  ext=${r.ext ? `${r.ext.start}..${r.ext.end}` : 'null'}  gold=${r.goldDates.join(',')}`
  );
}
