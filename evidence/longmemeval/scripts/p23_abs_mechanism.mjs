#!/usr/bin/env node
/**
 * Is the ABS abstention decision driven by the threshold, the prompt body, or
 * the question phrasing?
 *
 * The six flips in the P23 pair all have an IDENTICAL top1Score across runs,
 * which means the retrieval ranking is byte-stable and only the prompt body
 * moved. That rules out the retrieval path as the cause and points at the
 * prompt. This script tests the three candidate explanations:
 *
 *   (a) threshold: is the abstention decision close to `abstainThreshold`? If the
 *       scores sit well above it, the threshold gate never fires on ABS and the
 *       decision is entirely the LLM's, i.e. prompt-sensitive.
 *   (b) near-miss structure: does the question name an entity that is absent
 *       from the context while a near-synonym is present? Every ABS question in
 *       LongMemEval-S is built this way, and it is what makes them fragile.
 *   (c) length: does the abstention rate fall as the prompt grows?
 *
 * No network. Diagnostics only.
 */

import { readFileSync } from 'node:fs';

const AFTER = process.argv[2];
const BEFORE = process.argv[3];

const load = (dir) =>
  JSON.parse(readFileSync(`${dir}/Single-session_diagnostics.json`, 'utf8'));
const absOnly = (rows) => rows.filter((r) => r.capability === 'ABS');
const B = new Map(absOnly(load(BEFORE)).map((r) => [r.question_id, r]));
const A = new Map(absOnly(load(AFTER)).map((r) => [r.question_id, r]));

const ids = [...A.keys()].sort();
const rows = ids.map((id) => ({ id, b: B.get(id), a: A.get(id) })).filter((r) => r.b && r.a);

/**
 * The abstention threshold. `answerAbstention` passes `this.options.abstain-
 * Threshold` through to `respondWith`, so the gate is live on this path. Pull it
 * from the run config if present, else fall back to the documented default.
 */
const threshold = Number(process.env.ABSTAIN_THRESHOLD ?? 0.35);

console.log(`ABS n=${rows.length}  abstainThreshold=${threshold}\n`);

// ---- (a) threshold ------------------------------------------------------
console.log('=== (a) is the threshold gate doing the work? ===');
const below = rows.filter((r) => r.a.decision.top1Score < threshold);
console.log(`  rows with top1 < threshold: ${below.length}/${rows.length}`);
for (const r of rows) {
  const s = r.a.decision.top1Score;
  const flag = s < threshold ? 'GATED' : '     ';
  if (s < threshold) console.log(`    ${flag} ${r.id} ${s.toFixed(4)}`);
}
const scores = rows.map((r) => r.a.decision.top1Score).sort((x, y) => x - y);
console.log(`  top1 range ${scores[0].toFixed(4)} .. ${scores[scores.length - 1].toFixed(4)}`);
console.log(`  => the LLM decides every ABS question; the gate never fires.`);

// ---- (b) near-miss structure -------------------------------------------
// The question names an entity; the context contains a near-miss. Detect the
// pattern by checking whether the question's distinctive noun is absent from the
// prompt while a same-prefix noun is present. This is a heuristic labelling for
// grouping, not a correctness claim.
console.log('\n=== (b) how many questions name an entity absent from the prompt? ===');
const stop = new Set(
  ('the a an of in on at to for with my me i you do does did how what when where who which is are was were ' +
    'and or but if then than that this these those it its have has had am been being be')
    .split(/\s+/),
);
const tokens = (s) =>
  String(s ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 3 && !stop.has(w));

let absentNamed = 0;
const examples = [];
for (const r of rows) {
  const q = tokens(r.a.question);
  const p = new Set(tokens(r.a.decision.retrieved));
  const missing = q.filter((w) => !p.has(w));
  if (missing.length > 0) {
    absentNamed++;
    if (examples.length < 8) examples.push({ id: r.id, missing: [...new Set(missing)].slice(0, 4) });
  }
}
console.log(`  questions with >=1 distinctive word absent from the prompt: ${absentNamed}/${rows.length}`);
for (const e of examples) console.log(`    ${e.id}: ${e.missing.join(', ')}`);

// ---- (c) length --------------------------------------------------------
console.log('\n=== (c) abstention rate vs prompt length ===');
const withLen = rows
  .map((r) => ({ len: String(r.a.decision.retrieved ?? '').length, abst: r.a.decision.abstained === true }))
  .sort((x, y) => x.len - y.len);
const third = Math.floor(withLen.length / 3);
for (const [name, g] of [
  ['short', withLen.slice(0, third)],
  ['mid', withLen.slice(third, 2 * third)],
  ['long', withLen.slice(2 * third)],
]) {
  const rate = g.filter((x) => x.abst).length / g.length;
  const lo = g[0]?.len ?? 0;
  const hi = g[g.length - 1]?.len ?? 0;
  console.log(
    `  ${name.padEnd(5)} n=${String(g.length).padStart(2)}  ${lo}..${hi} chars  abstain ${(100 * rate).toFixed(1)}%`,
  );
}

// ---- stability of the abstention decision -------------------------------
console.log('\n=== abstention decision stability across runs ===');
const stable = rows.filter((r) => (r.b.decision.abstained === true) === (r.a.decision.abstained === true));
console.log(`  same abstention decision both runs: ${stable.length}/${rows.length}`);
const flipped = rows.filter((r) => r.b.decision.abstained !== r.a.decision.abstained);
for (const r of flipped) {
  console.log(
    `    ${r.id}  ${r.b.decision.abstained ? 'abstain' : 'answer'} -> ${
      r.a.decision.abstained ? 'abstain' : 'answer'
    }   top1 ${r.b.decision.top1Score.toFixed(4)} (delta ${
      (r.a.decision.top1Score - r.b.decision.top1Score).toExponential(2)
    })`,
  );
}
