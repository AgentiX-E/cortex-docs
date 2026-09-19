/**
 * The abstention contract was enforced for MR in 236ab1b ("enforce the MR
 * abstention contract instead of trusting the prompt"). This asks whether the
 * other capabilities still abstain at MR's old rate -- i.e. whether the fix was
 * scoped too narrowly.
 *
 * The benchmark reports abstention rate 9.40% and abstention CORRECT rate
 * 55.32%, so roughly 21 of the 74 failures are declines that should have been
 * answers. Locating them by capability decides where the next iteration goes.
 */

import { readFileSync } from 'node:fs';

const BASE = '/workspace/analysis/ab_retry/run_34791592602';
const load = (p) => JSON.parse(readFileSync(p, 'utf-8'));
const all = [...load(`${BASE}/MR_diagnostics.json`), ...load(`${BASE}/Single-session_diagnostics.json`)];

const capOf = (d) => d.capability ?? (String(d.question_id).endsWith('_abs') ? 'ABS' : 'MR');

console.log('cap    n    abstained  abst%    abst-that-were-WRONG   share of that cap failures');
let totAbst = 0;
let totWrongAbst = 0;
for (const c of ['IE', 'MR', 'KU', 'TR', 'ABS']) {
  const g = all.filter((d) => capOf(d) === c);
  const ab = g.filter((d) => (d.decision ?? {}).abstained);
  const wrongAbst = ab.filter((d) => !d.correct);
  const wrong = g.filter((d) => !d.correct).length;
  totAbst += ab.length;
  totWrongAbst += wrongAbst.length;
  console.log(
    `${c.padEnd(4)} ${String(g.length).padStart(4)}  ${String(ab.length).padStart(6)}  ${((ab.length / g.length) * 100).toFixed(2).padStart(6)}%  ${String(wrongAbst.length).padStart(10)}            ${((wrongAbst.length / wrong) * 100).toFixed(0).padStart(3)}% of ${wrong}`
  );
}
console.log(`\ntotal abstentions ${totAbst} (${((totAbst / all.length) * 100).toFixed(2)}%), of which WRONG ${totWrongAbst}`);

// A wrongful abstention is only a bug if the evidence was present. Reuse the
// strict turn-text test so the number is not inflated by genuine missing recall.
const LME = JSON.parse(readFileSync('/tmp/lme-data/lme.json', 'utf-8'));
const meta = new Map(LME.map((x) => [x.question_id, x]));
const SHINGLE = 30;
const SAMPLES = 24;
const turnPresent = (t, ret) => {
  const s = t.replace(/\s+/g, ' ');
  if (s.length < SHINGLE) return ret.includes(s);
  const step = Math.max(1, Math.floor((s.length - SHINGLE) / SAMPLES));
  for (let i = 0; i < s.length - SHINGLE; i += step) if (ret.includes(s.slice(i, i + SHINGLE))) return true;
  return false;
};

console.log('\nwrongful abstentions, by whether the labelled evidence reached the prompt:');
let withEvidence = 0;
const rows = [];
for (const d of all) {
  if (!(d.decision ?? {}).abstained || d.correct) continue;
  const inst = meta.get(d.question_id);
  const ids = d.answer_session_ids ?? inst?.answer_session_ids ?? [];
  const idsAll = inst?.haystack_session_ids ?? [];
  const sessions = inst?.haystack_sessions ?? [];
  const ret = String((d.decision ?? {}).retrieved ?? '');
  let strict = 0;
  for (const id of ids) {
    const k = idsAll.indexOf(id);
    if (k < 0) continue;
    const turns = sessions[k] ?? [];
    const texts = Array.isArray(turns)
      ? turns.map((u) => String(u?.content ?? ''))
      : Object.values(turns).map((u) => String(u?.content ?? ''));
    if (texts.some((t) => t.length > 0 && turnPresent(t, ret))) strict++;
  }
  const cap = capOf(d);
  if (strict > 0) withEvidence++;
  rows.push({ id: d.question_id, cap, strict, n: ids.length });
}
console.log(`  evidence present (at least one answer turn): ${withEvidence} of ${rows.length}`);
const byCap = {};
for (const r of rows) (byCap[r.cap] ??= []).push(r);
for (const c of Object.keys(byCap).sort()) {
  const g = byCap[c];
  console.log(
    `    ${c.padEnd(4)} ${String(g.length).padStart(3)} wrongful abstentions, ${g.filter((r) => r.strict > 0).length} with evidence present`
  );
}
console.log('\n-- the ones WITH evidence (the defendable bugs) --');
for (const r of rows.filter((r) => r.strict > 0).sort((a, b) => a.cap.localeCompare(b.cap))) {
  console.log(`   ${r.cap}  ${r.id}  ${r.strict}/${r.n} answer sessions present`);
}
