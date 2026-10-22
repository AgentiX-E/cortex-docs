/**
 * Statistical power of R4's load-bearing prediction (P3) at the cohort size the
 * benchmark can actually deliver.
 *
 * P3: the 6 conjunctive controls all still abstain under decomposition, 6/6.
 * Falsifier: any control flips to answered => decomposition causes collateral
 * damage. So P3 is a one-sided "zero events out of n" bound on the per-question
 * collateral-damage rate p.
 *
 * The exact (Clopper-Pearson) one-sided upper 95% bound on p given 0 events in n
 * trials is 1 - 0.05^(1/n). This is the honest statement of what P3 buys: not
 * "R4 is safe", but "R4's per-question damage rate is below X".
 */
function upperBound0ofN(n) {
  return 1 - Math.pow(0.05, 1 / n);
}

console.log('P3 is a 0-of-n bound. One-sided 95% upper bound on the per-question');
console.log('collateral-damage rate p, given every control still abstains:\n');
console.log('   n | upper bound on p | implied "expected damaged questions" in a 30-ABS set');
for (const n of [1, 3, 6, 10, 15, 29, 30]) {
  const ub = upperBound0ofN(n);
  console.log(
    `${String(n).padStart(4)} | ${(ub * 100).toFixed(1).padStart(15)}% | ${(ub * 30).toFixed(1).padStart(30)}`,
  );
}
console.log('\nRead: at the ORIGINAL limit=60 the arm sees 1/6 controls, so n=1 and the');
console.log('bound is 95% -- i.e. P3 would pass vacuously and prove nothing.');
console.log('At limit=200 the arm sees 6/6, so n=6 and the bound is 39% per question.');

console.log('\n--- What sample size would make P3 informative? ---');
for (const target of [0.5, 0.3, 0.2, 0.1]) {
  const n = Math.ceil(Math.log(0.05) / Math.log(1 - target));
  console.log(`  to bound p below ${(target * 100).toFixed(0)}% you need n >= ${n} controls`);
}
console.log('Only 7 conjunctive ABS questions exist in the WHOLE dataset (6 controls + 1 target),');
console.log('so p < 30% is the tightest bound this cohort can EVER support, at any limit.');

console.log('\n--- P2: the target. Single question, so the claim is binary. ---');
console.log('P2 asserts 6456829e_abs abstains under decomposition. n=1:');
console.log('  - passing costs no statistical power argument, it is a mechanism check;');
console.log('  - failing is unambiguous evidence the mechanism in p27 4.1 is wrong.');
console.log('So P2 is worth running for its FALSIFIER, not for its effect size.');

console.log('\n--- P5: the confound. What does the cohort actually contain? ---');
console.log('P5 needs the conjunctive cohort split by question type, and asks that');
console.log('quantity-type conjunctive questions not degrade. The cohort is 7 questions:');
console.log('  quantity/aggregation-type: 80ec1f4f (count museums), edced276 (days both),');
console.log('                             6456829e (count plants), e5ba910e (total cost) = 4');
console.log('  ordering/other:            gpt4_70e84552, gpt4_c27434e8, gpt4_fe651585 = 3 (all TR)');
console.log('4 quantity vs 3 ordering in a 7-question cohort supports no subgroup');
console.log('comparison: a 1-question move is 25% of the quantity subgroup. P5 is');
console.log('UNEVALUABLE at this cohort size and must be declared so, not glossed.');
