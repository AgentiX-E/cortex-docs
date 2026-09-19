/**
 * TR gold reachability census.
 *
 * Question this answers: for every temporal-reasoning (TR) question that the
 * benchmark got wrong, is the gold answer *derivable at all* from the dates
 * present in the retrieved context?
 *
 *   - If YES  -> the engine picked the wrong operands. Fix the extraction.
 *   - If NO   -> the evidence was never retrieved. Fixing the engine is futile;
 *                the fix has to be retrieval.
 *
 * Method: every candidate is evaluated by calling the SHIPPED
 * `computeTemporalAnswer` from `dist/`. Units (day/week/month), the
 * two-event-vs-question-date branch, rounding and ordering are therefore the
 * production ones by construction -- nothing is reimplemented here, so this
 * analysis cannot drift from the code it measures.
 *
 * A question counts as REACHABLE when some selection of dates from the
 * retrieved context makes the engine emit the gold value (within a tolerance).
 * That is an upper bound on what any operand-selection improvement could win:
 * it assumes a perfect extractor.
 */
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import {
  classifyTemporalQuestion,
  hasSecondEventReference,
  computeTemporalAnswer,
} from '/workspace/cortex/packages/cortex-eval/dist/temporal-engine.js';

const ROOT = '/workspace/analysis/ab_tr_two_event/treatment';
const RUNS = process.argv[2]
  ? [process.argv[2]]
  : ['run_33897747158', 'run_33897760408', 'run_33897768498', 'run_33902273327'];

/** Leading `YYYY/MM/DD` in a turn prefix such as `[2023/03/04 (Sat) 22:43]`. */
const DATE_RE = /(\d{4})\/(\d{2})\/(\d{2})/g;

function contextDates(retrieved) {
  const out = [];
  for (const m of String(retrieved ?? '').matchAll(DATE_RE)) {
    const d = `${m[1]}/${m[2]}/${m[3]}`;
    if (!out.includes(d)) out.push(d);
  }
  return out;
}

const WORDS = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6,
  seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
  a: 1, an: 1,
};

/**
 * Parse the numeric part of a gold answer. Returns `null` for golds that are
 * not machine-comparable ("before", an entity name, "about a month", ...),
 * which are then SKIPPED and counted rather than silently scored as misses.
 */
function goldNumber(gold) {
  if (gold === null || gold === undefined) return null;
  const s = String(gold).trim().toLowerCase();
  const digits = s.match(/-?\d[\d,]*(\.\d+)?/);
  if (digits) return Math.round(Number(digits[0].replace(/,/g, '')));
  const first = s.split(/[^a-z]+/)[0];
  if (first && first in WORDS) return WORDS[first];
  return null;
}

/** Engine output -> number, or null when the engine abstained / returned text. */
function outputNumber(out) {
  if (out === null || out === undefined) return null;
  const m = String(out).trim().match(/-?\d+/);
  return m ? Number(m[0]) : null;
}

function signature(dates) {
  return createHash('sha1').update(dates.join('|')).digest('hex').slice(0, 12);
}

/**
 * Best |gold - engine| achievable from the context, plus the operand pair that
 * achieves it. Returns `null` when no candidate produced a number.
 */
function bestCandidate(question, kind, questionDate, dates, gold, twoEvent) {
  let best = null;
  const consider = (events) => {
    const raw = computeTemporalAnswer(question, kind, questionDate, events);
    const n = outputNumber(raw);
    if (n === null) return;
    const diff = Math.abs(n - gold);
    if (best === null || diff < best.diff) {
      best = { diff, value: n, raw, operands: events.map((e) => e.date) };
    }
  };
  if (twoEvent) {
    for (let i = 0; i < dates.length; i += 1) {
      for (let j = i + 1; j < dates.length; j += 1) {
        consider([{ name: 'x', date: dates[i] }, { name: 'y', date: dates[j] }]);
      }
    }
  } else {
    for (const d of dates) consider([{ name: 'x', date: d }]);
  }
  return best;
}

/** Records for one question, keyed by the context-date signature. */
const cache = new Map();

function evaluate(rec) {
  const question = rec.question;
  const kind = classifyTemporalQuestion(question);
  const questionDate = rec.question_date;
  const gold = goldNumber(rec.ground_truth);
  const dates = contextDates(rec.decision?.retrieved);
  const twoEvent = kind === 'relative' && hasSecondEventReference(question);
  const key = `${rec.question_id}:${signature(dates)}`;
  if (cache.has(key)) return { ...cache.get(key), question_id: rec.question_id };
  let row = {
    question_id: rec.question_id,
    question,
    kind,
    twoEvent,
    goldRaw: rec.ground_truth,
    gold,
    dateCount: dates.length,
    comparable: gold !== null && kind === 'relative',
    best: null,
  };
  if (row.comparable && dates.length > 0) {
    row.best = bestCandidate(question, kind, questionDate, dates, gold, twoEvent);
  }
  const value = { ...row };
  cache.set(key, value);
  return value;
}

const perRun = [];
for (const run of RUNS) {
  const file = `${ROOT}/${run}/benchmark-single-session-diagnostics.json`;
  if (!existsSync(file)) {
    console.error(`missing ${file}`);
    continue;
  }
  const records = JSON.parse(readFileSync(file, 'utf8')).filter(
    (r) => r.capability === 'TR',
  );
  const rows = records.map(evaluate);
  const comparable = rows.filter((r) => r.comparable && r.best);
  const reach0 = comparable.filter((r) => r.best.diff === 0).length;
  const reach1 = comparable.filter((r) => r.best.diff <= 1).length;
  perRun.push({
    run,
    trQuestions: records.length,
    comparable: comparable.length,
    skipped: rows.filter((r) => !r.comparable).length,
    reachableExact: reach0,
    reachableTol1: reach1,
    unreachable: comparable.length - reach1,
    rows,
  });
}

console.log('=== TR GOLD REACHABILITY (upper bound: assumes a perfect extractor) ===\n');
for (const r of perRun) {
  console.log(
    `${r.run}  TR=${r.trQuestions}  comparable=${r.comparable}  skipped=${r.skipped}  ` +
      `reachable(exact)=${r.reachableExact}  reachable(+-1)=${r.reachableTol1}  ` +
      `UNREACHABLE=${r.unreachable} (${((100 * r.unreachable) / Math.max(1, r.comparable)).toFixed(1)}%)`,
  );
}

// Detailed listing from the last run, worst first.
const detail = perRun[perRun.length - 1];
const rows = detail.rows.filter((r) => r.comparable && r.best);
rows.sort((a, b) => a.best.diff - b.best.diff);
console.log(`\n=== PER-QUESTION (run ${detail.run}) ===`);
console.log('diff  kind     2ev  gold       best  question');
for (const r of rows) {
  console.log(
    `${String(r.best.diff).padStart(4)}  ${r.kind.padEnd(8)} ${r.twoEvent ? ' Y ' : ' . '}  ` +
      `${String(r.goldRaw).slice(0, 9).padEnd(9)} ${String(r.best.value).padStart(5)}  ` +
      `operands=[${r.best.operands.join(' , ')}]  ${r.question.slice(0, 70)}`,
  );
}

const skipped = detail.rows.filter((r) => !r.comparable);
const byKind = {};
for (const r of detail.rows) byKind[r.kind] = (byKind[r.kind] ?? 0) + 1;
console.log(`\n=== KIND BREAKDOWN (${detail.rows.length} TR questions) ===`);
for (const [k, v] of Object.entries(byKind)) console.log(`  ${k.padEnd(12)} ${v}`);
const skipWhy = {};
for (const r of skipped) {
  const why = r.gold === null ? `gold-not-numeric: ${JSON.stringify(r.goldRaw)}` : `kind=${r.kind}`;
  skipWhy[why] = (skipWhy[why] ?? 0) + 1;
}
console.log(`\n=== SKIPPED (${skipped.length}) ===`);
for (const [w, n] of Object.entries(skipWhy).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${String(n).padStart(3)}  ${w.slice(0, 100)}`);
}
