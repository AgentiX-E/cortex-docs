#!/usr/bin/env node
/** Inspect the ABS row shape to find where the evidence text actually lives. */
import { readFileSync } from 'node:fs';
const dir = process.argv[2];
const rows = JSON.parse(readFileSync(`${dir}/Single-session_diagnostics.json`, 'utf8'));
console.log('total rows', rows.length);
console.log('capabilities', [...new Set(rows.map((r) => r.capability))]);
const abs = rows.filter((r) => r.capability === 'ABS');
console.log('abs rows', abs.length);
if (abs.length === 0) {
  console.error('no ABS rows; capability labels are:', [...new Set(rows.map((r) => r.capability))]);
  process.exit(1);
}
const r = abs.find((x) => x.correct === false) ?? abs[0];
console.log('\n--- top-level keys ---');
console.log(Object.keys(r));
console.log('\n--- decision keys ---');
console.log(Object.keys(r.decision ?? {}));
console.log('\n--- answer_sessions_content type ---', typeof r.answer_sessions_content);
// The point of this script: on ABS rows these fields are UNDEFINED. Any claim of
// the form "the evidence session of an ABS question was fully admitted" is
// therefore not derivable from the artifact, which is why P23 §3 was retracted.
for (const key of ['answer_sessions_content', 'answer_session_ids', 'haystack_dates']) {
  console.log(`  ${key}: ${typeof r[key]}`);
}
console.log('\n--- ground_truth ---', JSON.stringify(r.ground_truth)?.slice(0, 300));
console.log('\n--- decision.retrieved type ---', typeof r.decision?.retrieved);
console.log('len', Array.isArray(r.decision?.retrieved) ? r.decision.retrieved.length : String(r.decision?.retrieved ?? '').length);
console.log('preview:', JSON.stringify(r.decision?.retrieved)?.slice(0, 500));
console.log('\n--- decision.reason ---', JSON.stringify(r.decision?.reason)?.slice(0, 400));
console.log('\n--- decision.abstained ---', r.decision?.abstained);
console.log('\n--- decision top1Score ---', r.decision?.top1Score);
