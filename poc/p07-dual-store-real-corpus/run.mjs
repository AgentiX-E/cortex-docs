#!/usr/bin/env node
/**
 * POC-7: the private/shared split on the evidence a real benchmark actually admitted.
 *
 * ## Why this is the missing measurement
 *
 * POC-4 and POC-6 measure the rule layer on sentences chosen for the purpose: 60 hand-labelled
 * utterances, and 1,467 persona attributes. Neither answers the question a product person asks
 * first: **if a user's memory were split in two, what would a shared task have left to read?**
 *
 * The 500 questions of a LongMemEval-S run already carry the answer's raw material -- every turn
 * the reader was shown, after retrieval, admission and the character budget. Running the rule
 * layer over exactly those turns is therefore not a simulation of the workload; it *is* the
 * workload, minus the parts this POC cannot know (which turn carried the gold answer).
 *
 * ## What it measures, stated so it can be wrong
 *
 *   shared rate        turns a shared task could read, over all admitted turns
 *   empty windows      questions where no admitted turn would survive the split -- a shared task
 *                      on that question has literally nothing, not "less"
 *   publication fire   how often `org-knowledge` matched at all, because a split whose publishing
 *                      side never fires produces a topology that exists but cannot be used
 *
 * ## What it cannot measure
 *
 * Which turn carried the answer. `goldOverlap` in the artifact records ranks, not identities, so
 * "the gold evidence was private" is not derivable here. That is why the headline is a share of
 * admitted turns and an empty-window count, not a lost-accuracy number: a lost-accuracy number
 * would need turn-level gold that this artifact does not contain.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { table, wilsonInterval } from '../lib/stats.mjs';
import { classify, destination, RULE_TABLE } from '../p04-triage-rules/rules.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const results = join(HERE, '..', 'results');

const artifactPath = process.argv[2] ?? process.env.POC_ARTIFACT;
if (!artifactPath) {
  console.error('usage: node p07-dual-store-real-corpus/run.mjs <benchmark-*-report.json>');
  process.exit(2);
}

const report = JSON.parse(readFileSync(artifactPath, 'utf8'));
const questions = report.questions ?? [];

/** `[2023/05/20 (Sat) 03:51] user: ...` -> { role, body }. */
function splitTurn(text) {
  const match = /^\[[^\]]+\]\s*([a-z]+):\s*/i.exec(text);
  if (!match) return { role: 'unknown', body: text };
  return { role: match[1].toLowerCase(), body: text.slice(match[0].length) };
}

const publishing = RULE_TABLE.find((rule) => rule.id === 'org-knowledge');
const ruleCounts = new Map();
let turns = 0;
let shared = 0;
let publishingHits = 0;
let publishingVetoed = 0;
const byRole = new Map();
let emptyWindows = 0;
let halfPrivate = 0;
const sharedFractions = [];

for (const question of questions) {
  let questionShared = 0;
  let questionTurns = 0;
  for (const turn of question.turns ?? []) {
    const { role, body } = splitTurn(turn.text ?? '');
    const verdict = destination(body);
    turns += 1;
    questionTurns += 1;
    ruleCounts.set(verdict.rule ?? 'defer', (ruleCounts.get(verdict.rule ?? 'defer') ?? 0) + 1);
    if (publishing.pattern.test(body)) {
      publishingHits += 1;
      if (classify(body).scope !== 'shared') publishingVetoed += 1;
    }
    if (verdict.destination === 'shared') {
      shared += 1;
      questionShared += 1;
    }
    const bucket = byRole.get(role) ?? { turns: 0, shared: 0 };
    bucket.turns += 1;
    if (verdict.destination === 'shared') bucket.shared += 1;
    byRole.set(role, bucket);
  }
  if (questionTurns > 0) {
    const fraction = questionShared / questionTurns;
    sharedFractions.push(fraction);
    if (questionShared === 0) emptyWindows += 1;
    if (fraction <= 0.5) halfPrivate += 1;
  }
}

const summary = {
  generatedAt: new Date().toISOString(),
  artifact: artifactPath.split('/').slice(-2).join('/'),
  dataset: report.dataset,
  questions: questions.length,
  turns,
  shared,
  sharedRate: turns === 0 ? 0 : shared / turns,
  sharedRateInterval: wilsonInterval(shared, turns),
  emptyWindows,
  emptyWindowRate: questions.length === 0 ? 0 : emptyWindows / questions.length,
  halfOrMorePrivate: halfPrivate,
  instrument: {
    publishingRuleHits: publishingHits,
    vetoedByPrivate: publishingVetoed,
    // Of every turn the publishing rule would have claimed, how many a private rule got to
    // first. This is the ordering's value measured on real text: not a hypothetical, since both
    // counts come from the same pass.
    vetoRate: publishingHits === 0 ? null : publishingVetoed / publishingHits,
    exercised: publishingHits > 0,
  },
  ruleCounts: Object.fromEntries([...ruleCounts.entries()].sort((a, b) => b[1] - a[1])),
  byRole: Object.fromEntries(
    [...byRole.entries()].map(([role, value]) => [role, { ...value, sharedRate: value.shared / value.turns }]),
  ),
};

writeFileSync(join(results, 'p07-dual-store-real-corpus.json'), JSON.stringify(summary, null, 2));

const markdown = [
  '# POC-7: the split applied to the evidence a real run admitted',
  '',
  `Source: \`${summary.artifact}\` — ${questions.length} questions, **${turns}** admitted turns, `
    + `${report.runs ?? '?'} runs, dataset \`${report.dataset}\`.`,
  'Every turn the reader was actually shown is classified by the shipped rule table.',
  '',
  '## What a shared task would have left',
  '',
  table(
    [
      {
        metric: 'turns a shared task could read',
        value: `${shared} / ${turns} = ${(summary.sharedRate * 100).toFixed(2)}%`,
        bound: `95% CI ${(summary.sharedRateInterval[0] * 100).toFixed(2)}–${(summary.sharedRateInterval[1] * 100).toFixed(2)}%`,
      },
      {
        metric: 'questions with an empty shared window',
        value: `${emptyWindows} / ${questions.length} = ${(summary.emptyWindowRate * 100).toFixed(1)}%`,
        bound: 'not "less evidence" — nothing at all',
      },
      {
        metric: 'questions with at most half the turns shareable',
        value: `${halfPrivate} / ${questions.length}`,
        bound: 'the population a shared task would be operating on',
      },
      {
        metric: 'publishing rule matched',
        value: `${publishingHits} turns`,
        bound: `${publishingVetoed} of them (${((summary.instrument.vetoRate ?? 0) * 100).toFixed(1)}%) vetoed by an earlier private rule`,
      },
    ],
    ['metric', 'value', 'bound'],
  ),
  '',
  '## Where the decisions come from',
  '',
  table(
    Object.entries(summary.ruleCounts).map(([rule, count]) => ({
      rule,
      turns: String(count),
      share: `${((count / turns) * 100).toFixed(1)}%`,
    })),
    ['rule', 'turns', 'share'],
  ),
  '',
  '## By speaker',
  '',
  table(
    Object.entries(summary.byRole).map(([role, value]) => ({
      role,
      turns: String(value.turns),
      shared: String(value.shared),
      'shared rate': `${(value.sharedRate * 100).toFixed(2)}%`,
    })),
    ['role', 'turns', 'shared', 'shared rate'],
  ),
  '',
].join('\n');

writeFileSync(join(results, 'p07-dual-store-real-corpus.md'), markdown + '\n');
console.log(markdown);
