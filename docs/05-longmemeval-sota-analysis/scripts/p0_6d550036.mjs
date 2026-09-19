import { readFileSync } from 'node:fs';
const diags = JSON.parse(readFileSync('/workspace/analysis/ab_retry/run_34791592602/mr_diagnostics.json','utf-8'));
const lme = JSON.parse(readFileSync('/tmp/lme-data/lme.json','utf-8'));
const byId = new Map(lme.map(x=>[x.question_id,x]));
const d = diags.find(x=>x.question_id==='6d550036');
const inst = byId.get('6d550036');
const answerIds = new Set(d.answer_session_ids ?? inst.answer_session_ids ?? []);
console.log('question:', d.question);
console.log('gold:', d.ground_truth, ' answer:', d.decision?.answer);
console.log('labelled:', [...answerIds].join(', '));
const ret = String(d.decision?.retrieved ?? '');
// every 'project' mention with surrounding context
const re = /project/gi; let m; const hits=[];
while ((m = re.exec(ret)) !== null) hits.push(m.index);
console.log('project mentions in retrieved:', hits.length);
const seen = new Set();
for (const p of hits) {
  const ctx = ret.slice(Math.max(0,p-180), p+140).replace(/\s+/g,' ');
  const key = ctx.slice(0,60);
  if (seen.has(key)) continue; seen.add(key);
  console.log('  --', ctx);
}
