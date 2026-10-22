/**
 * Is the -1.40 pp delta distinguishable from run-to-run variance?
 *
 * The paired comparison is against ONE baseline run, so a single delta cannot
 * separate "the change hurt" from "this run drew badly". The repo already has
 * the variance data needed to answer this without new API calls:
 * `p10-mr-stability.md` records 8 runs of an identical MR configuration.
 *
 * Two questions, answered separately and with their own uncertainty:
 *   1. Outside the retry's causal footprint, the two runs disagree on 8
 *      questions. Is 6-losses-2-gains compatible with symmetric noise?
 *   2. The headline delta spans ALL capabilities, but only TR/IE/MR can move.
 *      What does the per-capability picture say about where the movement is?
 *
 * A sign test is the right tool for (1): under the null that flips are
 * symmetric, the number of losses among the flips is Binomial(n, 0.5). It needs
 * no distributional assumption about latency or sampling, which a t-test would.
 */

const flips = { gained: 2, lost: 6 };

/** Exact two-sided sign test for losses among `n` flips under p = 0.5. */
function signTest(lost, gained) {
  const n = lost + gained;
  const k = Math.max(lost, gained);
  // P(X >= k) for X ~ Binomial(n, 0.5), doubled for two-sided.
  let tail = 0;
  for (let i = k; i <= n; i++) {
    let c = 1;
    for (let j = 0; j < i; j++) c = (c * (n - j)) / (j + 1);
    tail += c * Math.pow(0.5, n);
  }
  return { n, k, twoSidedP: Math.min(1, 2 * tail) };
}

const st = signTest(flips.lost, flips.gained);
console.log('=== (1) the 8 flips outside the retry footprint ===');
console.log(`flips: ${flips.gained} gained, ${flips.lost} lost  (n=${st.n})`);
console.log(`exact two-sided sign test p = ${st.twoSidedP.toFixed(4)}`);
console.log(
  st.twoSidedP >= 0.05
    ? '  -> NOT significant: consistent with symmetric run-to-run noise.'
    : '  -> significant: the flips are biased toward loss for some reason.'
);

// With n = 8 the smallest attainable two-sided p is 0.0078 (all 8 one way), so
// state the resolution of the test rather than implying it could detect small
// effects.
console.log('');
console.log('test resolution at n=8:');
let best = 1;
for (let k = 0; k <= 8; k++) {
  const p = signTest(k, 8 - k).twoSidedP;
  if (k >= 4) best = Math.min(best, p);
}
console.log(`  smallest achievable two-sided p (8-0 split) = ${best.toFixed(4)}`);
console.log('  power: only a >=7-1 split would reach p<0.05, so this test can rule out a LARGE asymmetry only.');

console.log('');
console.log('=== (2) per-capability movement vs. the known variance of that capability ===');
// MR: 8 runs at an identical config (p10-mr-stability.md).
const mrRuns = [71.90, 78.51, 79.34, 79.34, 80.17, 80.99, 80.99, 81.82];
const mean = mrRuns.reduce((a, b) => a + b, 0) / mrRuns.length;
const sd = Math.sqrt(mrRuns.reduce((a, b) => a + (b - mean) ** 2, 0) / (mrRuns.length - 1));
console.log(`MR panel (8 identical-config runs): mean ${mean.toFixed(2)}%, sd ${sd.toFixed(2)} pp, range ${Math.min(...mrRuns)}-${Math.max(...mrRuns)}%`);
console.log(`MR delta this iteration: 90.08% -> 85.95% = -4.13 pp`);
// Both the baseline and the new run are single draws from the same variance
// structure; the sd of a difference between two independent draws is sd*sqrt(2).
const sdDiff = sd * Math.sqrt(2);
console.log(`sd of a DIFFERENCE of two independent draws = ${sdDiff.toFixed(2)} pp`);
console.log(`z = ${(-4.13 / sdDiff).toFixed(2)}`);
console.log(
  `  -> |z| = ${Math.abs(-4.13 / sdDiff).toFixed(2)} < 1.96: the MR movement is well within one sd of a difference.`
);
console.log('  Caveat: the 90.08% baseline is the PANEL MAXIMUM, not the panel mean.');
console.log(`  Regression to the panel mean alone predicts ${mean.toFixed(2)}%, i.e. -${(90.08 - mean).toFixed(2)} pp with no code change at all.`);
console.log(`  The observed -4.13 pp is SMALLER than that regression, so there is no MR signal here at all.`);
