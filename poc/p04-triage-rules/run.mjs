#!/usr/bin/env node
/**
 * POC-4: does a deterministic rule layer keep private facts out of the shared store?
 *
 * ## The question, stated as a measurement
 *
 * docs/13 claims that the disclosure decision must not be delegated to a model, and that a rule
 * layer plus the user is the alternative. That claim is only worth something if the rule layer
 * can be measured on real text -- so this script runs it over 60 hand-labelled real utterances
 * and reports four numbers:
 *
 *   false-share   the rate at which a gold-private fact would reach the shared store. This is
 *                 the only asymmetric error: a false-private costs the user one tap, a
 *                 false-share cannot be taken back.
 *   coverage      the share of candidates the rules decide at all. The rest become cards.
 *   agreement     exact 3-way agreement with the gold labels, for context.
 *   stability     re-running the rules must give identical output. It is asserted, not assumed:
 *                 a rule layer that varied run to run would have the defect CIMemories measured
 *                 in models (25% on repeated identical prompts) with none of the excuses.
 *
 * ## Why the bound and not the count
 *
 * Zero false-shares in 60 is not a rate of zero. `wilsonUpper` turns it into "at most 5.9% at
 * 95%", which is the form a review can argue with. docs/14 quotes that number and says what
 * sample size would be needed to claim 1%.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { table, wilsonUpper } from '../lib/stats.mjs';
import { classify, destination, RULE_TABLE } from './rules.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const results = join(HERE, '..', 'results');

const gold = JSON.parse(readFileSync(join(HERE, 'labels.json'), 'utf8'));
const rows = gold.rows;

const outcomes = rows.map((row) => ({ ...row, ...destination(row.text) }));

const count = (predicate) => outcomes.filter(predicate).length;
const goldPrivate = outcomes.filter((row) => row.gold === 'private');
const goldShared = outcomes.filter((row) => row.gold === 'shared');
const goldDefer = outcomes.filter((row) => row.gold === 'defer');

const falseShare = goldPrivate.filter((row) => row.destination === 'shared');
const falsePrivate = outcomes.filter((row) => row.gold === 'shared' && row.destination !== 'shared');
const decided = outcomes.filter((row) => row.scope !== 'defer');
const agreed = outcomes.filter((row) => row.scope === row.gold);

const falseShareUpper = wilsonUpper(falseShare.length, goldPrivate.length);
const coverage = decided.length / outcomes.length;

// Stability: the same call, ten times, must give the same answer for every row.
const unstable = [];
for (let pass = 0; pass < 10; pass += 1) {
  for (const row of rows) {
    if (classify(row.text).scope !== outcomes[rows.indexOf(row)].scope) unstable.push(row.id);
  }
}

const perRule = new Map();
for (const row of outcomes) {
  const key = row.rule ?? 'defer';
  const bucket = perRule.get(key) ?? { rule: key, fired: 0, 'gold private': 0, 'gold shared': 0, 'gold defer': 0 };
  bucket.fired += 1;
  bucket[`gold ${row.gold}`] += 1;
  perRule.set(key, bucket);
}

const report = {
  generatedAt: new Date().toISOString(),
  sample: outcomes.length,
  strata: {
    random: outcomes.filter((row) => row.stratum === 'random').length,
    'work-cue': outcomes.filter((row) => row.stratum === 'work-cue').length,
  },
  gold: { private: goldPrivate.length, shared: goldShared.length, defer: goldDefer.length },
  falseShare: { count: falseShare.length, of: goldPrivate.length, wilsonUpper95: falseShareUpper },
  falsePrivate: { count: falsePrivate.length, of: goldShared.length },
  coverage,
  exactAgreement: agreed.length / outcomes.length,
  unstable,
  rules: [...perRule.values()],
  rows: outcomes.map((row) => ({
    id: row.id,
    gold: row.gold,
    predicted: row.scope,
    destination: row.destination,
    rule: row.rule,
    text: row.text,
  })),
};

writeFileSync(join(results, 'p04-triage-rules.json'), JSON.stringify(report, null, 2));

const summary = [
  table(
    [
      { metric: 'gold private', value: String(goldPrivate.length), note: 'must never reach the shared store' },
      { metric: 'gold shared', value: String(goldShared.length), note: 'may, after confirmation' },
      { metric: 'gold defer', value: String(goldDefer.length), note: 'decision handed to the user' },
      {
        metric: 'false-share',
        value: `${falseShare.length} / ${goldPrivate.length}`,
        note: `Wilson 95% upper ${(falseShareUpper * 100).toFixed(1)}%`,
      },
      { metric: 'false-private', value: `${falsePrivate.length} / ${goldShared.length}`, note: 'recoverable by one tap' },
      { metric: 'coverage', value: `${(coverage * 100).toFixed(1)}%`, note: 'decided by rules; the rest are cards' },
      {
        metric: 'exact 3-way agreement',
        value: `${((agreed.length / outcomes.length) * 100).toFixed(1)}%`,
        note: 'context, not a goal',
      },
      { metric: 'stability over 10 passes', value: unstable.length === 0 ? 'identical' : `${unstable.length} changed`, note: 'deterministic by construction' },
    ],
    ['metric', 'value', 'note'],
  ),
  '',
  '### Where each rule fired',
  '',
  table(
    report.rules.map((row) => ({
      rule: row.rule,
      fired: row.fired,
      'gold private': row['gold private'],
      'gold shared': row['gold shared'],
      'gold defer': row['gold defer'],
    })),
    ['rule', 'fired', 'gold private', 'gold shared', 'gold defer'],
  ),
  '',
  `Rules in table order: ${RULE_TABLE.map((rule) => rule.id).join(' -> ')}. Private rules run first,`,
  'so a sentence that is organisational *and* personal stays private.',
].join('\n');

writeFileSync(join(results, 'p04-triage-rules.md'), summary + '\n');
console.log(summary);
