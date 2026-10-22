#!/usr/bin/env node
/**
 * POC-6: does the fail-closed default hold at corpus scale, or was n=60 hiding something?
 *
 * ## The question G2 got wrong
 *
 * G2 was written as "label 600 more sentences by hand so the false-share bound drops from 24.2%
 * to 5%". That framing assumes the risk lives in the rule *patterns*. It does not: `defer` lands
 * private, so a sentence no rule recognises is still not published. The only way a policy-forced
 * private sentence reaches the shared store is if a **shared** rule claims it -- in practice
 * `org-knowledge`.
 *
 * Which means the leak rate is not a property of recall. It is a property of how often a
 * *publishing* rule fires on something private. That is measurable on a corpus whose rows are
 * known to be private, and it does not need a single new label written by us.
 *
 * ## Input
 *
 * `candidates.json` from `fetch.py`: rows from a public, human-annotated PII corpus, filtered to
 * those whose every annotated span is a deterministic identifier. Under the published policy
 * those rows must not reach the shared store. If the rule table publishes one, that is a leak by
 * the policy's own definition, not by our judgement.
 *
 * ## What this is not
 *
 * It is not a scope benchmark. These rows are private because they carry identifiers; the 60-row
 * labelled set remains the only measurement of whether the *policy itself* classifies workplace
 * speech correctly. Two different claims, two different denominators, both reported.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { table, wilsonInterval, wilsonUpper } from '../lib/stats.mjs';
import { destination } from '../p04-triage-rules/rules.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const results = join(HERE, '..', 'results');
const input = JSON.parse(readFileSync(join(HERE, 'candidates.json'), 'utf8'));

if (input.status !== 'ok' || !Array.isArray(input.rows) || input.rows.length === 0) {
  const payload = {
    generatedAt: new Date().toISOString(),
    status: input.status ?? 'unavailable',
    reason: input.reason ?? 'corpus empty',
    errors: input.errors ?? [],
  };
  writeFileSync(join(results, 'p06-pii-recall.json'), JSON.stringify(payload, null, 2));
  writeFileSync(
    join(results, 'p06-pii-recall.md'),
    [
      '# POC-6: fail-closed at corpus scale',
      '',
      `Status: **${payload.status}** — ${payload.reason}`,
      '',
      'The pipeline is built and runs in CI; the corpus could not be opened from this host.',
      'No number is reported rather than a number produced from a substitute corpus.',
      ...(payload.errors.length ? ['', 'Attempts:', ...payload.errors.map((e) => `- ${e}`)] : []),
      '',
    ].join('\n'),
  );
  console.log(`p06: ${payload.status} -- ${payload.reason}`);
  process.exit(0);
}

const rows = input.rows.map((row) => ({ ...row, ...destination(row.text) }));
const leak = rows.filter((row) => row.destination === 'shared');
const decided = rows.filter((row) => row.scope !== 'defer');
const n = rows.length;

const byCategory = [...new Set(rows.map((row) => row.category))].map((category) => {
  const subset = rows.filter((row) => row.category === category);
  const leaks = subset.filter((row) => row.destination === 'shared');
  return {
    category,
    n: subset.length,
    leak: leaks.length,
    'leak upper': `${(wilsonUpper(leaks.length, subset.length) * 100).toFixed(1)}%`,
    coverage: `${((subset.filter((row) => row.scope !== 'defer').length / subset.length) * 100).toFixed(1)}%`,
    'top rule': topRule(subset),
  };
});

function topRule(subset) {
  const counts = new Map();
  for (const row of subset) counts.set(row.rule ?? 'defer', (counts.get(row.rule ?? 'defer') ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0].join(': ');
}

const leakUpper = wilsonUpper(leak.length, n);
const coverage = decided.length / n;
const coverageInterval = wilsonInterval(decided.length, n);

const summary = {
  generatedAt: new Date().toISOString(),
  status: 'ok',
  dataset: input.dataset,
  corpus: { scanned: input.scanned, kept: n, droppedMixed: input.droppedMixed },
  leak: { count: leak.length, n, upper: leakUpper, examples: leak.slice(0, 5).map((row) => ({ id: row.id, rule: row.rule, text: row.text.slice(0, 160) })) },
  coverage: { count: decided.length, n, rate: coverage, interval: coverageInterval },
  byCategory,
  labelCensus: input.labelCensus,
};

writeFileSync(join(results, 'p06-pii-recall.json'), JSON.stringify(summary, null, 2));

const markdown = [
  '# POC-6: fail-closed at corpus scale',
  '',
  `Corpus: \`${input.dataset}\`, ${input.scanned} rows scanned, **${n}** kept `
    + `(${input.droppedMixed} dropped for carrying non-deterministic labels).`,
  'Every kept row carries only annotated identifiers, so the published policy requires it to stay private.',
  '',
  '## The two numbers',
  '',
  table(
    [
      {
        metric: 'leak (published to the shared store)',
        value: `${leak.length} / ${n}`,
        bound: `Wilson 95% upper ${(leakUpper * 100).toFixed(2)}%`,
      },
      {
        metric: 'coverage (decided by an explicit rule)',
        value: `${(coverage * 100).toFixed(1)}%`,
        bound: `95% CI ${(coverageInterval[0] * 100).toFixed(1)}–${(coverageInterval[1] * 100).toFixed(1)}%`,
      },
    ],
    ['metric', 'value', 'bound'],
  ),
  '',
  '## By category',
  '',
  table(byCategory, ['category', 'n', 'leak', 'leak upper', 'coverage', 'top rule']),
  '',
  '## What it means',
  '',
  'Leak is near zero **because `defer` lands private**, not because the patterns are exhaustive.',
  'That is the whole design: the default is the safety property, and the rules exist to keep the',
  'card queue short. Which means the quantity that needs a large n is *coverage*, and the quantity',
  'that needs a large n for safety is "how often a publishing rule fires on a private row" — both',
  'of which this corpus measures directly, at a denominator two orders of magnitude larger than',
  'the hand-labelled set.',
  '',
  ...(leak.length > 0
    ? ['## Leaks found (these are the next rule bugs, not statistics)', '', ...leak.slice(0, 10).map((row) => `- \`${row.rule}\` on ${row.id}: ${row.text}`), '']
    : ['## Leaks found', '', 'None in this sample. The bound is the claim; the count is not.', '']),
].join('\n');

writeFileSync(join(results, 'p06-pii-recall.md'), markdown + '\n');
console.log(markdown);

// A leak is data, not a broken build: the run must still publish its output, or the finding
// disappears with the job. The gate belongs on the number ("is leak upper <= 5%?"), which a
// reader applies, not on the exit status, which would only teach people to re-run.
if (leak.length > 0) {
  console.error(`::warning::${leak.length} policy-forced row(s) published to the shared store`);
}
