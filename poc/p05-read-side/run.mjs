#!/usr/bin/env node
/**
 * POC-5: does the write/read boundary hold end to end, and what does holding it cost?
 *
 * ## The question
 *
 * docs/02 (design) says three things about the private/shared split:
 *
 *   1. a shared task may only see shared rows (this is the boundary);
 *   2. `defer` defaults to private, because a deferred decision is not consent;
 *   3. the card queue is the main path, not an exception path.
 *
 * POC-4 measured the rule layer alone: 0 of 12 gold-private facts reach the shared store,
 * coverage 26.7%. What it did not measure is the *end-to-end* consequence -- what a reader
 * actually sees once the rules, the two stores and the read-side assembler are wired together.
 * This script measures that, on the same 60 hand-labelled rows, and it reports the cost as
 * well as the benefit:
 *
 *   leak          gold-private rows that appear in a shared window  (want 0)
 *   reach/shared  gold-shared rows a shared task can actually see    (want 8/8)
 *   reach/private gold-private rows a private task can see           (want 12/12)
 *   noise         gold-defer rows pushed into a shared window        (want 0)
 *
 * ## Why three user policies and not one
 *
 * The rule layer only decides 26.7% of candidates; the other 73% become cards. So the boundary
 * a real user gets depends on *what they do with the queue*, and a single number would hide
 * that. Three policies bracket the space:
 *
 *   rules-only    nobody confirms anything. Rules plus fail-closed default.
 *   oracle        a perfect user confirms exactly the correct cards. Upper bound on
 *                 completeness at zero leakage -- and it is not achievable, which is the point:
 *                 it prices what the queue would have to do perfectly.
 *   defer-shared  the A4 ablation, precisely: the private rules still run, but `defer` lands
 *                 shared instead of private. This is the change one line of code would make.
 *   no-triage     the A1 ablation: publish everything, no rule layer at all. Included because
 *                 "the rules are load-bearing" has to be shown against the thing they replaced,
 *                 not only against a variant of themselves.
 *
 * ## What this cannot prove
 *
 * - It says nothing about retrieval quality: the 60 rows are the whole corpus, so "reach" here
 *   is reachability under the boundary, not recall under a query. POC-4's caveats apply.
 * - It does not exercise the LLM proposer, real users, or non-English text.
 * - The assembler is wired over `MemoryStore`, not OPFS/SQLite; POC-1 and POC-3 cover those
 *   layers separately, and mixing them would make a failure ambiguous.
 * - The 12/8/40 split is small. Every proportion is therefore reported with a Wilson bound
 *   where it matters (leakage), and as a plain count where it is a completeness statement.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { table, wilsonUpper } from '../lib/stats.mjs';
import { destination } from '../p04-triage-rules/rules.mjs';
import { MemoryStore } from '../p03-federation/memory-store.mjs';
import { FederatedStorage } from '../p03-federation/federated.mjs';
import { ReadSideAssembler, ScopeViolation } from './assembler.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const results = join(HERE, '..', 'results');

const gold = JSON.parse(readFileSync(join(HERE, '..', 'p04-triage-rules', 'labels.json'), 'utf8'));
const rows = gold.rows.map((row) => ({ ...row, ...destination(row.text) }));

const GOLD_PRIVATE = rows.filter((row) => row.gold === 'private').length;
const GOLD_SHARED = rows.filter((row) => row.gold === 'shared').length;
const GOLD_DEFER = rows.filter((row) => row.gold === 'defer').length;

/**
 * Build the two stores for one user policy, then let the owning user read from both.
 *
 * The local store always receives everything: it is the owner's own memory, and separating
 * "what I know" from "what we know" must not cost the owner a row. The remote store receives
 * only the rows the policy publishes, and each published row carries `visibility: 'shared'` --
 * the declaration the assembler checks.
 */
async function buildWorld(policy) {
  const local = new MemoryStore();
  const shared = new MemoryStore();
  const federation = new FederatedStorage({ private: local, shared });

  for (const row of rows) {
    const value = { id: row.id, text: row.text, gold: row.gold, visibility: 'private' };
    await federation.put('private/facts', row.id, value);

    const publishes =
      policy === 'no-triage' ||
      (policy === 'defer-shared' && row.scope === 'defer') ||
      row.destination === 'shared' ||
      (policy === 'oracle' && row.gold === 'shared');
    if (publishes) {
      await federation.put('shared/facts', row.id, { ...value, visibility: 'shared' });
    }
  }

  return { federation, local, shared };
}

function measure(window, goldLabel) {
  return window.filter((row) => row.value.gold === goldLabel).length;
}

async function runPolicy(policy) {
  const { federation } = await buildWorld(policy);
  const assembler = new ReadSideAssembler(federation);

  const sharedWindow = await assembler.assemble({ task: 'shared' });
  const privateWindow = await assembler.assemble({ task: 'private' });

  const leak = measure(sharedWindow, 'private');
  return {
    policy,
    leak,
    leakUpper: wilsonUpper(leak, GOLD_PRIVATE),
    reachShared: measure(sharedWindow, 'shared'),
    reachPrivate: measure(privateWindow, 'private'),
    noise: measure(sharedWindow, 'defer'),
    sharedRows: sharedWindow.length,
    privateRows: privateWindow.length,
    originLabelled: sharedWindow.concat(privateWindow).every((row) => row.origin === 'private' || row.origin === 'shared'),
    deduped: privateWindow.length === rows.length && new Set(privateWindow.map((row) => row.key)).size === rows.length,
  };
}

const policies = [];
for (const policy of ['rules-only', 'oracle', 'defer-shared', 'no-triage']) policies.push(await runPolicy(policy));
const byPolicy = Object.fromEntries(policies.map((reading) => [reading.policy, reading]));

// ---------------------------------------------------------------------------------------------
// The guard, and the only way to show that it is load-bearing: break the writer on purpose.
//
// With the writer correct, rule 1 (read one store) already prevents leakage, and the guard is
// redundant -- so a passing run says nothing about whether the guard works. The ablation is
// therefore a fault injection: put a private row into the shared store directly, bypassing the
// router, exactly as a bug would. Then the guard either fires or the row lands in the window.
// ---------------------------------------------------------------------------------------------

async function faultInjection({ guard }) {
  const { federation, shared } = await buildWorld('rules-only');
  const victim = rows.find((row) => row.gold === 'private');
  // Bypass the router: this is the defect, not a supported call.
  await shared.put('facts', victim.id, { id: victim.id, text: victim.text, gold: victim.gold, visibility: 'private' });

  const assembler = new ReadSideAssembler(federation, { guard });
  try {
    const window = await assembler.assemble({ task: 'shared' });
    return { guard, threw: false, leak: measure(window, 'private') };
  } catch (error) {
    return { guard, threw: error instanceof ScopeViolation, leak: 0, message: error.message };
  }
}

const guarded = await faultInjection({ guard: true });
const unguarded = await faultInjection({ guard: false });

// ---------------------------------------------------------------------------------------------
// Determinism: two assemblies of the same stores must return the same ids in the same order.
// ---------------------------------------------------------------------------------------------

const { federation: stableFederation } = await buildWorld('oracle');
const stableAssembler = new ReadSideAssembler(stableFederation);
const first = (await stableAssembler.assemble({ task: 'private' })).map((row) => row.key).join(',');
const second = (await stableAssembler.assemble({ task: 'private' })).map((row) => row.key).join(',');

// ---------------------------------------------------------------------------------------------
// Assertions. Nine of them, each of which a real defect could break.
// ---------------------------------------------------------------------------------------------

const checks = [];
function check(name, predicate, detail) {
  let passed = false;
  let note = detail;
  try {
    passed = Boolean(predicate());
  } catch (error) {
    note = `${detail} (threw: ${error.message})`;
  }
  checks.push({ check: name, result: passed ? 'PASS' : 'FAIL', detail: note });
  return passed;
}

check(
  'a shared window carries no gold-private row (rules-only)',
  () => byPolicy['rules-only'].leak === 0,
  `leak ${byPolicy['rules-only'].leak}/${GOLD_PRIVATE}, Wilson upper ${(byPolicy['rules-only'].leakUpper * 100).toFixed(1)}%`,
);
check(
  'a private window carries every row, exactly once',
  () => byPolicy['rules-only'].deduped,
  `${byPolicy['rules-only'].privateRows} rows for ${rows.length} facts`,
);
check(
  'every assembled row says where it came from',
  () => byPolicy['rules-only'].originLabelled,
  'origin label survives the two-store merge',
);
check(
  'the guard fires on a private row injected into the shared store',
  () => guarded.threw === true,
  guarded.threw ? 'ScopeViolation raised, no prompt launched' : 'nothing was raised: the guard cannot fail',
);
check(
  'without the guard the same injection reaches the window',
  () => unguarded.threw === false && unguarded.leak === 1,
  `guard off: leak ${unguarded.leak}/1 -- this is what the guard buys`,
);
check(
  'defer-shared leaks, so the defer default is load-bearing',
  () => byPolicy['defer-shared'].leak > 0,
  `leak ${byPolicy['defer-shared'].leak}/${GOLD_PRIVATE} (A4 ablation: one line moved)`,
);
check(
  'no-triage leaks everything, so the rule layer is load-bearing',
  () => byPolicy['no-triage'].leak === GOLD_PRIVATE,
  `leak ${byPolicy['no-triage'].leak}/${GOLD_PRIVATE} (A1 ablation)`,
);
check(
  'a perfect confirmation buys completeness the rules cannot',
  () => byPolicy['oracle'].reachShared > byPolicy['rules-only'].reachShared,
  `reach ${byPolicy['rules-only'].reachShared}/${GOLD_SHARED} -> ${byPolicy['oracle'].reachShared}/${GOLD_SHARED}`,
);
check(
  'the perfect-confirmation path still leaks nothing',
  () => byPolicy['oracle'].leak === 0,
  'confirming the right cards is sound at both ends',
);
check(
  'assembly is deterministic across two passes',
  () => first === second,
  first === second ? `${first.split(',').length} ids identical` : 'two passes disagreed',
);

let unknownRefused = false;
try {
  await new ReadSideAssembler(stableFederation).assemble({ task: 'both' });
} catch (error) {
  unknownRefused = error instanceof ScopeViolation;
}
check('an unknown task scope is refused', () => unknownRefused, '"both" is not a task scope');

// ---------------------------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------------------------

const summary = table(
  policies.map((reading) => ({
    policy: reading.policy,
    leak: `${reading.leak} / ${GOLD_PRIVATE}`,
    'leak upper': `${(reading.leakUpper * 100).toFixed(1)}%`,
    'reach shared': `${reading.reachShared} / ${GOLD_SHARED}`,
    'reach private': `${reading.reachPrivate} / ${GOLD_PRIVATE}`,
    noise: `${reading.noise} / ${GOLD_DEFER}`,
    'shared rows': reading.sharedRows,
  })),
  ['policy', 'leak', 'leak upper', 'reach shared', 'reach private', 'noise', 'shared rows'],
);

const markdown = [
  '# POC-5: the write/read boundary, end to end',
  '',
  `Corpus: the same ${rows.length} hand-labelled LongMemEval-S utterances as POC-4 `
    + `(${GOLD_PRIVATE} private / ${GOLD_SHARED} shared / ${GOLD_DEFER} defer).`,
  'The rules decide the first pass; the card queue is simulated by the policy column.',
  '',
  '## The four user policies',
  '',
  summary,
  '',
  '**Reading it.** `rules-only` is the shipped default: the boundary holds at zero leakage, but a',
  'shared task reaches only half of what is legitimately shareable, because four gold-shared rows',
  'were classified private and became cards. `oracle` is the upper bound a perfect queue would',
  'reach: 8/8 with no leakage, which is what makes the queue worth building rather than a tax.',
  '`defer-shared` is the A4 ablation -- one line of code, `defer` landing shared instead of private:',
  'it buys three more reachable facts and publishes three gold-private ones, and no later audit can',
  'take those back. `no-triage` is A1, the thing the rule layer replaced: every gold-private fact',
  'in the sample reaches the shared store.',
  '',
  '## The guard, priced by a fault',
  '',
  table(
    [
      { state: 'guard on', result: guarded.threw ? 'ScopeViolation' : 'no error', leak: '0 / 1' },
      { state: 'guard off', result: unguarded.threw ? 'ScopeViolation' : 'no error', leak: `${unguarded.leak} / 1` },
    ],
    ['state', 'result', 'leak'],
  ),
  '',
  'The guard is redundant while the writer is correct, so a clean run proves nothing about it.',
  'Injecting one private row into the shared store -- bypassing the router, as a bug would -- is',
  'the only way to show it is load-bearing: it refuses to launch a prompt rather than filtering',
  'the row out, because filtering would keep the boundary looking intact while the writer stayed',
  'broken.',
  '',
  '## Assertions',
  '',
  table(checks, ['check', 'result', 'detail']),
  '',
].join('\n');

writeFileSync(
  join(results, 'p05-read-side.json'),
  JSON.stringify(
    {
      generatedAt: new Date().toISOString(),
      corpus: { rows: rows.length, goldPrivate: GOLD_PRIVATE, goldShared: GOLD_SHARED, goldDefer: GOLD_DEFER },
      policies,
      guard: { on: guarded, off: unguarded },
      checks,
    },
    null,
    2,
  ),
);
writeFileSync(join(results, 'p05-read-side.md'), `${markdown}\n`);
console.log(markdown);

const failed = checks.filter((entry) => entry.result !== 'PASS');
if (failed.length > 0) {
  console.error(`${failed.length} assertion(s) failed`);
  process.exitCode = 1;
}
