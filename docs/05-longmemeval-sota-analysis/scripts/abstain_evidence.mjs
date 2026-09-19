/**
 * Evidence locator for abstained questions whose gold answer IS present in the
 * retrieved context.
 *
 * An earlier version of this indexed the NORMALISED string but sliced the RAW
 * one; normalisation strips punctuation and collapses whitespace, so the two
 * index spaces do not correspond and every printed snippet was offset. The
 * membership test was unaffected, but the evidence display was not evidence.
 *
 * This builds a regex from the gold that tolerates arbitrary whitespace and
 * punctuation between words, so it locates the true span in the raw context and
 * reports the enclosing TURN (the `[YYYY/MM/DD ...]` line), which is the unit
 * the prompt actually feeds the model.
 */
import { readFileSync } from 'node:fs';

const RUN = process.argv[2] ?? 'run_33902273327';
const ROOT = `/workspace/analysis/ab_tr_two_event/treatment/${RUN}`;

const single = JSON.parse(readFileSync(`${ROOT}/benchmark-single-session-diagnostics.json`, 'utf8'));
const mr = JSON.parse(
  readFileSync(`${ROOT}/benchmark-mr-diagnostics.json`, 'utf8'),
).map((r) => ({ ...r, capability: 'MR' }));
const all = [...single, ...mr];

/** Regex matching the gold with flexible whitespace/punctuation between tokens. */
function goldRegex(gold) {
  const toks = String(gold)
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (toks.length === 0) return null;
  return new RegExp(toks.join('[^A-Za-z0-9]{0,4}'), 'i');
}

/** The `[YYYY/MM/DD ...]` turn containing `index`, or a fixed-size window. */
function enclosingTurn(ctx, index, spanLen) {
  const turns = [];
  const re = /\[\d{4}\/\d{2}\/\d{2}[^\]]*\]/g;
  let m;
  while ((m = re.exec(ctx)) !== null) turns.push(m.index);
  let start = 0;
  let end = ctx.length;
  for (let i = 0; i < turns.length; i += 1) {
    if (turns[i] <= index) start = turns[i];
    if (turns[i] > index) {
      end = turns[i];
      break;
    }
  }
  return ctx.slice(start, Math.min(ctx.length, end)).replace(/\s+/g, ' ').trim();
}

const rows = [];
for (const r of all) {
  if (!r.decision || r.decision.abstained !== true) continue;
  const gold = r.ground_truth;
  if (gold === null || gold === undefined || String(gold).trim() === '') continue;
  const ctx = String(r.decision.retrieved ?? '');
  const re = goldRegex(gold);
  if (!re) continue;
  const m = re.exec(ctx);
  if (!m) continue;
  rows.push({
    capability: r.capability,
    question_id: r.question_id,
    top1Score: r.decision.top1Score,
    question: r.question,
    gold: String(gold),
    answer: r.decision.answer,
    turn: enclosingTurn(ctx, m.index, m[0].length),
  });
}

console.log(`run ${RUN}: abstained with gold verbatim in context = ${rows.length}`);
for (const r of rows) {
  console.log('='.repeat(110));
  console.log(`[${r.capability}] ${r.question_id}  top1Score=${r.top1Score?.toFixed(4) ?? 'n/a'}`);
  console.log(`Q    : ${r.question}`);
  console.log(`GOLD : ${JSON.stringify(r.gold)}`);
  console.log(`ANS  : ${JSON.stringify(r.answer)}`);
  console.log(`EVID : ${r.turn.slice(0, 400)}`);
}
