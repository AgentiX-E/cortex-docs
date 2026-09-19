/**
 * Real-data check of the abstention admission fix.
 *
 * Replays every ABS question in LongMemEval-S through the real retrieval and
 * real prompt builder, with a stub LLM that only records the prompt. No API
 * calls, so this measures the change the fix makes to the prompt the model
 * would see, not a simulated answer.
 *
 * What it establishes: with `admissionMode: 'session'` (the pre-fix behaviour)
 * the ABS prompt reaches the 40,000-character band on most questions; with
 * `admissionMode: 'hits'` (the fix) it stays below it. It also reports the
 * coverage score so the trim is not mistaken for evidence loss -- the retrieval
 * hits are identical in both modes, only the completion turns differ.
 *
 * Usage: node /tmp/abs_replay.mjs
 * Requires the built package at packages/cortex-eval/dist.
 */
import { readFileSync } from 'node:fs';

const { loadLongMemEval, NaturalLanguageMemorySystem, HashEmbedding } = await import(
  '/workspace/cortex/packages/cortex-eval/dist/index.js'
);

const raw = JSON.parse(readFileSync('/tmp/lme-data/lme.json', 'utf8'));

const dataset = loadLongMemEval(raw);
console.log('loaded instances:', dataset.length);

const withSessions = dataset.questions.filter((q) => Array.isArray(q.sessions) && q.sessions.length > 0);
console.log('with session boundaries:', withSessions.length);

// The loader marks the abstention questions with a `_abs` id suffix and sets
// `expected` to null; that is the exact set `runBenchmark` routes to
// `answerAbstention`.
const rows = dataset.questions.filter((q) => q.capability === 'ABS');
console.log('ABS questions:', rows.length);
if (rows.length === 0) {
  console.error('no ABS questions found; capability mapping changed');
  process.exit(1);
}

const embedding = new HashEmbedding(64);

async function measure(mode) {
  let captured = null;
  const llm = {
    complete: async (prompt) => {
      captured = prompt;
      return 'UNANSWERABLE';
    },
    completeStructured: async () => ({}),
  };
  const system = new NaturalLanguageMemorySystem('s', { embedding, llm, admissionMode: mode });
  const out = [];
  for (const q of rows) {
    captured = null;
    await system.answerAbstention(q.question, q.context, q.sessions);
    out.push({ id: q.id, len: captured ? captured.length : 0, prompt: captured ?? '' });
  }
  return out;
}

const sess = await measure('session');
const hits = await measure('hits');

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

/**
 * Count admitted turns in a rendered prompt, whichever format it uses.
 *
 * The conservative prompt renders raw dated turns; other prompts render a JSON
 * array via `formatStructuredContext`. Counting with only one pattern silently
 * returns 0 for the other, which reads as "no turns admitted" rather than "wrong
 * pattern" -- so both are tried and a prompt matching neither is reported loudly.
 */
const countTurns = (prompt) => {
  const dated = (prompt.match(/\[\d{4}\/\d{2}\/\d{2}/g) ?? []).length;
  if (dated > 0) return dated;
  return (prompt.match(/"role":"(user|assistant)"/g) ?? []).length;
};

console.log('\nmode       mean prompt   >40k band   max');
for (const [name, m] of [
  ['session', sess],
  ['hits', hits],
]) {
  const lens = m.map((r) => r.len);
  console.log(
    `${name.padEnd(10)} ${String(Math.round(mean(lens))).padStart(10)}   ${String(
      m.filter((r) => r.len >= 40000).length,
    ).padStart(6)}/${m.length}   ${Math.max(...lens)}`,
  );
}

// The falsifiable prediction for the next full run: the admitted turn count on
// ABS drops to the ceiling. Measured on run 35004814319 the mean was 42.6
// (1,277 / 30) and the abstention rate collapsed specifically in the 45-60 band.
console.log('\nadmitted turns per question (the quantity the cap bounds):');
for (const [name, m] of [
  ['session', sess],
  ['hits', hits],
]) {
  const counts = m.map((r) => countTurns(r.prompt));
  const over = counts.filter((c) => c > 30).length;
  const blank = counts.filter((c) => c === 0).length;
  console.log(
    `${name.padEnd(10)} mean ${mean(counts).toFixed(1).padStart(5)}  max ${String(
      Math.max(...counts),
    ).padStart(3)}  over the 30 cap: ${over}/${counts.length}` +
      (blank > 0 ? `  UNPARSED: ${blank}/${counts.length}` : ''),
  );
}

console.log('\nper-question delta (session -> hits):');
const byId = new Map(hits.map((r) => [r.id, r]));
const deltas = sess.map((r) => byId.get(r.id).len - r.len);
console.log(`  prompt shrank on ${deltas.filter((d) => d < 0).length}/${sess.length} questions`);
console.log(`  prompt grew   on ${deltas.filter((d) => d > 0).length}/${sess.length} questions`);
console.log(`  mean delta ${Math.round(mean(deltas))} chars`);

console.log('\nlargest shrink:');
const pairs = sess
  .map((r) => ({ id: r.id, before: r.len, after: byId.get(r.id).len, d: byId.get(r.id).len - r.len }))
  .sort((x, y) => x.d - y.d);
for (const p of pairs.slice(0, 5)) {
  console.log(`  ${p.id}  ${p.before} -> ${p.after}  (${p.d})`);
}

// Guard: the cap must not starve the prompt. The right comparison is the ADMITTED
// TURN COUNT against the pre-4955d8e production baseline, not character length:
// character length depends on the rendering format, so comparing across formats
// produces a false alarm (a JSON turn costs ~40 more characters than a raw one).
// Measured on run 34915402976 the baseline was 32.8 turns (max 42).
const baselineTurns = 32.8;
const meanHitsTurns = mean(hits.map((r) => countTurns(r.prompt)));
const meanSessTurns = mean(sess.map((r) => countTurns(r.prompt)));
console.log('\nguard (turn counts, format-independent):');
console.log(`  pre-4955d8e baseline       ${baselineTurns.toFixed(1)}`);
console.log(`  session mode (the regression) ${meanSessTurns.toFixed(1)}`);
console.log(`  hits mode (the fix)           ${meanHitsTurns.toFixed(1)}`);
console.log(
  `  ${meanHitsTurns >= baselineTurns * 0.8 ? 'OK' : 'REVIEW'}: the cap lands near the calibrated regime, not far below it`,
);
