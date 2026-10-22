/**
 * Post-fix verification against the BUILT `dist/`, not the source.
 *
 * Scope check for the KU no-qualifier fix. The new Step 2 branch is only
 * reachable for questions that `classifyKnowledgeUpdateQualifier` labels
 * `'other'`: the routing guard in `answerKnowledgeUpdate` is
 * `qualifier !== 'other'`, so a `'previous'`/`'current'` question takes the
 * bitemporal path instead and never sees this prompt. A question like
 * "What new kitchen gadget did I invest in BEFORE getting the Air Fryer?" is
 * classified `'previous'` and is therefore OUT OF SCOPE for this fix, even
 * though it is one of the observed abstentions.
 *
 * This reports, per real LongMemEval-S question, whether the fix can reach it.
 */
import { readFileSync } from 'node:fs';
import { classifyKnowledgeUpdateQualifier } from '/workspace/cortex/packages/cortex-eval/dist/fact-store.js';
import { buildKnowledgeUpdatePrompt } from '/workspace/cortex/packages/cortex-eval/dist/natural-language-memory.js';

const RUN = '/workspace/analysis/ab_tr_two_event/treatment/run_33902273327';
const records = JSON.parse(
  readFileSync(`${RUN}/benchmark-single-session-diagnostics.json`, 'utf8'),
).filter((r) => r.capability === 'KU' && r.decision?.abstained === true);

console.log('=== KU abstentions: which ones can the fix actually reach? ===\n');
let inScope = 0;
let outOfScope = 0;
for (const r of records) {
  const q = classifyKnowledgeUpdateQualifier(r.question);
  const prompt = buildKnowledgeUpdatePrompt(r.question, 'ctx');
  const reaches = q === 'other';
  const hasRule = prompt.includes('NO time qualifier');
  const hasGuard = prompt.includes('NOT a reason to abstain');
  if (reaches) inScope += 1;
  else outOfScope += 1;
  console.log(
    `${reaches ? 'IN-SCOPE ' : 'out      '} [${q.padEnd(8)}] rule=${hasRule ? 'Y' : 'n'} guard=${hasGuard ? 'Y' : 'n'}  ` +
      `${r.question.slice(0, 78)}`,
  );
}
console.log(
  `\nIN-SCOPE (reached by the fix): ${inScope}/${records.length}   out of scope: ${outOfScope}`,
);
console.log(
  'Note: hasRule/hasGuard are properties of the prompt builder and are true for',
  'every question; the discriminator is the qualifier, which decides routing.',
);
