/**
 * End-to-end timeout verification against a REAL socket.
 *
 * `AbortSignal.timeout()` uses an unref'd timer in Node, so it does not keep the
 * event loop alive by itself. Every unit test above therefore exercises the
 * deadline only while the test runner holds the loop open; none of them proves
 * the deadline fires against a genuinely stalled socket, which is the failure
 * that actually killed a benchmark run (`TypeError: terminated` after a reset).
 *
 * This opens a server that accepts the connection and then never replies, and
 * checks that a real `fetch` is aborted by the deadline.
 */
import { createServer } from 'node:http';
import { retryableFetch, DEFAULT_RETRY_TIMEOUT_MS } from '/workspace/cortex/packages/cortex-llm/dist/retry.js';

const TIMEOUT_MS = 300;

const server = createServer(() => {
  // Deliberately never respond: simulate a half-open / stalled connection.
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const { port } = server.address();
const url = `http://127.0.0.1:${port}/chat/completions`;

let failures = 0;
const check = (label, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`);
  if (!ok) failures += 1;
};

// ---- 1. A stalled socket must be bounded by the deadline. ----
const started = Date.now();
let aborted = false;
try {
  await retryableFetch(
    fetch,
    url,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
    { maxRetries: 0, timeoutMs: TIMEOUT_MS },
  );
  check('stalled socket is aborted by the deadline', false, 'fetch returned instead of aborting');
} catch (err) {
  aborted = true;
  const elapsed = Date.now() - started;
  check('stalled socket is aborted by the deadline', true, `${err.name}: ${err.message}`);
  check('abort happens at the deadline, not before', elapsed >= TIMEOUT_MS, `elapsed ${elapsed}ms >= ${TIMEOUT_MS}ms`);
  check(
    'abort happens promptly after the deadline',
    elapsed < TIMEOUT_MS + 1500,
    `elapsed ${elapsed}ms < ${TIMEOUT_MS + 1500}ms`,
  );
}
check('the deadline did fire', aborted);

// ---- 2. Each retry gets its own deadline on a real socket. ----
let attempts = 0;
const counting = (u, init) => {
  attempts += 1;
  return fetch(u, init);
};
const started2 = Date.now();
try {
  await retryableFetch(counting, url, { method: 'POST', body: '{}' }, {
    maxRetries: 2,
    baseDelayMs: 1,
    timeoutMs: TIMEOUT_MS,
  });
  check('retries against a stalled socket eventually throw', false, 'returned instead of throwing');
} catch {
  const elapsed = Date.now() - started2;
  check('every retry was attempted (3 attempts)', attempts === 3, `attempts=${attempts}`);
  check(
    'three independent deadlines elapsed',
    elapsed >= TIMEOUT_MS * 3,
    `elapsed ${elapsed}ms >= ${TIMEOUT_MS * 3}ms`,
  );
}

// ---- 3. The default is sane. ----
check('default deadline is 60s', DEFAULT_RETRY_TIMEOUT_MS === 60_000, String(DEFAULT_RETRY_TIMEOUT_MS));

await new Promise((resolve, reject) => server.close((e) => (e ? reject(e) : resolve())));

console.log(`\n${failures === 0 ? 'ALL PASS' : failures + ' FAILURE(S)'}`);
process.exit(failures === 0 ? 0 : 1);
