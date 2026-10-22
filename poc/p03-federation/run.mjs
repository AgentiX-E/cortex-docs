#!/usr/bin/env node
/**
 * POC-3: the federation's semantics, asserted rather than described.
 *
 * ## The claim under test
 *
 * docs/02 says the four storage topologies reduce to one contract plus a router, and that the
 * router can live in `cortex-core` because it is pure composition over `Storage`. This script
 * is that router, and the seven checks below are the ones a reviewer would ask for: routing,
 * read isolation, labelled provenance, delete scoping, ttl independence, and two refusals
 * (cross-store transaction, unknown scope).
 *
 * ## Why there is no latency number here
 *
 * Nothing in this POC is about speed: `Storage` is `Promise`-shaped, so the browser's worker
 * RPC fits it without a change, and POC-1 measures what a real engine costs. What cannot be
 * discovered by reading the code is whether the *boundary* holds -- so that is all this
 * measures, and every assertion is a real behaviour of two real stores.
 */

import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { table } from '../lib/stats.mjs';
import { FederatedStorage, FederationError, scopeOf } from './federated.mjs';
import { MemoryStore } from './memory-store.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const results = join(HERE, '..', 'results');

const checks = [];
function check(name, assertion, detail) {
  let passed = false;
  try {
    passed = assertion() === true;
  } catch (error) {
    detail = `${detail} (threw: ${error.message})`;
  }
  checks.push({ check: name, result: passed ? 'PASS' : 'FAIL', detail });
  if (!passed) throw new Error(`check failed: ${name} -- ${detail}`);
}

const federation = new FederatedStorage({ private: new MemoryStore(), shared: new MemoryStore() });

// 1. Routing: the prefix decides the store, and an unprefixed table is private.
check(
  'routing follows the prefix, unprefixed is private',
  () => scopeOf('shared/facts') === 'shared' && scopeOf('facts') === 'private',
  'shared/facts -> shared, facts -> private',
);

// 2. A private write is invisible to the shared store at the engine level, not just in query.
await federation.put('private/facts', 'f1', { text: 'my dentist appointment is on Thursday' });
await federation.put('shared/facts', 'f2', { text: 'the project plan covers onboarding' });
// A check whose assertion cannot fail is worse than no check: the first draft of this file had
// one (`async () => true`) and it threw on its own Promise rather than on the behaviour. Removed.
// Both stores now hold a table called `facts` -- that is the namespace fix working. What must
// not happen is the private *row* appearing in the shared store.
const sharedRows = await federation.stores.shared.query('facts');
check(
  'the shared store holds the shared row and not the private one',
  () => sharedRows.length === 1 && sharedRows[0].text.startsWith('the project plan'),
  `${sharedRows.length} row(s) in the shared store: ${sharedRows.map((row) => row.text.slice(0, 16)).join(' / ')}`,
);

// 3. Reading one scope cannot see the other.
const privateRows = await federation.query('private/facts');
check('private query returns only private rows', () => privateRows.length === 1 && privateRows[0].text.startsWith('my dentist'), `${privateRows.length} row(s)`);

// 4. Cross-store reads carry their origin.
const across = await federation.queryAcross('facts');
check(
  'queryAcross labels every row with its origin',
  () => across.length === 2 && across.filter((row) => row.origin === 'private').length === 1,
  across.map((row) => `${row.origin}:${row.value.text.slice(0, 12)}`).join(', '),
);

// 5. Delete is scoped: removing the shared row leaves the private one.
await federation.del('shared/facts', 'f2');
const afterDelete = await federation.queryAcross('facts');
check('delete touches one scope only', () => afterDelete.length === 1 && afterDelete[0].origin === 'private', `${afterDelete.length} row(s) left`);

// 6. ttl is per-store, so one store's clock cannot expire the other's fact.
await federation.put('shared/facts', 'ttl', { text: 'temporary' }, { ttlMs: 5 });
await federation.put('private/facts', 'ttl', { text: 'permanent' });
await new Promise((resolve) => setTimeout(resolve, 15));
const afterTtl = await federation.queryAcross('facts');
check(
  'an expiring shared row does not expire the private row',
  () => afterTtl.some((row) => row.origin === 'private' && row.value.text === 'permanent') && !afterTtl.some((row) => row.value.text === 'temporary'),
  `${afterTtl.length} row(s) left after ttl`,
);

// 7. The two refusals.
let refused = false;
try {
  await federation.transaction(async () => 1);
} catch (error) {
  refused = error instanceof FederationError;
}
check('a federated transaction is refused, not faked', () => refused, 'FederationError raised');

let unknownRefused = false;
try {
  await federation.transactionIn('both', async () => 1);
} catch (error) {
  unknownRefused = error instanceof FederationError;
}
check('an unknown scope is refused', () => unknownRefused, '"both" rejected: it is not a store');

// 8. A scoped transaction is the real thing: it rolls back.
await federation.transactionIn('private', async (tx) => {
  await tx.put('private/facts', 'rolled', { text: 'should disappear' });
  throw new Error('abort');
}).catch(() => undefined);
const rolled = await federation.get('private/facts', 'rolled');
check('a scoped transaction rolls back', () => rolled === undefined, 'row absent after abort');

const markdown = [
  table(checks, ['check', 'result', 'detail']),
  '',
  'Eight checks, no mocks: both halves are a full `Storage` implementation with tags, ttl,',
  'prefix queries and a rollback-capable transaction. What is *not* implemented is a',
  'cross-store commit, and check 7 asserts that the router refuses rather than approximates.',
].join('\n');

writeFileSync(join(results, 'p03-federation.json'), JSON.stringify({ generatedAt: new Date().toISOString(), checks }, null, 2));
writeFileSync(join(results, 'p03-federation.md'), markdown + '\n');
console.log(markdown);
