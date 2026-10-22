#!/usr/bin/env node
/**
 * Regression gate: every row the CI corpus run published must now be private.
 *
 * ## Why these rows and not a hand-written list
 *
 * They were not invented. A CI run of POC-6 over 3,000 identifier-bearing rows found 16 rows
 * that reached the shared store, and these are the ten whose text the report quoted. Each one is
 * a sentence the published policy says must stay private -- "the CVV is 412", "provide your
 * Bitcoin address 3D1mKZ…" -- and each one was published because no private rule claimed it.
 *
 * That makes them the cheapest possible regression suite: they are exactly the defects that
 * existed, they cost nothing to re-check, and every one of them was invisible to the 60-row
 * hand-labelled set, because that set contains no payment secrets.
 *
 * ## The honest limit
 *
 * The report truncated each row at 160 characters, so a row whose identifier fell past the cut
 * cannot exercise a pattern that would have matched only there. `regressions.json` says so, and
 * the CI re-run is what actually confirms the count went to zero -- this file only makes sure it
 * cannot come back.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { destination } from './rules.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(join(HERE, 'regressions.json'), 'utf8'));

let failures = 0;
let skipped = 0;
for (const row of fixture.rows) {
  // A row the report truncated cannot be judged from the string we have. Skipping it is not a
  // waiver: it stays in the file with its reason, it is counted separately, and the CI re-run --
  // which sees the full row -- is what settles it. Pretending it passed would be worse than the
  // red it produces.
  if (row.truncated) {
    skipped += 1;
    console.log(`SKIP ${row.id.padEnd(9)} ${'truncated'.padEnd(14)} ${row.text.slice(0, 70)}`);
    continue;
  }
  const verdict = destination(row.text);
  const ok = verdict.destination === 'private';
  if (!ok) failures += 1;
  console.log(
    `${ok ? 'ok  ' : 'FAIL'} ${row.id.padEnd(9)} ${ok ? (verdict.rule ?? 'defer').padEnd(14) : 'PUBLISHED'} ${row.text.slice(0, 70)}`,
  );
}

const judged = fixture.rows.length - skipped;
console.log(`\n${judged - failures}/${judged} judgeable rows are private again (${skipped} skipped as truncated)`);
if (failures > 0) {
  console.error(`${failures} row(s) would still reach the shared store`);
  process.exitCode = 1;
}
