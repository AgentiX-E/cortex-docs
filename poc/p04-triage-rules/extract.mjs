#!/usr/bin/env node
/**
 * Extract candidate *facts* from real assistant-conversation turns.
 *
 * ## Where the corpus comes from
 *
 * `corpus.json` is a frozen, deduplicated set of user turns from LongMemEval-S, taken from a
 * benchmark artifact this project already owns (run `39699987781`). Using the artifact rather
 * than the upstream dataset keeps this POC reproducible without a Hugging Face token, and it
 * keeps the text exactly as the product saw it -- role prefix included, which is what the
 * extractor has to strip.
 *
 * ## Why extraction is heuristic and not a model
 *
 * The design (docs/13) puts extraction on the model and disclosure on the rules. This script
 * is the *ruler* for the disclosure layer, so it must not itself be a model: a model-based
 * extractor would make the measurement circular. The heuristic below is deliberately crude --
 * first-person marker, no question mark, a stative or event predicate -- and its recall is
 * therefore a floor, not a ceiling. The POC measures the rule layer on what it caught, and
 * says so.
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

const FIRST_PERSON = /\b(i|i'm|i've|i'd|i'll|my|mine|me)\b/i;
const STATIVE =
  /\b(have|has|own|owns|live|lives|moved|work|works|bought|buy|paid|pay|lost|found|started|finished|planning|plan|booked|joined|attended|led|leading|switched|cancelled|signed|adopted|diagnosed|allergic|vegan|vegetarian)\b/i;
const NOT_FACT = /^(can you|could you|what|how|why|when|where|who|which|do you|does|is |are |should|would|will|please|thanks|thank)\b/i;

/** One sentence per line, split on sentence punctuation but not on decimals or times. */
function sentences(text) {
  return text
    .replace(/([.!?])\s+/g, '$1\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Strip the `[date] role:` prefix the dataset writes. */
function body(text) {
  const match = /^\[[^\]]+\]\s*(?:user|assistant):\s*([\s\S]*)$/.exec(text);
  return (match ? match[1] : text).replace(/\s+/g, ' ').trim();
}

export function candidates(turns) {
  const seen = new Set();
  const found = [];
  for (const turn of turns) {
    for (const sentence of sentences(body(turn))) {
      if (sentence.length < 40 || sentence.length > 240) continue;
      if (!FIRST_PERSON.test(sentence)) continue;
      if (sentence.includes('?')) continue;
      if (NOT_FACT.test(sentence)) continue;
      if (!STATIVE.test(sentence)) continue;
      const key = sentence.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(sentence);
    }
  }
  return found;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const corpus = JSON.parse(readFileSync(join(HERE, 'corpus.json'), 'utf8'));
  const found = candidates(corpus.turns);
  console.log(`${corpus.turns.length} turns -> ${found.length} candidate facts`);
  for (const [index, sentence] of found.slice(0, 12).entries()) {
    console.log(`  ${String(index).padStart(3)} ${sentence.slice(0, 150)}`);
  }
  writeFileSync(join(HERE, 'candidates.json'), JSON.stringify({ generatedAt: new Date().toISOString(), candidates: found }, null, 2));
}
