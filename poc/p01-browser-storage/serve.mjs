/**
 * The static server both drivers use.
 *
 * ## Why it is a file and not a few lines inside run.mjs
 *
 * Two programs need the same routing: the Playwright runner (which also evaluates script) and a
 * WebDriver session that can only navigate. Two copies of "where does /vendor go" would drift,
 * and the drift would look like a browser bug -- the SAH-pool VFS spawns its async proxy worker
 * relative to the document, so a missing `/sqlite3-*` route fails at a place that has nothing to
 * do with the file that moved.
 *
 * ## The one non-obvious route
 *
 * `/sqlite3-*` is mirrored at the origin root on purpose. `@sqlite.org/sqlite-wasm` resolves the
 * proxy worker against the document URL rather than the module URL, so serving it only under
 * `/vendor/` yields a 404 that surfaces as "the VFS never initialises".
 */

import { createServer } from 'node:http';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const VENDOR = join(HERE, '..', 'node_modules', '@sqlite.org', 'sqlite-wasm', 'dist');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.wasm': 'application/wasm',
  '.json': 'application/json',
};

/** Serve the page, the worker and the sqlite-wasm assets from one origin. */
export function serve({ port = 0, host = '127.0.0.1' } = {}) {
  const server = createServer((request, response) => {
    const url = new URL(request.url ?? '/', 'http://localhost');
    let file;
    if (url.pathname === '/' || url.pathname === '/page.html') file = join(HERE, 'page.html');
    else if (url.pathname === '/worker.js') file = join(HERE, 'worker.js');
    else if (url.pathname.startsWith('/vendor/')) {
      const name = normalize(url.pathname.slice('/vendor/'.length)).replace(/^(\.\.[/\\])+/, '');
      file = join(VENDOR, name);
    } else if (url.pathname.startsWith('/sqlite3-')) {
      file = join(VENDOR, url.pathname.slice(1));
    } else if (url.pathname === '/favicon.ico') {
      response.writeHead(204).end();
      return;
    } else {
      response.writeHead(404).end('not found');
      return;
    }
    if (!existsSync(file)) {
      response.writeHead(404).end('missing ' + file);
      return;
    }
    response.writeHead(200, { 'content-type': MIME[extname(file)] ?? 'application/octet-stream' });
    response.end(readFileSync(file));
  });
  return new Promise((resolve) => {
    server.listen(port, host, () => resolve({ server, port: server.address().port }));
  });
}

// Standalone mode, for the WebDriver probe: `node serve.mjs --port 8000`.
if (process.argv[1] && process.argv[1].endsWith('serve.mjs')) {
  const index = process.argv.indexOf('--port');
  const port = index === -1 ? 8000 : Number(process.argv[index + 1]);
  const { port: bound } = await serve({ port, host: '0.0.0.0' });
  console.log(`serving p01 on http://127.0.0.1:${bound}`);
}
