/**
 * Paired comparison of the graded run BEFORE and AFTER the P32/P33 fixes.
 *
 * `run_35162802298` (limit=60, 379 diagnostic rows) predates the P32
 * `formatOrdering` sequence fix and the P33 `before`-qualifier fix.
 * `run35405919424` (limit=200, 171 diagnostic rows) carries both.
 *
 * The two samples differ in size, so the only honest comparison is the
 * INTERSECTION of question ids: those 171 questions were asked of both systems
 * under a deterministic pipeline, so a per-question flip is attributable to the
 * code between them and not to sampling. Questions present in only one run are
 * excluded rather than approximated.
 *
 * The feature system is graded in both files, and the join key is `question_id`,
 * so no alignment by index is needed.
 */
import { readFileSync } from 'node:fs';

const OLD = '/workspace/analysis/ab_admission/run_35162802298_run/Single-session_diagnostics.json';
const NEW = '/workspace/run35405919424/longmemeval-s-report/benchmark-single-session-diagnostics.json';

const load = (p) => JSON.parse(readFileSync(p, 'utf8'));
const oldRows = load(OLD);
const newRows = load(NEW);

const oi = new Map(oldRows.map((r) => [r.question_id, r]));
const ni = new Map(newRows.map((r) => [r.question_id, r]));
const ids = [...oi.keys()].filter((id) => ni.has(id)).sort();

console.log(`old=${oldRows.length} new=${newRows.length} intersection=${ids.length}\n`);

function mcnemar(b, c) {
  const n = b + c;
  if (n === 0) return 1;
  let tail = 0;
  const k = Math.min(b, c);
  for (let i = 0; i <= k; i++) {
    let cN = 1;
    for (let j = 0; j < i; j++) cN = (cN * (n - j)) / (j + 1);
    tail += cN * Math.pow(0.5, n);
  }
  return Math.min(1, 2 * tail);
}

const byCap = new Map();
for (const id of ids) {
  const o = oi.get(id);
  const n = ni.get(id);
  const cap = n.capability;
  if (!byCap.has(cap)) byCap.set(cap, []);
  byCap.get(cap).push({ id, o, n });
}

console.log('=== paired change, by capability (intersection only) ===');
console.log('cap  | n  | old acc | new acc | old✓new✗ | old✗new✓ | McNemar p');
let tb = 0;
let tc = 0;
for (const [cap, rows] of [...byCap.entries()].sort()) {
  const oldOk = rows.filter((r) => r.o.correct).length;
  const newOk = rows.filter((r) => r.n.correct).length;
  const b = rows.filter((r) => r.o.correct && !r.n.correct).length;
  const c = rows.filter((r) => !r.o.correct && r.n.correct).length;
  tb += b;
  tc += c;
  console.log(
    `${cap.padEnd(4)} | ${String(rows.length).padStart(2)} | ` +
      `${(oldOk / rows.length * 100).toFixed(1).padStart(7)}% | ` +
      `${(newOk / rows.length * 100).toFixed(1).padStart(7)}% | ` +
      `${String(b).padStart(8)} | ${String(c).padStart(8)} | ${mcnemar(b, c).toExponential(3)}`,
  );
}
console.log(
  `\noverall: ${ids.length} questions, old✓new✗=${tb}, old✗new✓=${tc}, McNemar p=${mcnemar(tb, tc).toExponential(3)}`,
);

console.log('\n=== questions that went WRONG after the fixes (regressions) ===');
for (const [, rows] of byCap) {
  for (const r of rows) {
    if (r.o.correct && !r.n.correct) {
      console.log(`  [${r.n.capability}] ${r.id} | ${r.n.question.slice(0, 66)}`);
    }
  }
}

console.log('\n=== questions that went RIGHT after the fixes (fixes) ===');
for (const [, rows] of byCap) {
  for (const r of rows) {
    if (!r.o.correct && r.n.correct) {
      console.log(`  [${r.n.capability}] ${r.id} | ${r.n.question.slice(0, 66)}`);
    }
  }
}
