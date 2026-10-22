#!/usr/bin/env node
/**
 * POC-1: SQLite-WASM on OPFS, in Chromium, across a browser restart.
 *
 * ## What this answers, and what nothing else could
 *
 * docs/02 rejects DuckDB-WASM as the system of record and calls SQLite-WASM + OPFS the default.
 * That choice rests on three things that cannot be settled by reading documentation:
 *
 *   1. does the `opfs` VFS actually work in a Worker in this Chromium (no cross-origin isolation)?
 *   2. does data survive a *browser restart*, not just a page reload?
 *   3. what does the KV workload this product generates cost?
 *
 * The runner therefore launches a persistent profile twice. The first launch writes and returns
 * a digest; the second launch, in a new process and a new page, reads the same rows back and
 * returns its own digest. Equal digests and equal row counts are the persistence claim, and they
 * are stronger than a reload because the process died in between.
 *
 * ## What this does NOT show
 *
 * Safari. PGlite's documentation records a 252-handle limit in Safari that breaks its own OPFS
 * VFS, and nothing here can speak to whether sqlite-wasm's VFS hits the same wall. docs/04
 * records that as the one open blocker and names the probe that would close it.
 */

import { readdirSync, existsSync, rmSync, writeFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium, webkit } from 'playwright-core';
import { bytes, table } from '../lib/stats.mjs';
import { serve } from './serve.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const RESULTS = join(ROOT, 'results');
const PROFILE = join(ROOT, '.profile-p01');
const ROWS = Number(process.env.POC_ROWS ?? 10_000);

// The engine is a parameter because the Safari question is the one this POC could not answer on
// its own host: Playwright's WebKit is the closest thing to Safari that runs in CI. It is not
// Safari -- different networking and storage plumbing -- so the workflow tests both and records
// the difference rather than reporting one as the other.
const BROWSER = process.env.POC_BROWSER ?? 'chromium';
const ENGINE = BROWSER === 'webkit' ? webkit : chromium;

// The vector scan is three 60k-dimensional passes; useful on a laptop, wasteful on a CI runner
// whose only job is the persistence question.
const WITH_VECTOR = (process.env.POC_VECTOR ?? 'on') !== 'off';


async function withPage(port, fn) {
  const options = { headless: true };
  if (BROWSER === 'chromium') {
    options.executablePath =
      process.env.CHROMIUM_PATH ?? '/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome';
    options.args = ['--no-sandbox', '--disable-dev-shm-usage'];
  }
  const context = await ENGINE.launchPersistentContext(PROFILE, options);
  try {
    const page = await context.newPage();
    page.on('console', (message) => {
      if (message.type() === 'error') console.error('[page]', message.text());
    });
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.ready === true);
    return await fn(page);
  } finally {
    await context.close();
  }
}

const rpc = (page, cmd, payload) => page.evaluate(([c, p]) => window.rpc(c, p), [cmd, payload]);

// A fresh profile per run, so "the data survived" cannot be an artefact of a previous run.
if (existsSync(PROFILE)) rmSync(PROFILE, { recursive: true, force: true });

const { server, port } = await serve();
let phaseOne;
let phaseTwo;
try {
  console.log(`phase 1: write ${ROWS} rows, then close the browser`);
  phaseOne = await withPage(port, async (page) => {
    const userAgent = await page.evaluate(() => navigator.userAgent);
    const init = await rpc(page, 'init');
    const write = await rpc(page, 'write', { rows: ROWS });
    const read = await rpc(page, 'read', { rows: ROWS });
    const vector = WITH_VECTOR
      ? {
          small: await rpc(page, 'vectorScan', { count: 20_000, dimensions: 384 }),
          large: await rpc(page, 'vectorScan', { count: 60_000, dimensions: 384 }),
          wide: await rpc(page, 'vectorScan', { count: 20_000, dimensions: 1024 }),
        }
      : null;
    await rpc(page, 'closeDb');
    return { userAgent, init, write, read, vector };
  });

  console.log(`phase 2: relaunch, read the same rows back, compare digests`);
  phaseTwo = await withPage(port, async (page) => {
    const init = await rpc(page, 'init');
    const read = await rpc(page, 'read', { rows: ROWS });
    await rpc(page, 'closeDb');
    return { init, read };
  });
} finally {
  server.close();
}

const digestOne = phaseOne.read.digest >>> 0;
const digestTwo = phaseTwo.read.digest >>> 0;
const persisted = digestOne === digestTwo && phaseOne.read.scanned === phaseTwo.read.scanned;

/** Recursive byte count of the browser profile, so the storage claim has a size beside it. */
function directoryBytes(dir) {
  let total = 0;
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return 0;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) total += directoryBytes(full);
    else {
      try {
        total += statSync(full).size;
      } catch {
        // A file that vanished mid-walk contributes nothing rather than aborting the count.
      }
    }
  }
  return total;
}

const profileBytes = directoryBytes(PROFILE);

const summary = {
  generatedAt: new Date().toISOString(),
  browser: BROWSER,
  userAgent: phaseOne.userAgent,
  sqliteVersion: phaseOne.init.version,
  sqliteVfs: phaseOne.init.vfs,
  rows: ROWS,
  initMs: phaseOne.init.initMs,
  reopenMs: phaseTwo.init.initMs,
  writeMs: phaseOne.write.writeMs,
  checkpointMs: phaseOne.write.checkpointMs,
  rowsPerSecond: phaseOne.write.rowsPerSecond,
  pointReadMs: phaseOne.read.pointReadMs,
  tagQueryMs: phaseOne.read.tagQueryMs,
  fullScanMs: phaseOne.read.fullScanMs,
  digestPhaseOne: digestOne,
  digestPhaseTwo: digestTwo,
  rowsPhaseOne: phaseOne.read.scanned,
  rowsPhaseTwo: phaseTwo.read.scanned,
  persisted,
  vector: phaseOne.vector,
  profileBytes,
};

const stem = BROWSER === 'chromium' ? 'p01-browser-storage' : `p01-browser-storage-${BROWSER}`;
writeFileSync(join(RESULTS, `${stem}.json`), JSON.stringify(summary, null, 2));

const markdown = [
  table(
    [
      { metric: 'rows written', value: String(ROWS), note: 'KV table with a tag index, one transaction' },
      { metric: 'write throughput', value: `${Math.round(phaseOne.write.rowsPerSecond)} rows/s`, note: `${phaseOne.write.writeMs.toFixed(0)} ms for the insert batch` },
      { metric: 'checkpoint', value: `${phaseOne.write.checkpointMs.toFixed(0)} ms`, note: 'flush to OPFS, without it a killed tab loses the batch' },
      { metric: 'point read', value: `${phaseOne.read.pointReadMs.toFixed(3)} ms`, note: '200 lookups, primary key' },
      { metric: 'tag query', value: `${phaseOne.read.tagQueryMs.toFixed(2)} ms`, note: `${phaseOne.read.tagRows} rows via the tags index` },
      { metric: 'full scan', value: `${phaseOne.read.fullScanMs.toFixed(0)} ms`, note: `${phaseOne.read.scanned} rows back through the JS boundary` },
      { metric: 'digest, launch 1', value: String(digestOne), note: 'FNV-1a over every payload' },
      { metric: 'digest, launch 2', value: String(digestTwo), note: 'new browser process, same profile' },
      { metric: 'persisted across restart', value: persisted ? 'YES' : 'NO', note: `rows ${phaseOne.read.scanned} vs ${phaseTwo.read.scanned}` },
      { metric: 'profile size on disk', value: bytes(profileBytes), note: 'includes Chromium\'s own profile files' },
      {
        metric: 'vector scan 20k x 384, in tab',
        value: `${phaseOne.vector.small.p50Ms.toFixed(1)} ms p50`,
        note: `p95 ${phaseOne.vector.small.p95Ms.toFixed(1)} ms, ${bytes(phaseOne.vector.small.storedBytes)} held`,
      },
      ...(phaseOne.vector
        ? [
            {
              metric: 'vector scan 60k x 384, in tab',
              value: `${phaseOne.vector.large.p50Ms.toFixed(1)} ms p50`,
              note: `p95 ${phaseOne.vector.large.p95Ms.toFixed(1)} ms, ${bytes(phaseOne.vector.large.storedBytes)} held`,
            },
            {
              metric: 'vector scan 20k x 1024, in tab',
              value: `${phaseOne.vector.wide.p50Ms.toFixed(1)} ms p50`,
              note: `p95 ${phaseOne.vector.wide.p95Ms.toFixed(1)} ms, ${bytes(phaseOne.vector.wide.storedBytes)} held`,
            },
          ]
        : [{ metric: 'vector scan', value: 'skipped', note: 'POC_VECTOR=off: this run only answers persistence' }]),
    ],
    ['metric', 'value', 'note'],
  ),
  '',
  `SQLite ${phaseOne.init.version} via \`@sqlite.org/sqlite-wasm\`, \`${phaseOne.init.vfs}\` VFS inside a module Worker,`,
  `${BROWSER} headless, no cross-origin isolation headers.`,
  'Phase 1 writes and closes the browser; phase 2 is a new process reading the same profile.',
].join('\n');

writeFileSync(join(RESULTS, `${stem}.md`), markdown + '\n');
console.log('\n' + markdown);
