/**
 * Small, dependency-free statistics used by every POC.
 *
 * ## Why this file exists
 *
 * The design documents make claims of the form "a scan costs 10-20 ms" and "the rule layer
 * false-shares at most X%". A claim like that needs an estimator with a stated method, not a
 * printed average: an average hides the tail, and a count of zero failures is not a rate of
 * zero. Every number quoted in docs/12-15 is produced here or by a function beside it.
 */

/** Sorted copy, for percentile work that must not mutate the caller's array. */
export function sorted(values) {
  return [...values].sort((a, b) => a - b);
}

/** Nearest-rank percentile. `p` in [0, 1]; `p=0.5` is the median. */
export function percentile(values, p) {
  if (values.length === 0) throw new Error('percentile of an empty sample');
  const ordered = sorted(values);
  const rank = Math.ceil(p * ordered.length) - 1;
  return ordered[Math.max(0, Math.min(ordered.length - 1, rank))];
}

/** Mean and sample standard deviation (n-1). */
export function describe(values) {
  const n = values.length;
  const mean = values.reduce((sum, value) => sum + value, 0) / n;
  const variance =
    n < 2 ? 0 : values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (n - 1);
  return { n, mean, sd: Math.sqrt(variance), min: Math.min(...values), max: Math.max(...values) };
}

/**
 * Upper bound of the Wilson score interval for a binomial proportion.
 *
 * ## Why an upper bound and not the observed rate
 *
 * The rule layer's job is to *not* send private facts to the shared store. Observing zero
 * false-shares in 120 labelled facts is not a false-share rate of zero; it is evidence that
 * the rate is below some number, and a design that promises "never" on the strength of a
 * zero count is promising something the sample cannot support. The Wilson upper bound at
 * 95% is the number a reviewer can check: with 0 of 120 it is 3.1%, with 1 of 120 it is 5.6%.
 */
export function wilsonUpper(successes, n, z = 1.959_963_984_540_054) {
  if (n === 0) return 1;
  const p = successes / n;
  const denominator = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return Math.min(1, (centre + margin) / denominator);
}

/** Two-sided 95% interval for a proportion, as [lower, upper]. */
export function wilsonInterval(successes, n) {
  if (n === 0) return [0, 1];
  const p = successes / n;
  const z = 1.959_963_984_540_054;
  const denominator = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [Math.max(0, (centre - margin) / denominator), Math.min(1, (centre + margin) / denominator)];
}

/** Format a byte count the way the docs quote it. */
export function bytes(value) {
  const units = ['B', 'KiB', 'MiB', 'GiB'];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(amount >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/** Markdown table from rows of objects, with the columns named in order. */
export function table(rows, columns) {
  const header = `| ${columns.join(' | ')} |`;
  const rule = `| ${columns.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${columns.map((name) => row[name] ?? '').join(' | ')} |`);
  return [header, rule, ...body].join('\n');
}
