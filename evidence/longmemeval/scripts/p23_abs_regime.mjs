#!/usr/bin/env node
/**
 * The ABS volume→abstention relation, tested rather than eyeballed.
 *
 * The mechanism script showed a non-monotone-looking pattern (90% / 100% / 50%
 * across length thirds) on n=30, which is too small to read by eye. This script:
 *
 *   1. reports the relation on both runs independently, so a single-run fluke is
 *      visible as a disagreement
 *   2. runs a permutation test on the rank correlation between prompt length and
 *      abstention, because n=30 and normality is not available
 *   3. reports it separately for the four questions that flip, which is the only
 *      sub-population the change actually acted on
 *
 * No network.
 */

import { readFileSync } from 'node:fs';

const AFTER = process.argv[2];
const BEFORE = process.argv[3];

const load = (dir) =>
  JSON.parse(readFileSync(`${dir}/Single-session_diagnostics.json`, 'utf8'))
    .filter((r) => r.capability === 'ABS')
    .map((r) => ({
      id: r.question_id,
      len: String(r.decision?.retrieved ?? '').length,
      abst: r.decision?.abstained === true,
      correct: r.correct === true,
      top1: r.decision?.top1Score,
    }));

const A = load(AFTER);
const B = load(BEFORE);
const byId = (rs) => new Map(rs.map((r) => [r.id, r]));
const aM = byId(A);
const bM = byId(B);

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);

/** Spearman rank correlation with average ranks for ties. */
function spearman(xs, ys) {
  const rank = (v) => {
    const idx = v.map((val, i) => [val, i]).sort((p, q) => p[0] - q[0]);
    const r = new Array(v.length);
    let i = 0;
    while (i < idx.length) {
      let j = i;
      while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
      const avg = (i + j) / 2 + 1;
      for (let k = i; k <= j; k++) r[idx[k][1]] = avg;
      i = j + 1;
    }
    return r;
  };
  const rx = rank(xs);
  const ry = rank(ys);
  const mx = mean(rx);
  const my = mean(ry);
  let num = 0;
  let dx = 0;
  let dy = 0;
  for (let i = 0; i < rx.length; i++) {
    num += (rx[i] - mx) * (ry[i] - my);
    dx += (rx[i] - mx) ** 2;
    dy += (ry[i] - my) ** 2;
  }
  return num / Math.sqrt(dx * dy);
}

/** Two-sided permutation test on the rank correlation. */
function permTest(xs, ys, iters = 20000) {
  const obs = Math.abs(spearman(xs, ys));
  let ge = 0;
  const idx = ys.map((_, i) => i);
  // Deterministic LCG, so the reported p-value is reproducible.
  let seed = 12345;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  for (let it = 0; it < iters; it++) {
    for (let i = idx.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [idx[i], idx[j]] = [idx[j], idx[i]];
    }
    const shuffled = idx.map((i) => ys[i]);
    if (Math.abs(spearman(xs, shuffled)) >= obs - 1e-12) ge++;
  }
  return { obs, p: (ge + 1) / (iters + 1) };
}

function report(name, rows) {
  console.log(`\n=== ${name} (n=${rows.length}) ===`);
  const xs = rows.map((r) => r.len);
  const ys = rows.map((r) => (r.abst ? 1 : 0));
  const { obs, p } = permTest(xs, ys);
  console.log(`  Spearman(length, abstain) = ${spearman(xs, ys).toFixed(4)}   permutation p = ${p.toFixed(4)}`);
  const t = Math.floor(rows.length / 3);
  const sorted = [...rows].sort((x, y) => x.len - y.len);
  for (const [n, g] of [
    ['short', sorted.slice(0, t)],
    ['mid', sorted.slice(t, 2 * t)],
    ['long', sorted.slice(2 * t)],
  ]) {
    console.log(
      `    ${n.padEnd(5)} n=${String(g.length).padStart(2)}  ${g[0].len}..${g[g.length - 1].len}  abstain ${(
        100 * g.filter((x) => x.abst).length / g.length
      ).toFixed(1)}%`,
    );
  }
  // Median split, which is more robust than thirds at n=30.
  const med = sorted[Math.floor(sorted.length / 2)].len;
  const lo = rows.filter((r) => r.len < med);
  const hi = rows.filter((r) => r.len >= med);
  console.log(
    `  median split at ${med}: below n=${lo.length} abstain ${(100 * lo.filter((r) => r.abst).length / lo.length).toFixed(1)}%` +
      `  |  above n=${hi.length} abstain ${(100 * hi.filter((r) => r.abst).length / hi.length).toFixed(1)}%`,
  );
}

report('before run 34915402976', B);
report('after run 35004814319', A);

// ---- the sub-population the change acted on -----------------------------
const flips = A.filter((r) => bM.has(r.id) && bM.get(r.id).abst !== r.abst);
console.log(`\n=== the 6 flips ===`);
console.log(`  mean prompt length: before ${mean(flips.map((r) => bM.get(r.id).len)).toFixed(0)}  after ${mean(flips.map((r) => r.len)).toFixed(0)}`);
const nonFlips = A.filter((r) => bM.has(r.id) && bM.get(r.id).abst === r.abst);
console.log(`  mean prompt length: before ${mean(nonFlips.map((r) => bM.get(r.id).len)).toFixed(0)}  after ${mean(nonFlips.map((r) => r.len)).toFixed(0)}`);

// ---- how many ABS questions are in the high-volume regime? --------------
const THRESH = 40000;
console.log(`\n=== regime split at ${THRESH} chars (after) ===`);
const hi = A.filter((r) => r.len >= THRESH);
const lo = A.filter((r) => r.len < THRESH);
console.log(`  >=${THRESH}: n=${hi.length}  abstain ${(100 * hi.filter((r) => r.abst).length / hi.length).toFixed(1)}%  acc ${(100 * hi.filter((r) => r.correct).length / hi.length).toFixed(1)}%`);
console.log(`  < ${THRESH}: n=${lo.length}  abstain ${(100 * lo.filter((r) => r.abst).length / lo.length).toFixed(1)}%  acc ${(100 * lo.filter((r) => r.correct).length / lo.length).toFixed(1)}%`);
console.log(`\n  before run, same split:`);
const hiB = B.filter((r) => r.len >= THRESH);
const loB = B.filter((r) => r.len < THRESH);
console.log(`  >=${THRESH}: n=${hiB.length}  abstain ${hiB.length ? (100 * hiB.filter((r) => r.abst).length / hiB.length).toFixed(1) : 'n/a'}%`);
console.log(`  < ${THRESH}: n=${loB.length}  abstain ${(100 * loB.filter((r) => r.abst).length / loB.length).toFixed(1)}%`);
