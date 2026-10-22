#!/usr/bin/env node
/**
 * POC-2: what does exact vector search actually cost, and what does the storage dtype buy?
 *
 * ## The claims under test
 *
 * 1. The design originally carried 10-20 ms for an exact cosine scan at 60k turns x 384
 *    dimensions. That was arithmetic (mul-adds / assumed throughput), not measurement.
 * 2. The design recommends storing f32/int8 and widening only the query, on the assumption
 *    that the narrower store is *cheaper*. The memory half of that is obvious; the time half
 *    is not.
 *
 * ## What the first version of this script got wrong, kept here as the method's own lesson
 *
 * The first run reported f32 60k as **37.9 ms** and f64 as 16.2 ms -- the wider store three
 * times faster, which cannot be right. The cause was not the dtype: the top-k used
 * `Array.prototype.sort()` on every candidate that beat the threshold, and that bookkeeping
 * dominated the loop. Rewriting it as an insertion into a fixed-size array moved the same
 * measurement to 17-19 ms for f32. The numbers below are from the corrected implementation,
 * and the earlier pair is quoted in docs/02 section 4 as evidence that a benchmark's
 * *bookkeeping* can masquerade as its algorithm.
 *
 * ## Shapes measured
 *
 * 384 and 1024 dimensions (the two embedding sizes the product can plausibly choose), 20k and
 * 60k turns (the LongMemEval-S window scale), three storage types (f64, f32, int8+scale).
 *
 * ## What this does NOT show
 *
 * Node, not a browser; plain JS, not a wasm-SIMD kernel. A browser tab on the same machine is
 * the comparison, and POC-1 supplies the Chromium numbers. No SIMD means the int8 result here
 * is a *memory* result only: in JS int8 is the slowest of the three per query, and nothing in
 * this script can say how an i8x16 kernel would behave.
 */

import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { bytes, percentile, table } from '../lib/stats.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const RESULTS = join(HERE, '..', 'results');

/** xorshift32: deterministic, so two runs produce the same vectors and the same ranking. */
function rng(seed) {
  let state = seed || 0x9e37_79b9;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 0x1_0000_0000;
  };
}

function unitVector(random, dimensions, ArrayType) {
  const vector = new ArrayType(dimensions);
  let norm = 0;
  for (let index = 0; index < dimensions; index += 1) {
    const value = random() * 2 - 1;
    vector[index] = value;
    norm += value * value;
  }
  const scale = 1 / Math.sqrt(norm);
  for (let index = 0; index < dimensions; index += 1) vector[index] *= scale;
  return vector;
}

function store(random, count, dimensions, ArrayType) {
  const flat = new ArrayType(count * dimensions);
  for (let row = 0; row < count; row += 1) {
    flat.set(unitVector(random, dimensions, ArrayType), row * dimensions);
  }
  return flat;
}

function quantise(flat, count, dimensions) {
  const codes = new Int8Array(count * dimensions);
  const scales = new Float32Array(count);
  for (let row = 0; row < count; row += 1) {
    let max = 0;
    for (let d = 0; d < dimensions; d += 1) {
      max = Math.max(max, Math.abs(flat[row * dimensions + d]));
    }
    const scale = max / 127 || 1;
    scales[row] = scale;
    for (let d = 0; d < dimensions; d += 1) {
      codes[row * dimensions + d] = Math.round(flat[row * dimensions + d] / scale);
    }
  }
  return { codes, scales };
}

const K = 10;

/**
 * Exact top-k by cosine, into a fixed-size insertion buffer.
 *
 * The buffer is why this is fast: `best[k]` is the current threshold, and a candidate that
 * does not beat it costs one comparison. An implementation that sorts on every improvement
 * pays O(k log k) per improvement instead of O(k) on a shift.
 */
function topK(flat, query, count, dimensions, decode) {
  const scores = new Float64Array(K).fill(-Infinity);
  const rows = new Int32Array(K).fill(-1);
  for (let row = 0; row < count; row += 1) {
    let dot = 0;
    const base = row * dimensions;
    for (let d = 0; d < dimensions; d += 1) dot += flat[base + d] * query[d];
    const score = decode === undefined ? dot : dot * decode[row];
    if (score <= scores[K - 1]) continue;
    let slot = K - 1;
    while (slot > 0 && scores[slot - 1] < score) {
      scores[slot] = scores[slot - 1];
      rows[slot] = rows[slot - 1];
      slot -= 1;
    }
    scores[slot] = score;
    rows[slot] = row;
  }
  return { rows: Array.from(rows), scores: Array.from(scores) };
}

const CASES = [
  { count: 20_000, dimensions: 384, kind: 'f64' },
  { count: 20_000, dimensions: 384, kind: 'f32' },
  { count: 20_000, dimensions: 384, kind: 'int8' },
  { count: 60_000, dimensions: 384, kind: 'f64' },
  { count: 60_000, dimensions: 384, kind: 'f32' },
  { count: 60_000, dimensions: 384, kind: 'int8' },
  { count: 60_000, dimensions: 1024, kind: 'f64' },
  { count: 60_000, dimensions: 1024, kind: 'f32' },
  { count: 60_000, dimensions: 1024, kind: 'int8' },
];

const QUERIES = 40;
const rows = [];
const raw = {};

for (const { count, dimensions, kind } of CASES) {
  const random = rng(0x1234_5678);
  const narrow = kind === 'f64' ? null : store(random, count, dimensions, Float32Array);
  const wide = kind === 'f64' ? store(random, count, dimensions, Float64Array) : null;
  const quantised = kind === 'int8' ? quantise(narrow, count, dimensions) : null;
  const queryType = kind === 'f64' ? Float64Array : Float32Array;
  const queries = Array.from({ length: QUERIES }, () => unitVector(random, dimensions, queryType));

  const flat = kind === 'int8' ? quantised.codes : (wide ?? narrow);
  const decode = kind === 'int8' ? quantised.scales : undefined;

  // Two warm-ups: the first call compiles the loop, the second settles the store in cache.
  topK(flat, queries[0], count, dimensions, decode);
  topK(flat, queries[0], count, dimensions, decode);

  const timings = [];
  for (const query of queries) {
    const started = process.hrtime.bigint();
    topK(flat, query, count, dimensions, decode);
    timings.push(Number(process.hrtime.bigint() - started) / 1e6);
  }

  const storedBytes =
    kind === 'f64' ? count * dimensions * 8 : kind === 'f32' ? count * dimensions * 4 : count * dimensions + count * 4;
  const label = `${kind} ${dimensions}d ${(count / 1000).toFixed(0)}k`;
  const p50 = percentile(timings, 0.5);
  const p95 = percentile(timings, 0.95);
  rows.push({
    case: label,
    stored: bytes(storedBytes),
    'p50 ms': p50.toFixed(1),
    'p95 ms': p95.toFixed(1),
    'max ms': Math.max(...timings).toFixed(1),
    'M mul-add': ((count * dimensions) / 1e6).toFixed(1),
  });
  raw[label] = {
    count,
    dimensions,
    kind,
    storedBytes,
    p50Ms: p50,
    p95Ms: p95,
    maxMs: Math.max(...timings),
    mulAddsPerQuery: count * dimensions,
    queries: QUERIES,
    k: K,
  };
  console.log(`${label.padEnd(18)} ${bytes(storedBytes).padStart(9)}  p50 ${p50.toFixed(1).padStart(6)} ms  p95 ${p95.toFixed(1).padStart(6)} ms`);
}

const markdown = [
  table(rows, ['case', 'stored', 'p50 ms', 'p95 ms', 'max ms', 'M mul-add']),
  '',
  `Exact top-${K} cosine over the whole store, ${QUERIES} queries per row, two warm-up scans`,
  `discarded, insertion-buffer top-k. Node ${process.version} on ${process.arch}, one thread,`,
  'plain JS (no wasm SIMD).',
  '',
  'The dtype trade is a **memory** trade, not a time trade: at 384d the three types are within',
  '25% of each other per query, while the store is 176 MiB / 88 MiB / 22 MiB. int8 is the',
  '*slowest* here because JS has no i8x16 dot product; its case rests on fitting in cache and in',
  'a browser heap, not on throughput.',
].join('\n');

writeFileSync(
  join(RESULTS, 'p02-vector-scan.json'),
  JSON.stringify({ generatedAt: new Date().toISOString(), node: process.version, raw }, null, 2),
);
writeFileSync(join(RESULTS, 'p02-vector-scan.md'), markdown + '\n');
console.log('\n' + markdown);
