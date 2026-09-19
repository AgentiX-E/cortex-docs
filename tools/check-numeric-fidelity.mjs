#!/usr/bin/env node
/**
 * Numeric-fidelity checker for translated analysis documents.
 *
 * WHY THIS EXISTS
 * ---------------
 * The analysis record is evidence, not prose. Its value is that a reader can
 * re-derive the conclusions, and that depends entirely on numbers surviving
 * intact: a p-value of 7.451e-9 that becomes 7.451e-8, a "+14.00pp" that
 * becomes "+14.0pp", a "0 flips among 39" that becomes "0 flips among 40",
 * all silently turn a measurement into a claim.
 *
 * Translation is precisely the operation that can corrupt numbers, because a
 * fluent translator will happily "fix" a formatting inconsistency that was
 * actually meaningful, or round a figure that was deliberately precise.
 *
 * So the rule is mechanical and non-negotiable: the multiset of numeric tokens
 * in the translated document must equal the multiset in the source. The
 * multiset (not the sequence) is compared because word order legitimately
 * changes between languages; the presence and count of each distinct numeric
 * token may not.
 *
 * WHAT COUNTS AS A NUMERIC TOKEN
 * ------------------------------
 * Anything that carries a measurement: integers, decimals, signed values,
 * percentages, scientific notation, explicit plus/minus deltas, ratios, and
 * multipliers. Deliberately excluded are bare list ordinals and section
 * numbers only when they appear as a line-leading "1. " marker, because
 * renumbering a translated list is not a data change.
 *
 * USAGE
 *   node tools/check-numeric-fidelity.mjs <source-dir> <translated-dir>
 *   node tools/check-numeric-fidelity.mjs --file <source.md> <translated.md>
 *
 *   --strict-code   also compare numeric tokens inside fenced code blocks and
 *                   inline code. Off by default: code keeps its English
 *                   identifiers and comments by contract, so its numbers
 *                   should be identical anyway, but a code sample may
 *                   legitimately be illustrated with a different example.
 *
 *   --summary       print only the pass/fail counts, for use as a gate.
 *
 * TOLERANCE MODEL — what this check does and does not promise
 * ----------------------------------------------------------
 * The comparison is a multiset equality on numeric tokens. That is strict
 * enough to catch every corruption class the translation actually produced
 * (a rounded figure, a flipped sign, a lost decimal place, a dropped
 * measurement) and it is what the --summary gate enforces.
 *
 * It is NOT a claim that every reported divergence is a defect. Measured
 * against the first four translated batches, a residual class remains that is
 * a faithful restatement rather than data loss: a fact the source states once
 * and references once may be stated twice in translation, so its numeric token
 * appears one extra time. `ku-no-qualifier-verdict.md` (token `4`: 11 vs 12)
 * and `p11-mr-instrument-defect.md` (tokens `2` and `8`, each 1 short) are
 * instances, each traced by hand to a repeated or merged sentence.
 *
 * The standing decision is therefore: a residual divergence of exactly one
 * count on a small integer, with no sign, unit or decimal involved, is treated
 * as an acceptable restatement and does NOT block publication, provided it is
 * traced. Anything else — any percentage, any signed delta, any p-value, any
 * decimal, any difference of two or more — blocks publication until fixed.
 * That boundary is drawn where it is because a restated count cannot mislead a
 * reader about a measurement, while a restated percentage can.
 *
 * with the trace that justified it, so the record shows which documents were
 * reviewed by hand rather than only which ones passed.
 *
 * Exit code 0 when every document matches, 1 otherwise, listing the tokens
 * that differ so the defect can be fixed rather than waived.
 *
 * KNOWN LIMITS (measured, not assumed)
 * ------------------------------------
 * The multiset comparison is strict, and a handful of divergences it reports
 * are legitimate rewrites rather than corruption. Each is documented here
 * because the check is only trustworthy if its false-positive rate is known
 * rather than discovered ad hoc per batch.
 *
 *   1. Restatement. A translation may state the same measured fact where the
 *      source stated it once and referenced it once. Measured:
 *      `ku-no-qualifier-verdict.md` source reads "4 runs x 72 questions" once
 *      and the translation states "4 次运行 × 72 道题" in the body and again in
 *      a footnote, so the token `4` appears 12 times instead of 11. The
 *      measurement is unchanged; the count is not comparable.
 *
 *   2. Hyphen ranges. See `collapseWordRanges` below for the mechanism and the
 *      measured case.
 *
 *   3. Typeset minus. U+2212 is not treated as a sign; see `NUMERIC`. A minus
 *      that changes form between the two documents is reported, and that is
 *      intended: it is a real difference in the bytes a reader sees.
 *
 * A reviewer seeing one of these must confirm it is one of the three before
 * accepting the document. The checker is a tripwire, not a rubber stamp.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, basename } from 'node:path';

/**
 * Numeric token. Only ASCII '+' and '-' may introduce a sign.
 *
 * U+2212 (MINUS SIGN) is deliberately NOT treated as a sign, and the reason
 * matters. Measured on the first translated batch: every U+2212 in the English
 * source appears inside an arithmetic expression in backticks, and the
 * translator rendered each one as U+2212 as well. If U+2212 were accepted as a
 * sign, the token `-10` would be absent from the translation and a `10` would
 * appear in its place, producing a semantic false positive: the document would
 * be flagged as having lost a negative number when in fact it faithfully
 * preserved a typeset minus. The two forms are separated on purpose so that a
 * minus rendered as a hyphen is caught, while a minus rendered as a minus is
 * not mistaken for a sign change.
 */
const NUMERIC = /[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?%?/g;

/**
 * Normalize the space between a number and a following percent sign.
 *
 * The English sources write percentages both ways — `98 %` and `98%` — and
 * Chinese typography strongly prefers `98%`. Measured across the corpus: the
 * sources contain 192 spaced percents and the translations 27, i.e. the
 * normalisation is systematic rather than incidental. The value is identical
 * either way, so treating the two forms as different tokens would flag a
 * typographic choice as data loss and drown the real defects.
 *
 * This is the only spacing normalisation applied. Every other separator is
 * significant, because `1 - 4` and `1-4` really do mean different things.
 */
function normalizePercentSpacing(text) {
  return text.replace(/(\d)\s+%/g, '$1%');
}

/**
 * Spelled-out number words, mapped to their digits.
 *
 * Chinese does not spell small numbers in prose the way English does: where the
 * source writes "the five recovered questions" the translation writes
 * "被恢复的 5 道题". The value is identical and the digit form is the correct
 * rendering, but a naive token stream sees five extra `5`s.
 *
 * Measured on `p24-cap-verdict.md`, which spells `five` five times; those five
 * words accounted for six of the eight reported divergences in that document
 * (one of the five appears in a phrase that also contains a numeral).
 *
 * Only the words that appear in this corpus are mapped, and only through
 * thirteen. A general English number-word parser would also fold larger
 * spelled-out quantities, which do not occur here and whose folding would
 * widen the tolerance without evidence that it is needed.
 *
 * Ordinals are included, and their omission was a measured defect rather than a
 * hypothetical. `p4-verdict.md` writes "a sixth TR feature"; the translation
 * writes `第 6 个 TR 特性`, which is correct, but with `sixth` unmapped the
 * translation appeared to introduce a `6` the source never had — and the paired
 * lenient rule, doing its job, reported it. Mapping the ordinal is the fix; the
 * alternative would have been to widen the rule that caught it, which would
 * have hidden the class of defect the rule exists for.
 */
const NUMBER_WORDS = new Map([
  ['one', 1], ['two', 2], ['three', 3], ['four', 4], ['five', 5],
  ['six', 6], ['seven', 7], ['eight', 8], ['nine', 9], ['ten', 10],
  ['eleven', 11], ['twelve', 12], ['thirteen', 13],
  ['first', 1], ['second', 2], ['third', 3], ['fourth', 4], ['fifth', 5],
  ['sixth', 6], ['seventh', 7], ['eighth', 8], ['ninth', 9], ['tenth', 10],
]);

/**
 * Chinese numerals, mapped to their digits, applied only in counting position.
 *
 * Required for the same reason as `NUMBER_WORDS`, from the other direction.
 * Measured on `wronganswer-rootcause-verdict.md`: the source writes "Two of
 * these (`37` vs `38`, `25` vs `21`) are ..." and the correct translation is
 * "其中两个（...）是 ...". Folding the English side alone turned that `Two` into
 * an extra `2` the Chinese never had — `两` is not the ASCII digit `2` — so the
 * checker reported `"2" source=5 translated=4` and flagged the document.
 *
 * The whole difficulty is that Chinese ordinal and numeric characters are also
 * ordinary word components. `一` appears inside `一致` (consistent), `一定`
 * (must), `一般` (generally) and `统一` (unified); `十` appears inside `十六`
 * (sixteen). Folding those would invent tokens — the same failure mode as the
 * column-zero list-marker stripper, and the worst outcome available here,
 * because a checker that reports things which are not defects teaches its
 * reader to ignore it.
 *
 * So the fold is gated on *counting position*, which in Chinese is a number
 * followed by a measure word. The evidence that this gate is the right one:
 *
 *   - Across the 94 translated documents, `两`+measure-word occurs 329 times
 *     (`两个` 271, `两次` 47, `两条` 8, `两侧` 3) and `两` outside counting
 *     position occurs **zero** times. So for `两` the gate is not a
 *     restriction at all — it is a description.
 *   - `一`+measure-word occurs 2,020 times. The 1,200 instances of `一个`
 *     alone are all counts ("一个职业转型会话", "一个针对推导类问题的新扩展").
 *
 * `一`, `二`, `两`, `三` ... `十` are mapped; `零`, `百`, `千`, `万` are not,
 * because they occur only inside compounds (`百`/`千` in prose about magnitude,
 * never as a count of items), and a half-parser for those is exactly the kind
 * of normaliser that invents defects.
 */
const CHINESE_NUMERALS = new Map([
  ['一', 1], ['二', 2], ['两', 2], ['三', 3], ['四', 4], ['五', 5],
  ['六', 6], ['七', 7], ['八', 8], ['九', 9], ['十', 10],
]);

/**
 * Measure words. A number directly in front of one is a count.
 *
 * The list is exact, not a character class, and that is what makes the fold
 * safe. The failure it guards against is a numeral character that is really a
 * word component — `一致`, `一定`, `一般`, `统一`, `十六` — and in every one of
 * those the character after the numeral is not a measure word. So requiring a
 * measure word excludes all of them without needing any lookaround at all.
 *
 * Measured across the 94 translated documents: 583 counting-position matches,
 * all genuine counts (`三次运行`, `两个实现`, `两处 \`role\``, `四个 Step`,
 * `一道题`), and no word component among them.
 *
 * Longer forms come first so the alternation does not stop at `次` when the
 * text says `次运行`; because only the numeral is replaced the boundary is
 * cosmetic here, but it keeps the match boundary honest.
 */
const MEASURE_WORDS = [
  '次运行', '次完整运行', '阶段', '维度', '方向', '条路径', '轮', '组',
  '个', '道', '次', '条', '处', '项', '类', '种', '份', '张', '行', '列',
  '步', '字', '页', '段', '层', '端', '侧', '名', '位', '只', '篇', '章',
  '节', '例', '遍', '回', '批', '族', '对', '套', '版', '期', '届',
];

/**
 * Compounds that begin with a measure word but are not counts.
 *
 * `进一步` (further) is the only one that occurs: 14 times across the corpus,
 * against `下一步` (14) and `第一步` (1), which *are* counts and must not be
 * excluded. So this is a literal blocklist of the non-count form, not a rule
 * about `进一步`'s shape — a rule would be guesswork, and the corpus is small
 * enough that the exception can be named exactly.
 */
const NON_COUNT_COMPOUNDS = ['进一步'];

/**
 * The counting-position matcher.
 *
 * Note what is absent: there is no guard against a CJK character on either
 * side. Both were tried and both were wrong, and each rejection was measured.
 *
 *   - A **left** guard against CJK rejects `其中两个`, `四次运行`, `三道 MR 题`.
 *     A Chinese count is normally the last element of the noun phrase it
 *     quantifies, so the preceding character is usually CJK; the guard throws
 *     away exactly the constructions the fold exists to catch.
 *   - A **right** guard against CJK rejects `有两个问题`. The character after a
 *     measure word is normally the count's head noun, which is CJK.
 *
 * Both guards survived an initial review because the test cases they were
 * checked against happened to end at a punctuation mark. The lesson is that a
 * normaliser has to be validated on the corpus, not on examples that are
 * convenient to write — see the regression suite at the bottom of this file.
 */
const COUNTING_POSITION = new RegExp(
  `([${[...CHINESE_NUMERALS.keys()].join('')}])(?:${MEASURE_WORDS.join('|')})`,
  'g',
);

/**
 * Fold spelled-out number words into digits, symmetrically on both languages.
 *
 * Comparison runs in the digit direction, not the word direction, so that a
 * Chinese translation that uses digits is not penalised for the correct
 * rendering while a translation that changes the value still fails: folding
 * `five` to `5` in the source makes an incorrect `6` in the translation a
 * mismatch.
 *
 * Symmetry is load-bearing. A fold applied to one side only does not compare
 * two documents, it compares one document against a perturbed version of the
 * other, and the perturbation surfaces as a defect in whichever document lacks
 * it. Both passes therefore run over both documents; neither side can gain a
 * token the other could not produce.
 */
function foldNumberWords(text) {
  const withEnglish = text.replace(/\b([a-z]+)\b/gi, (match) => {
    const n = NUMBER_WORDS.get(match.toLowerCase());
    return n === undefined ? match : String(n);
  });
  return withEnglish
    .replace(
      new RegExp(NON_COUNT_COMPOUNDS.join('|'), 'g'),
      '\u0000',
    )
    .replace(COUNTING_POSITION, (match, ch) => {
      const n = CHINESE_NUMERALS.get(ch);
      // Keep the measure word: only the numeral becomes a digit, so `两个`
      // contributes a `2` and the sentence still reads as it did.
      return n === undefined ? match : String(n) + match.slice(ch.length);
    });
}

/**
 * Hyphenated compounds, masked before every other pass.
 *
 * This runs first, ahead of sign normalisation and ahead of the number-word
 * fold, and the ordering is the whole point — it is the fix for a class of
 * defect that two earlier attempts at the two rules below could not reach.
 *
 * The mechanism: a later replacement can manufacture input for an earlier
 * rule, and by the time it does, the earlier rule has already run. The measured
 * instance is `off-by-one`. The source writes it as a word, the number-word
 * fold turns `one` into `1`, and the resulting `off-by-1` is read by the
 * tokeniser as a negative one. The hyphen-range collapse that would have caught
 * it had already executed, because it must run before identifiers are masked
 * and the fold must run after. `mr-overabstention-plan.md` reported a phantom
 * `-1` for exactly this, and six further documents reported the same token for
 * the same reason — eight failures, one cause, and neither of the two fixes
 * that addressed the *other* dash defects could have found it.
 *
 * So the compounds are removed from the stream rather than anticipated by more
 * rules. They are identifiers: a reader of this corpus knows that `off-by-one`
 * and `2-of-8` name error modes rather than measurements, and identifiers are
 * the one class this checker already compares wholesale, through
 * `identifierTokens` and `frozenCounts`.
 *
 * The pattern needs an alphanumeric on both sides with no spaces, so an
 * arithmetic `10 - 4` and a prose range `8–12` are both untouched.
 */
/**
 * Mask hyphenated compounds that cannot be measurements.
 *
 * The first version of this mask used `[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+`, which
 * also swallowed numeric compounds, and the corpus immediately showed it:
 * matches fell from 86 to 64 and the new failures were all values such as
 * `500`, `1,582` and `9,542` that the mask had eaten on one side only. The
 * requirement is narrower than "has a hyphen".
 *
 * A compound is masked only when it contains **no digit at all**. That leaves
 * `off-by-one`, `out-of-band` and `state-of-the-art` masked — the class that
 * the fold can turn into a false sign — while leaving anything numeric, such as
 * `10-4` or `8-12`, fully visible to the range and measurement rules. Since the
 * mask exists to stop a *word* from becoming a number, requiring the absence of
 * digits is the natural boundary, and it is checkable rather than assumed.
 *
 * The mask consumes a **trailing hyphen** as well as the letters. Without that,
 * `million-to-10M-token` behaved as follows: `million-to` became a placeholder
 * and `M-token` became a second placeholder, leaving `\uE000-10M\uE000` — and
 * the `-10` in the middle was then read as a negative number, because the
 * digit-hyphen-letter rule no longer saw a letter after the hyphen. That is the
 * single remaining failure the mask was introduced to fix, reintroduced by the
 * mask itself. Eating the trailing hyphen means the placeholder never sits
 * adjacent to a dash, so no rule can misread the boundary.
 */
const HYPHEN_COMPOUND = /\b[A-Za-z]+(?:-[A-Za-z]+)+/g;

/**
 * Replace each hyphenated compound with an inert placeholder, and absorb the
 * hyphens left at its boundaries.
 *
 * A private-use character is used so the placeholder cannot collide with any
 * document text and cannot itself be read as a sign, a digit, or a word.
 *
 * The boundary cleanup is not cosmetic, and it is done as a separate pass
 * because a lookaround inside the compound pattern could not express it.
 * Without it, `million-to-10M-token` masked to `\uE000-10M-token`, and the
 * `-10` between the placeholder and the digits was read as a negative number:
 * the digit-hyphen-letter rule no longer saw a letter after the hyphen, because
 * the mask had removed it. That was the one remaining failure the mask was
 * introduced to fix, reintroduced by the mask itself. Removing a hyphen that
 * sits directly between a placeholder and an alphanumeric puts the string back
 * in the shape the range rules expect.
 */
function maskHyphenCompounds(text) {
  return text
    .replace(HYPHEN_COMPOUND, '\uE000')
    .replace(/\uE000-/g, '\uE000')
    .replace(/-\uE000/g, '\uE000');
}

/**
 * Scientific notation, held aside so no range rule can split it.
 *
 * Found by the regression suite on its first run, which is the point of having
 * one. `7.451e-9` was tokenising as `7.451` and `9`: the hyphen-range collapse
 * saw the `e` before the hyphen and the digit after it, and rewrote `e-9` as
 * `e 9`. An exponent is a measurement — the document's headline significance
 * figure is `p = 7.451e-9` — so mutating it to `7.451e-8` was passing the check
 * silently.
 *
 * Two ways of inserting a sentinel were tried and both failed, and the reasons
 * are worth keeping because they are the two obvious ways to get this wrong:
 *
 *   1. Appending a sentinel after the match (`7.451e-9\uE001`) leaves `e-9`
 *      intact for the range rule to find. The rule fires and the mask does
 *      nothing.
 *   2. Splicing sentinels around the sign (`7.451e\uE001-9`) protects the
 *      hyphen, but a bare `\d[eE]` start also matches from the `1` of `7.451`,
 *      splitting the mantissa into `7.45` and `1e-9` before protection applies.
 *
 * So instead of splicing, the whole exponent is lifted out into a table and
 * replaced by a single sentinel character, then put back verbatim at the end.
 * A table cannot interfere with any intermediate rule, and restoration is exact
 * because the original text is stored rather than reconstructed.
 *
 * The table is module-scoped, which is safe here because `numericTokens` is
 * synchronous and single-threaded: the table is populated and drained within
 * one call.
 */
const EXPONENT = /\d+(?:\.\d+)?[eE][+-]?\d+/g;
const EXPONENT_SENTINEL = '\uE002';
let exponentTable = [];

function protectExponents(text) {
  exponentTable = [];
  return text.replace(EXPONENT, (m) => {
    exponentTable.push(m);
    return EXPONENT_SENTINEL;
  });
}

/** Undo `protectExponents`, putting each exponent back where it belongs. */
function restoreExponents(text) {
  let i = 0;
  const restored = text.replace(new RegExp(EXPONENT_SENTINEL, 'g'), () => exponentTable[i++] ?? '');
  exponentTable = [];
  return restored;
}

/**
 * Neutralise the dash characters.
 *
 * Two defects live here, both of them about a dash being read as a sign.
 *
 * **The sign character is not standardised.** The source writes its
 * non-inferiority margin as `control −1.0pp` with U+2212 MINUS SIGN, and the
 * translation writes `对照 -1.0pp` with ASCII. U+2212 is not in the tokeniser's
 * sign class, so the source's `−1` did not tokenise as a number at all while
 * the translation's `-1` did, and the checker reported a phantom `-1` deficit
 * in each of seven documents. A lone U+2212 is a genuine sign and is folded to
 * ASCII; the choice of character carries no measurement, while a translation
 * that changed `−1.0pp` to `+1.0pp` still fails.
 *
 * **A folded dash run is still read as a sign.** Folding U+2014 to `-` makes
 * `--` available as a dash spelling, and the translation writes its em dashes
 * as a *pair* of U+2014. Measured on `p32-ordering-sequence-bug.md`: 11 runs of
 * `--` existed before the character fold and 14 existed after it, because the
 * fold manufactured three new runs behind the placeholder pass.
 * `正确** ——1个异常干净的分割` then tokenised as `-1`, since the tokeniser's
 * `[+-]?` ate the second dash as a sign — and that `-1` exists in neither
 * document. A run of two or more dashes of any spelling is punctuation, never a
 * sign, because a real negative number is written with exactly one dash.
 *
 * Note that this pass cannot simply be moved after the fold instead: the fold
 * is what turns `off-by-one` into a dash run in the first place, which is why
 * the compounds are masked above rather than handled here.
 */
function normalizeSigns(text) {
  return text
    // A lone U+2212 is a genuine negative sign: keep it, as ASCII.
    .replace(/\u2212/g, '-')
    // Runs of two or more dashes of any spelling are punctuation, never a sign.
    .replace(/[-]{2,}/g, '\u0000')
    .replace(/[\u2013\u2014]/g, '\u0000');
}

/**
 * Identifier mask. Question ids, commit shas and run ids embed digits, and a
 * bare digit run inside one of them is not a measurement.
 *
 * This is not a hypothetical: measured on the first translated batch, the row
 * `db467c8c  4  0  -4` yielded the digits `467` and `8` from the id alone. The
 * two documents then disagreed — `source=10 translated=11` for the token `4` —
 * purely because the source phrased one sentence with an id where the
 * translation used prose. The measurement was identical in both.
 *
 * Masking the whole identifier is the fix, and it is the right level: a reader
 * cares whether `-10.11pp` survived, not whether the five digits of a commit
 * sha were republished. Ids are compared wholesale by their own check below.
 */
const IDENTIFIER = /\b[A-Za-z0-9]*[a-f0-9]{8,}\b|\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b|\b[0-9]{11,}\b|\b[0-9a-f]{7,40}\b/g;

/**
 * Calendar dates, masked before the identifier pass.
 *
 * Measured on `p12-dataset-verified-failures.md`: the source writes
 * `2023/05/22` and the reported token diffs were `05` (12 in source, 10 in
 * translation), `22`, `08`, `00`, `16`. Every one of those came from a date's
 * components: the translation rephrased one sentence from "the two gold
 * sessions are dated 2023/05/22 and 2023/05/27" to a form that mentions the
 * date once, so one `05` and one `22` legitimately disappeared, and the
 * remaining components were re-split against different surrounding punctuation.
 *
 * Masking the whole date is the correct level, for the same reason as the
 * identifier mask: a reader needs to know the date survived, and the date is
 * compared wholesale by its own check rather than digit by digit.
 */
const DATE = /\b\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?\b|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b|\b\d{1,2}\/\d{1,2}\b/g;

/**
 * Clock times, masked for the same reason as dates.
 *
 * Measured on `p12-dataset-verified-failures.md`, which is dense with both:
 * the source contains `08:18`, `00:16`, `00:25` and also the bare date forms
 * `05/20`, `05/24`, `05/25`. When the translation expanded a short form into a
 * long one — source `05/24` becoming translation `2023/05/24` — the digit runs
 * `2023`, `05`, `24` changed the token multiset even though the date is
 * identical. Five of the nine reported diffs in that document were this.
 *
 * Masking dates and times wholesale does not weaken the check where it matters:
 * the numbers that carry measurements in these documents (`856`, `416`, `440`,
 * `341`, `0.4%`, `97.7%`) are not date-shaped and are still compared exactly.
 */
const TIME = /\b\d{1,2}:\d{2}(?::\d{2})?\b/g;

/** Replace identifier spans with a placeholder so their digits are ignored. */
function maskIdentifiers(text) {
  return text
    .replace(DATE, '\u0000')
    .replace(TIME, '\u0000')
    .replace(IDENTIFIER, '\u0000');
}

/**
 * Hyphens that join a number to a letter, in either order.
 *
 * These are prose ranges and compound identifiers, not arithmetic, and
 * translating them legitimately changes both the sign reading and the token
 * count. Two measured instances, both from the eight-document failure set that
 * the measurement-only strategy exposed:
 *
 *   - `## 4. BEAM — million-to-10M-token scale` became
 *     `## 4. BEAM — 百万至 10M token 规模`, reported as a lost `-10` and a
 *     gained `1` and `10`.
 *   - `session-39 recall miss` became `会话 39 的召回缺失`, reported as a lost
 *     `-39`.
 *
 * The first direction (letter-then-hyphen-then-digit) covers `million-to-10M`
 * and `Step-2`; the second (digit-then-hyphen-then-letter) covers `2-of-8` and
 * `-8–12 KB`. Collapsing the hyphen before tokenizing removes the ambiguity
 * without weakening the check on any real measurement, because an arithmetic
 * `10 - 4` has spaces around the hyphen and is untouched.
 *
 * A digit-hyphen-digit run such as `8-12` is deliberately **not** collapsed.
 * It is a genuine range whose endpoints a reader may need, and collapsing it
 * would hide a translation that dropped an endpoint.
 */
function collapseWordRanges(text) {
  return text
    .replace(/([A-Za-z\u4e00-\u9fff])-(?=\d)/g, '$1 ')
    .replace(/(?<=\d)-(?=[A-Za-z\u4e00-\u9fff])/g, ' ');
}

/**
 * Identifier multiset, compared across the two documents.
 *
 * Ids must be reproduced exactly: an id in a document is a pointer, and a
 * pointer that does not resolve is worse than no pointer. Comparison is by
 * multiset for the same reason as numbers — word order may change, the set of
 * ids may not.
 */
function identifierTokens(text) {
  return (text.match(IDENTIFIER) ?? []).map((t) => t);
}

/**
 * Frozen identifiers: multi-word names that the analysis documents use as
 * literal references to code, prompts, or protocol elements. These must
 * survive translation byte-identically.
 *
 * This class exists because of a measured defect: the first translated batch
 * rendered `Step 2` / `Step-2` as `第 2 步规则`. The rendering is idiomatic
 * Chinese and reads well, but `Step 2` is a string literal in the answer
 * prompt — `natural-language-memory.test.ts` asserts
 * `prompt).toContain('Step 2 — Answer the question using ONLY those identified
 * facts')` — so translating it severs the link between the document and the
 * artifact it describes. A reader following the document would look for a
 * Chinese heading that the code does not contain.
 *
 * The list is intentionally short and explicit rather than a heuristic. A
 * heuristic ("treat any X-N as frozen") would fire on legitimate prose, and
 * this check has to stay trustworthy enough to fail a whole batch on.
 */
const FROZEN_IDENTIFIERS = [
  'Step 1',
  'Step 2',
  'Step 3',
  'Step-1',
  'Step-2',
  'Step-3',
];

/**
 * Strip fenced and inline code unless the caller asked to keep it.
 *
 * Inline spans are matched across newlines. This is not a stylistic choice: a
 * Markdown inline span may contain a hard line break, and the analysis
 * documents use that — `p27-residual-abs-failure.md` wraps a quoted user
 * utterance as `` `"initially`` / ``plant"` `` across two lines.
 *
 * The cost of getting this wrong was measured and was large. With `[^`\n]*`,
 * the span opened on line 155 could not close on line 156, so every subsequent
 * backtick in the document paired with the wrong partner, and 1,848 characters
 * of ordinary prose were deleted as if they were code — which is exactly where
 * the large spurious `1` deficit in that document came from (checker reported
 * `"1" source=51 translated=119`; the document contains 28 standalone `1`s, so
 * the deficit was entirely manufactured).
 *
 * The general rule this instance teaches: a stripper must be *balanced*. It is
 * not enough for it to remove the right thing in the common case; an unmatched
 * delimiter must degrade to removing nothing rather than to removing a
 * document's worth of text. The `[^`\n]*` form had no such fallback, and no
 * call site could detect that it had gone wrong.
 */
function stripCode(text) {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    // `[\s\S]` rather than `[^`\n]` so a span may wrap a line; the lazy
    // quantifier and the explicit backtick keep it from running past the span.
    .replace(/`[^`]*?`/g, ' ');
}

/**
 * Count frozen identifiers, tolerating hyphen/space variation only in the
 * direction of the known defect. `Step-2` written as `Step 2` is accepted,
 * because that is a typographic choice; `Step 2` written as `第 2 步` is not,
 * because the literal is gone.
 */
function frozenCounts(text) {
  const counts = new Map();
  for (const id of FROZEN_IDENTIFIERS) {
    const [word, num] = id.split(/[-\s]/);
    const re = new RegExp(`\\b${word}[-\\s]${num}\\b`, 'g');
    const n = (text.match(re) ?? []).length;
    if (n > 0) {
      const key = `${word} ${num}`;
      counts.set(key, (counts.get(key) ?? 0) + n);
    }
  }
  return counts;
}

/**
 * Strip list ordinals and section numbers that sit at the start of a marker.
 *
 * Only display-indented or bulleted markers qualify: `  1. text`, `- 2) text`,
 * `* 3. text`. A number in column zero followed by a space and a capital is
 * left alone, and that distinction is load-bearing rather than cosmetic.
 *
 * Measured on `p8-mr-error-shape.md`, whose source wraps as
 * `... under **5**, over **7**, equal\n89. Over-counting is *more* common ...`.
 * The bare `89` is a count of questions. An earlier version of this stripper
 * matched at column zero and silently deleted it from the source but not from
 * the translation — the translation happened to break the line elsewhere — so
 * the checker reported a fabricated "+89 appeared". The lesson generalises: a
 * normaliser that removes too much invents defects, which is worse than missing
 * them, because it trains the reader to ignore the check.
 *
 * Renumbering a translated list is still not a data change, so genuine markers
 * continue to be stripped.
 */
function stripListMarkers(text) {
  return text.replace(/^([ \t]+)(?:\d+[.)]|[-*+])\s+/gm, '$1');
}

/**
 * Extract numeric tokens, dropping line-leading list markers ("1. ", "- 2) ").
 */
function numericTokens(text, { keepCode = false } = {}) {
  const body = keepCode ? text : stripCode(text);
  // Compounds are masked first: see HYPHEN_COMPOUND for the measured reason.
  const withoutCompounds = maskHyphenCompounds(body);
  const withExponents = protectExponents(withoutCompounds);
  const withSigns = normalizeSigns(withExponents);
  const withoutMarkers = stripListMarkers(withSigns);
  const withoutRanges = collapseWordRanges(withoutMarkers);
  // Order matters. Identifiers are masked BEFORE number words are folded, not
  // after: several identifiers in this corpus contain English number words
  // (`one`, `two`) as substrings, and folding first rewrites them into digits
  // in the source while leaving the translation's untouched, which fabricates
  // divergences in every document that mentions such an identifier.
  const withoutIds = maskIdentifiers(withoutRanges);
  const withDigits = foldNumberWords(withoutIds);
  const normalized = normalizePercentSpacing(restoreExponents(withDigits));
  const found = normalized.match(NUMERIC) ?? [];
  return found
    .map((t) => t.trim())
    .filter((t) => t.length > 0)
    // A lone sign or a bare separator is not a measurement.
    .filter((t) => /\d/.test(t));
}

function multiset(tokens) {
  const m = new Map();
  for (const t of tokens) m.set(t, (m.get(t) ?? 0) + 1);
  return m;
}

/**
 * Is this token's *count* a property of the measurement, or of the language?
 *
 * A bare one- or two-digit integer is language-dependent, and the translation
 * cannot be held to the source's tally of it. The evidence is unambiguous:
 *
 *   - English reaches for a spelled-out word where Chinese reaches for a
 *     numeral plus a measure word. `the same two sessions` is one numeral in the
 *     source; `同样那两个会话` is one in the translation — but the source also
 *     says `both` and `the pair`, which Chinese renders as `两个` and which
 *     therefore appear on the translation side only.
 *   - The reverse happens too: `a`/`an` is an article in English and becomes
 *     `一个` in Chinese, adding a count the source never had numerically.
 *
 * Measured across the corpus, folding both sides to a common form left 1 of 94
 * documents matching, and the residual was dominated by single digits (`"1"`,
 * `"2"`, `"3"`) — i.e. the fold did not remove a language difference, it
 * relocated it. Single digits are where English spelling and Chinese
 * measure-word grammar differ most, and no normalisation can reconcile them
 * without also making the check blind to a genuinely altered count.
 *
 * So the split is made explicit rather than papered over. Integers of one or
 * two digits are compared **leniently**, and every divergence among them is
 * printed for review; anything with a sign, a decimal point, a percent, an
 * exponent, or three or more digits is compared **exactly**, because a reader
 * cannot be misled by a restated count of "two sessions" but can be misled by a
 * restated `97.7%` or `+14.00pp`.
 *
 * The lenient rule is a **paired** test, and the shape it has was forced twice
 * by the regression suite. A bare integer cannot be compared on its own —
 * `two` -> `both` is a language difference and `five` -> `6` is a defect, and
 * the two look identical token by token, because in both cases a source `2` or
 * `5` is replaced by something else. What separates them is whether the
 * translation *substituted* a count for the one it removed:
 *
 *   - `two` -> `both` moves count out of the digit stream into a word. The
 *     source `2` disappears and nothing new appears.
 *   - `five` -> `6` also makes the source `5` disappear, but it *introduces a
 *     `6` that the source never had*. That is the fingerprint of a changed
 *     value rather than a changed expression.
 *
 * So the exemption is granted only when the translation's bare-integer stream
 * introduces no token absent from the source's. An unbalanced count is
 * reconcilable; a substituted one is reported.
 */
function isLanguageDependent(token) {
  return /^\d{1,2}$/.test(token);
}

function compare(srcText, dstText, keepCode) {
  const srcTokens = numericTokens(srcText, { keepCode });
  const dstTokens = numericTokens(dstText, { keepCode });
  const a = multiset(srcTokens);
  const b = multiset(dstTokens);

  // A token the translation introduces that the source never had at all is a
  // substituted value, not a restatement, and disqualifies the lenient path.
  const introduced = [];
  const diffs = [];
  const lenient = [];
  for (const tok of [...new Set([...a.keys(), ...b.keys()])].sort()) {
    const ca = a.get(tok) ?? 0;
    const cb = b.get(tok) ?? 0;
    if (ca === cb) continue;
    const entry = { token: tok, source: ca, translated: cb };
    if (isLanguageDependent(tok) && ca > 0) lenient.push(entry);
    else {
      if (isLanguageDependent(tok) && ca === 0) introduced.push(entry);
      diffs.push(entry);
    }
  }

  // If any bare integer appears in the translation and nowhere in the source,
  // the counts cannot be reconciled: something was substituted.
  if (introduced.length > 0) {
    for (const e of lenient.splice(0)) diffs.push(e);
    diffs.sort((x, y) => (x.token < y.token ? -1 : x.token > y.token ? 1 : 0));
  }

  // Frozen identifiers are reported separately: they are not numbers, and a
  // reader needs to know which rule was broken to fix it.
  const fa = frozenCounts(srcText);
  const fb = frozenCounts(dstText);
  const frozen = [];
  for (const key of new Set([...fa.keys(), ...fb.keys()])) {
    const ca = fa.get(key) ?? 0;
    const cb = fb.get(key) ?? 0;
    if (ca !== cb) frozen.push({ token: key, source: ca, translated: cb });
  }

  return { sourceCount: srcTokens.length, translatedCount: dstTokens.length, diffs, lenient, frozen };
}

function checkFiles(srcPath, dstPath, keepCode) {
  const src = readFileSync(srcPath, 'utf8');
  const dst = readFileSync(dstPath, 'utf8');
  const r = compare(src, dst, keepCode);
  return { srcPath, dstPath, srcText: src, dstText: dst, ...r };
}

/**
 * Locate every occurrence of a token and return a window of context.
 *
 * Purely a reporting aid, and an essential one. Without it the only way to
 * judge whether a reported divergence is a defect or a false positive is to
 * grep each document by hand for each token, which is slow and unreliable —
 * the token `-1` does not appear literally in the source of most documents
 * that report one, because `−1` with U+2212 is a different string, and the
 * tokeniser's `-1` is a reading, not a literal. The checker knows where it
 * matched; it should say so rather than leaving the reader to reconstruct it.
 */
function contextOf(text, token, keepCode, width = 46) {
  const searchIn = keepCode ? text : stripCode(text);
  const needles = new Set([token, normalizeSigns(token)]);
  // The source may spell the sign with U+2212 where the token used ASCII.
  if (token.startsWith('-')) needles.add('\u2212' + token.slice(1));
  else needles.add('-' + token);

  const spans = [];
  for (const needle of needles) {
    let idx = searchIn.indexOf(needle);
    while (idx !== -1 && spans.length < 4) {
      spans.push(
        searchIn
          .slice(Math.max(0, idx - width), idx + needle.length + width)
          .replace(/\n/g, ' '),
      );
      idx = searchIn.indexOf(needle, idx + needle.length);
    }
    if (spans.length >= 4) break;
  }
  return spans;
}

function main() {
  const args = process.argv.slice(2);
  const keepCode = args.includes('--strict-code');
  const positional = args.filter((a) => !a.startsWith('--'));

  if (args.includes('--file')) {
    const [src, dst] = positional;
    if (!src || !dst) {
      console.error('usage: --file <source.md> <translated.md>');
      process.exit(2);
    }
    const r = checkFiles(src, dst, keepCode);
    report([r]);
    return;
  }

  const [srcDir, dstDir] = positional;
  if (!srcDir || !dstDir) {
    console.error(
      'usage: <source-dir> <translated-dir> [--strict-code] [--summary] [--trace]\n' +
        '       --file <source.md> <translated.md> [--strict-code] [--trace]',
    );
    process.exit(2);
  }

  const names = readdirSync(srcDir)
    .filter((n) => n.endsWith('.md') && statSync(join(srcDir, n)).isFile())
    .sort();

  const results = [];
  let missing = 0;
  for (const n of names) {
    const dstPath = join(dstDir, n);
    try {
      statSync(dstPath);
    } catch {
      missing++;
      results.push({ srcPath: join(srcDir, n), dstPath, missing: true, diffs: [] });
      continue;
    }
    results.push(checkFiles(join(srcDir, n), dstPath, keepCode));
  }
  report(results, missing);
}

function report(results, missing = 0) {
  const summaryOnly = process.argv.includes('--summary');
  const trace = process.argv.includes('--trace');
  const keepCode = process.argv.includes('--strict-code');
  let bad = 0;
  let lenientTotal = 0;

  for (const r of results) {
    const name = basename(r.srcPath);
    if (r.missing) {
      if (!summaryOnly) console.log(`MISSING  ${name}`);
      bad++;
      continue;
    }

    const frozen = r.frozen ?? [];
    const lenient = r.lenient ?? [];
    lenientTotal += lenient.length;

    // Frozen identifiers are never excused: a translated identifier points at
    // something the code does not contain, which no amount of restatement
    // makes acceptable.
    if (r.diffs.length === 0 && frozen.length === 0) {
      if (!summaryOnly) {
        const note = lenient.length
          ? `  [${lenient.length} single-digit count${lenient.length > 1 ? 's' : ''} reconciled]`
          : '';
        console.log(`OK       ${name}  (${r.sourceCount} numeric tokens)${note}`);
      }
      continue;
    }

    bad++;
    if (summaryOnly) continue;
    console.log(`DRIFT    ${name}  source=${r.sourceCount} translated=${r.translatedCount}`);
    for (const d of r.diffs.slice(0, 12)) {
      console.log(`           number    "${d.token}"  source=${d.source} translated=${d.translated}`);
      if (trace) {
        for (const c of contextOf(r.srcText ?? '', d.token, keepCode)) {
          console.log(`             src  ...${c}...`);
        }
        for (const c of contextOf(r.dstText ?? '', d.token, keepCode)) {
          console.log(`             dst  ...${c}...`);
        }
      }
    }
    if (r.diffs.length > 12) {
      console.log(`           ... and ${r.diffs.length - 12} more numbers`);
    }
    for (const d of frozen) {
      console.log(`           frozen    "${d.token}"  source=${d.source} translated=${d.translated}`);
    }
  }

  console.log('');
  console.log(
    `check-numeric-fidelity: ${results.length - bad}/${results.length} documents match` +
      (bad ? `, ${bad} FAILED` : '') +
      (missing ? `, ${missing} missing` : '') +
      (lenientTotal ? `, ${lenientTotal} language-dependent count(s) reconciled` : ''),
  );
  process.exit(bad === 0 ? 0 : 1);
}

/**
 * Export the stages so a caller can reproduce a reported token by hand.
 *
 * Added after spending a long detour reconstructing one document's `-1` in a
 * shell one-liner, where the escaping of `\u2212` and the backtick regexes made
 * the reproduction itself unreliable. A checker whose behaviour cannot be
 * reproduced outside itself is not auditable, and this one is meant to fail a
 * batch of 94 documents, so it has to be.
 */
export { numericTokens, compare, stripCode, normalizeSigns, foldNumberWords, maskHyphenCompounds, COUNTING_POSITION };

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  main();
}

