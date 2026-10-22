/**
 * Verify the R4 cohort guard against the REAL dataset at the dispatch limit.
 *
 * The guard is only useful if `LIMIT=200` actually satisfies it and `LIMIT=60`
 * actually trips it. This script reproduces the bench's sampling + scoping
 * pipeline (sampler -> capability filter -> cohort coverage) against
 * `/tmp/lme-data/lme.json` and prints the verdict, so the dispatch decision is
 * made on the real distribution rather than on a fixture that happens to agree.
 *
 * Keep this in sync with `sampleInstances` and `cohortCoverage`; the point is to
 * confirm the two compose as the benchmark will actually run them.
 */
import { readFileSync } from 'node:fs';

const inst = JSON.parse(readFileSync('/tmp/lme-data/lme.json', 'utf8'));

const TYPE_TO_CAP = {
  'single-session-user': 'IE',
  'single-session-assistant': 'IE',
  'single-session-preference': 'IE',
  'temporal-reasoning': 'TR',
  'knowledge-update': 'KU',
  'multi-session': 'MR',
};
const toCapability = (id, type) => (id.endsWith('_abs') ? 'ABS' : (TYPE_TO_CAP[type] ?? 'IE'));
const bucketKey = (i) => {
  const c = toCapability(i.question_id, i.question_type);
  return c === 'IE' ? `IE:${i.question_type}` : c;
};

function sampleInstances(list, limit) {
  if (limit <= 0 || limit >= list.length) return [...list];
  const buckets = new Map();
  for (const i of list) {
    const k = bucketKey(i);
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(i);
  }
  const keys = [...buckets.keys()];
  const out = [];
  let cursor = 0;
  while (out.length < limit) {
    const k = keys[cursor % keys.length];
    const n = buckets.get(k).shift();
    if (n) out.push(n);
    cursor++;
  }
  return out;
}

const COHORT = [
  '6456829e_abs',
  'edced276_abs',
  'e5ba910e_abs',
  'gpt4_70e84552_abs',
  'gpt4_c27434e8_abs',
  'gpt4_fe651585_abs',
  '80ec1f4f_abs',
];
const SCOPE = ['ABS', 'IE'];

function coverageOf(sample) {
  const inScope = sample.filter((i) => SCOPE.includes(toCapability(i.question_id, i.question_type)));
  const ids = new Set(inScope.map((i) => i.question_id));
  const present = COHORT.filter((id) => ids.has(id));
  const missing = COHORT.filter((id) => !ids.has(id));
  return { present, missing, ratio: present.length / COHORT.length };
}

console.log('R4 cohort guard, evaluated against the real dataset.\n');
console.log(' LIMIT | scoped | covered | guard verdict');
for (const limit of [60, 100, 150, 200, 250, 300, 0]) {
  const sample = sampleInstances(inst, limit);
  const cov = coverageOf(sample);
  const scoped = sample.filter((i) =>
    SCOPE.includes(toCapability(i.question_id, i.question_type)),
  ).length;
  const verdict =
    cov.missing.length === 0 ? 'PASS (runs)' : `THROW (missing ${cov.missing.length})`;
  console.log(
    `${String(limit === 0 ? 'all' : limit).padStart(6)} | ${String(scoped).padStart(6)} | ` +
      `${String(cov.present.length + '/7').padStart(7)} | ${verdict}`,
  );
  if (limit === 200 || limit === 60) {
    if (cov.missing.length) console.log(`        missing: ${cov.missing.join(', ')}`);
  }
}

console.log('\nExpected arm cost in retrieval work (turn count, the embedding driver):');
for (const limit of [60, 200]) {
  const sample = sampleInstances(inst, limit);
  const turns = sample.reduce(
    (a, s) => a + (s.haystack_sessions ?? []).reduce((x, ss) => x + ss.length, 0),
    0,
  );
  console.log(`  LIMIT=${String(limit).padStart(3)}: ${String(turns).padStart(6)} turns`);
}
