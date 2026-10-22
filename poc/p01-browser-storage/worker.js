/**
 * The browser side of POC-1: SQLite-WASM on OPFS, inside a Worker.
 *
 * ## Why a Worker and not the page
 *
 * OPFS's synchronous access handles exist only in a dedicated worker, and the official
 * sqlite-wasm build routes its `opfs` VFS through an async proxy for the same reason. A design
 * that kept storage on the main thread would have to use the async-only handle API and lose the
 * synchronous VFS entirely -- so the Worker boundary is not an optimisation, it is the only
 * shape that works. This also validates the claim in docs/02 that `Storage`'s Promise-shaped
 * contract fits an RPC boundary without change.
 *
 * ## What it reports
 *
 * Raw timings and a digest, nothing interpreted. The runner turns them into the table in
 * docs/04; keeping interpretation out of the browser keeps the measurement honest.
 */

import sqlite3InitModule from '/vendor/index.mjs';

const PAYLOAD_CHARS = 480;
const digestState = { hash: 0x811c9dc5, count: 0 };

/** FNV-1a over the row payloads, so a reload can prove the bytes are the same ones. */
function fold(text) {
  for (let index = 0; index < text.length; index += 1) {
    digestState.hash ^= text.charCodeAt(index);
    digestState.hash = Math.imul(digestState.hash, 0x01000193) >>> 0;
  }
  digestState.count += 1;
}

function payloadFor(index) {
  // Deterministic, index-dependent, and long enough that the page is not compressible to nothing.
  const stem = `row-${String(index).padStart(6, '0')}`;
  return `${stem}:${'x'.repeat(PAYLOAD_CHARS - stem.length)}`;
}

let sqlite3 = null;
let db = null;
let pool = null;

/**
 * Open the database on OPFS.
 *
 * ## Why the SAH pool and not `oo1.OpfsDb`
 *
 * In `@sqlite.org/sqlite-wasm@3.54.1-build1` the bundler build (`dist/index.mjs`) exposes only
 * `oo1.DB`, `oo1.Stmt` and `oo1.JsStorageDb`, and `sqlite3_vfs_find('opfs')` returns 0 -- the
 * `opfs` VFS is not registered, so `new sqlite3.oo1.OpfsDb(...)` throws "not a constructor".
 * What is available is `installOpfsSAHPoolVfs`, the "access handle pool" VFS: a pool of
 * synchronously-usable OPFS handles allocated to database files, which is the same technique
 * PGlite's documentation describes borrowing from wa-sqlite.
 *
 * That distinction matters for the Safari question in docs/04: PGlite's OPFS-AHP VFS is the one
 * their docs say breaks in Safari on a 252-handle limit. This POC therefore exercises exactly the
 * VFS shape that has a known Safari risk, not a different one that happens to work in Chromium.
 */
async function open() {
  pool = await sqlite3.installOpfsSAHPoolVfs({ name: 'cortex-poc-pool', initialCapacity: 8 });
  db = new pool.OpfsSAHPoolDb('/cortex-poc.sqlite3');
  db.exec(`
    CREATE TABLE IF NOT EXISTS kv (
      table_name TEXT NOT NULL,
      key TEXT NOT NULL,
      value TEXT NOT NULL,
      tags TEXT NOT NULL DEFAULT '[]',
      PRIMARY KEY (table_name, key)
    );
    CREATE INDEX IF NOT EXISTS kv_tags ON kv(table_name, tags);
  `);
}

const handlers = {
  async init() {
    const started = performance.now();
    sqlite3 = await sqlite3InitModule({ locateFile: (file) => `/vendor/${file}` });
    await open();
    const initMs = performance.now() - started;
    return {
      initMs,
      version: sqlite3.version.libVersion,
      // The pool's VFS is registered under the pool's own name, so the honest evidence that it is
      // in use is that `installOpfsSAHPoolVfs` returned a handle with a DB constructor.
      vfs: pool && typeof pool.OpfsSAHPoolDb === 'function' ? 'opfs-sahpool' : 'unknown',
      sahPool: typeof sqlite3.installOpfsSAHPoolVfs === 'function',
    };
  },

  async write({ rows }) {
    const started = performance.now();
    db.exec('BEGIN');
    const statement = db.prepare('INSERT OR REPLACE INTO kv (table_name, key, value, tags) VALUES (?, ?, ?, ?)');
    for (let index = 0; index < rows; index += 1) {
      statement.bind(['facts', `k${index}`, payloadFor(index), JSON.stringify([`t${index % 50}`])]).stepReset();
    }
    statement.finalize();
    db.exec('COMMIT');
    const writeMs = performance.now() - started;
    // A checkpoint is what actually flushes to OPFS; without it a killed tab loses the writes.
    const checkpointStarted = performance.now();
    db.exec('PRAGMA wal_checkpoint(TRUNCATE)');
    const checkpointMs = performance.now() - checkpointStarted;
    return { writeMs, checkpointMs, rowsPerSecond: rows / (writeMs / 1000) };
  },

  async read({ rows }) {
    const pointStarted = performance.now();
    const point = [];
    for (let index = 0; index < 200; index += 1) {
      const row = db.selectObject('SELECT value FROM kv WHERE table_name = ? AND key = ?', [
        'facts',
        `k${(index * 37) % rows}`,
      ]);
      if (row) fold(row.value);
    }
    const pointMs = (performance.now() - pointStarted) / 200;

    const tagStarted = performance.now();
    const tagged = db.selectObjects('SELECT key FROM kv WHERE table_name = ? AND tags LIKE ? LIMIT 100', [
      'facts',
      `%"t7"%`,
    ]);
    const tagMs = performance.now() - tagStarted;

    const scanStarted = performance.now();
    let scanned = 0;
    db.exec({
      sql: 'SELECT value FROM kv WHERE table_name = ? ORDER BY key',
      bind: ['facts'],
      rowMode: 'array',
      callback: (row) => {
        fold(row[0]);
        scanned += 1;
      },
    });
    const scanMs = performance.now() - scanStarted;

    return {
      pointReadMs: pointMs,
      tagQueryMs: tagMs,
      tagRows: tagged.length,
      fullScanMs: scanMs,
      scanned,
      digest: digestState.hash >>> 0,
      digestCount: digestState.count,
    };
  },

  async vectorScan({ count, dimensions }) {
    // Dense f32 store in memory, the shape docs/02 section 4 recommends, scanned with the same
    // insertion-buffer top-k as POC-2 so the two numbers are comparable.
    const flat = new Float32Array(count * dimensions);
    let state = 0x9e3779b9;
    const random = () => {
      state ^= state << 13;
      state ^= state >>> 17;
      state ^= state << 5;
      return (state >>> 0) / 4294967296;
    };
    for (let index = 0; index < flat.length; index += 1) flat[index] = random() * 2 - 1;

    const query = new Float32Array(dimensions);
    for (let index = 0; index < dimensions; index += 1) query[index] = random() * 2 - 1;

    const K = 10;
    const scores = new Float64Array(K).fill(-Infinity);
    const scan = () => {
      scores.fill(-Infinity);
      for (let row = 0; row < count; row += 1) {
        let dot = 0;
        const base = row * dimensions;
        for (let d = 0; d < dimensions; d += 1) dot += flat[base + d] * query[d];
        if (dot <= scores[K - 1]) continue;
        let slot = K - 1;
        while (slot > 0 && scores[slot - 1] < dot) {
          scores[slot] = scores[slot - 1];
          slot -= 1;
        }
        scores[slot] = dot;
      }
    };
    scan();
    scan();
    const timings = [];
    for (let pass = 0; pass < 15; pass += 1) {
      const started = performance.now();
      scan();
      timings.push(performance.now() - started);
    }
    timings.sort((a, b) => a - b);
    return {
      count,
      dimensions,
      storedBytes: flat.byteLength,
      p50Ms: timings[Math.floor(timings.length / 2)],
      p95Ms: timings[Math.min(timings.length - 1, Math.floor(timings.length * 0.95))],
      top: Array.from(scores).slice(0, 3),
    };
  },

  async closeDb() {
    db.close();
    return { closed: true };
  },
};

self.onmessage = async (event) => {
  const { id, cmd, payload } = event.data;
  try {
    const result = await handlers[cmd](payload ?? {});
    self.postMessage({ id, ok: true, result });
  } catch (error) {
    self.postMessage({ id, ok: false, error: `${error && error.message ? error.message : error}` });
  }
};
