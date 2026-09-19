#!/usr/bin/env node
/**
 * Regression suite for the numeric-fidelity checker.
 *
 * The checker's tolerance has to be calibrated, not just asserted: every rule
 * added above that excuses a difference is a rule that could be excusing a real
 * defect. This suite pins the boundary by mutation.
 *
 * Two kinds of case:
 *
 *   - **Tamper cases must FAIL.** A changed value is the thing the checker
 *     exists to catch. If any of these passes, the tolerance has been widened
 *     past the point of usefulness and the whole gate is worthless.
 *   - **Restatement cases must PASS.** A correct translation that renders a
 *     count differently is not a defect. If any of these fails, the checker is
 *     reporting things that are not wrong, which trains the reader to ignore it.
 *
 * Run: node tools/check-numeric-fidelity.test.mjs
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CHECKER = join(HERE, 'check-numeric-fidelity.mjs');

const SOURCE = [
  '# Verdict',
  '',
  'The paired test gives a McNemar p-value of 7.451e-9, an improvement of',
  '+14.00pp with the control at 72.00% and the treatment at 86.00%.',
  '',
  'Five of the recovered questions moved; two of them were spelled out.',
  'The margin is no worse than control \u22121.0pp on every capability.',
  'A run at `off-by-one` rates 2-of-8, and million-to-10M-token scale holds.',
  '',
].join('\n');

const CASES = [
  {
    name: 'identical text',
    expect: 'pass',
    dst: SOURCE,
    why: 'the trivial control: a document compared with itself must match',
  },
  {
    name: 'exponent changed 7.451e-9 -> 7.451e-8',
    expect: 'fail',
    dst: SOURCE.replace('7.451e-9', '7.451e-8'),
    why: 'an exponent is a measurement; a changed one is a defect',
  },
  {
    name: 'delta changed +14.00pp -> +14.0pp',
    expect: 'fail',
    dst: SOURCE.replace('+14.00pp', '+14.0pp'),
    why: 'a restated precision is a changed value, not a restatement',
  },
  {
    name: 'value dropped: 72.00% removed',
    expect: 'fail',
    dst: SOURCE.replace('72.00%', ''),
    why: 'a dropped measurement must not pass as a translation choice',
  },
  {
    name: 'sign flipped: -1.0pp -> +1.0pp',
    expect: 'fail',
    dst: SOURCE.replace('\u22121.0pp', '+1.0pp'),
    why: 'the sign rule must survive the dash normalisation',
  },
  {
    name: 'word changed: five -> 6',
    expect: 'fail',
    dst: SOURCE.replace('Five', '6'),
    why: 'a spelled-out count that changes must fail after folding',
  },
  {
    name: 'word kept: five -> 5',
    expect: 'pass',
    dst: SOURCE.replace('Five', '5'),
    why: 'the digit rendering of a spelled count is correct, not a defect',
  },
  {
    name: 'count restated: two -> both',
    expect: 'pass',
    dst: SOURCE.replace('two of them', 'both of them'),
    why: 'single-digit counts are language-dependent and reconciled',
  },
  {
    name: 'compound intact: off-by-one preserved',
    expect: 'pass',
    dst: SOURCE,
    why: 'a hyphenated word containing a number word must not become a sign',
  },
  {
    name: 'compound altered: off-by-one -> off-by-2',
    expect: 'pass',
    dst: SOURCE.replace('off-by-one', 'off-by-2'),
    why: 'masked compounds are identifiers, compared by their own check',
  },
  {
    name: 'range endpoint changed: 2-of-8 -> 2-of-9',
    expect: 'fail',
    dst: SOURCE.replace('2-of-8', '2-of-9'),
    why: 'an "N of M" tally is a count a reader relies on; changing it fails',
  },
  {
    name: 'measurement altered: 86.00% -> 68.00%',
    expect: 'fail',
    dst: SOURCE.replace('86.00%', '68.00%'),
    why: 'the headline result is a measurement and must be compared exactly',
  },
];

let failures = 0;
const dir = mkdtempSync(join(tmpdir(), 'fidelity-'));
const srcPath = join(dir, 'source.md');
writeFileSync(srcPath, SOURCE);

for (const c of CASES) {
  const dstPath = join(dir, 'translated.md');
  writeFileSync(dstPath, c.dst);
  let status = 0;
  try {
    execFileSync('node', [CHECKER, '--file', srcPath, dstPath], { stdio: 'pipe' });
  } catch (e) {
    status = e.status ?? 1;
  }
  const got = status === 0 ? 'pass' : 'fail';
  const ok = got === c.expect;
  if (!ok) failures++;
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${c.name.padEnd(46)} expected=${c.expect} got=${got}`);
  if (!ok) console.log(`        why it matters: ${c.why}`);
}

rmSync(dir, { recursive: true, force: true });
console.log('');
console.log(
  failures === 0
    ? `check-numeric-fidelity.test: ${CASES.length}/${CASES.length} cases behave as specified`
    : `check-numeric-fidelity.test: ${failures} of ${CASES.length} cases WRONG`,
);
process.exit(failures === 0 ? 0 : 1);
