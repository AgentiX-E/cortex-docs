/**
 * The mechanism behind "session reached, turn missing".
 *
 * The previous probe showed the answering turn is often absent while turns from
 * the SAME session are present. Two candidate mechanisms:
 *
 *   (a) CAPACITY -- the prompt is assembled from a fixed budget, so sessions are
 *       admitted partly and the tail is cut. Then the missing fraction should
 *       grow with how much competing material retrieval returned.
 *   (b) RANKING -- turns are selected by relevance, and the answering turn scores
 *       below turn that merely share vocabulary. Then the missing fraction is
 *       independent of budget.
 *
 * These predict different fixes (raise the budget vs. fix the ranking), so the
 * test is to correlate coverage of the ANSWER session against the size of the
 * retrieved blob. If coverage is flat while the blob grows, it is ranking.
 *
 * `[truncated]` appears in 268 of 500 blobs, so truncation is active in this
 * system and can be distinguished from silent omission.
 */

import { readFileSync } from 'node:fs';

const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const RUN = process.env.RUN_DIR ?? "/workspace/analysis/ab_retry/run_34915402976";
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

const rows = [];
for (const [cap, d] of allRows) {
  const inst = meta.get(d.question_id);
  if (!inst) continue;
  const retrieved = String(d.decision?.retrieved ?? '');
  const idsAll = inst.haystack_session_ids ?? [];
  const sessions = inst.haystack_sessions ?? [];
  const answerIds = inst.answer_session_ids ?? [];
  let turnsTotal = 0;
  let turnsPresent = 0;
  for (const sid of answerIds) {
    const k = idsAll.indexOf(sid);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    for (const t of texts) {
      if (t.length === 0) continue;
      turnsTotal++;
      if (turnPresent(t, retrieved)) turnsPresent++;
    }
  }
  if (turnsTotal === 0) continue;
  rows.push({
    id: d.question_id,
    cap,
    correct: !!d.correct,
    blob: retrieved.length,
    turnsTotal,
    turnsPresent,
    coverage: turnsPresent / turnsTotal,
    truncated: retrieved.includes('[truncated]'),
    nSessions: (retrieved.match(/\d{4}\/\d{2}\/\d{2} \(/g) ?? []).length,
  });
}

console.log(`questions analysed: ${rows.length}`);

/** Pearson correlation, so the sign and magnitude are explicit. */
function pearson(xs, ys) {
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let dx = 0;
  let dy = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    dx += (xs[i] - mx) ** 2;
    dy += (ys[i] - my) ** 2;
  }
  return num / Math.sqrt(dx * dy);
}

console.log('');
console.log('=== (a) vs (b): does answer-session turn coverage fall as the blob grows? ===');
for (const c of ['TR', 'IE', 'MR', 'KU']) {
  const g = rows.filter((r) => r.cap === c);
  if (g.length < 5) continue;
  const corr = pearson(g.map((r) => r.blob), g.map((r) => r.coverage));
  const meanCov = g.reduce((a, r) => a + r.coverage, 0) / g.length;
  console.log(
    `  ${c.padEnd(3)} n=${String(g.length).padStart(3)}  mean turn coverage ${(meanCov * 100).toFixed(1)}%  corr(blob, coverage)=${corr.toFixed(3)}`
  );
}

// Bucket by blob size to show the shape rather than a single coefficient.
console.log('');
console.log('=== turn coverage by retrieved-blob size (all capabilities) ===');
const buckets = [
  [0, 6000, '<6k'],
  [6000, 9000, '6-9k'],
  [9000, 12000, '9-12k'],
  [12000, 18000, '12-18k'],
  [18000, Infinity, '>18k'],
];
console.log('| blob | n | mean turn coverage | wrong |');
for (const [lo, hi, label] of buckets) {
  const g = rows.filter((r) => r.blob >= lo && r.blob < hi);
  if (g.length === 0) continue;
  const cov = g.reduce((a, r) => a + r.coverage, 0) / g.length;
  const wrong = g.filter((r) => !r.correct).length;
  console.log(`| ${label} | ${g.length} | ${(cov * 100).toFixed(1)}% | ${wrong} |`);
}

console.log('');
console.log('=== correctness vs answer-session turn coverage ===');
console.log('| coverage of answer session | n | correct | accuracy |');
const covBuckets = [
  [0, 0.0001, '0% (nothing)'],
  [0.0001, 0.5, '1-49%'],
  [0.5, 0.9999, '50-99%'],
  [0.9999, 2, '100% (all)'],
];
for (const [lo, hi, label] of covBuckets) {
  const g = rows.filter((r) => r.coverage >= lo && r.coverage < hi);
  if (g.length === 0) continue;
  const ok = g.filter((r) => r.correct).length;
  console.log(`| ${label} | ${g.length} | ${ok} | ${((ok / g.length) * 100).toFixed(1)}% |`);
}

console.log('');
console.log('=== the killer cell: full coverage but still wrong? ===');
const fullButWrong = rows.filter((r) => r.coverage === 1 && !r.correct);
console.log(`answer session 100% present AND answered wrong: ${fullButWrong.length}`);
console.log(
  `mean blob among them: ${(fullButWrong.reduce((a, r) => a + r.blob, 0) / fullButWrong.length).toFixed(0)} chars`
);
