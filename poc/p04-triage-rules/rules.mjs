/**
 * The deterministic disclosure layer, as a pure function of one sentence.
 *
 * ## Why rules first, and why this file is short
 *
 * docs/02 splits the triage into extraction (a model's job) and disclosure (not a model's job),
 * and cites CIMemories: frontier models violate context-appropriate flow on up to 69% of
 * attribute-level checks, violations accumulate with use, and privacy prompting makes them
 * worse rather than better. A layer with that error profile cannot be the last word on "may
 * this leave the device".
 *
 * So the last word is a rule table that a reviewer can read in one screen, plus the user.
 * The rules are ordered: every private rule runs before any shared rule, so a sentence that
 * looks organisational *and* mentions money stays private. That ordering is the entire
 * fail-closed argument, and POC-4 measures whether it holds.
 *
 * ## Where the model still sits
 *
 * After this function returns `defer`, which is 2 of 3 candidates in the measured sample. The
 * model's job there is to write a *card* for the user to accept, edit, or dismiss -- not to
 * decide. `p04` measures only what the rules decide, because that is the part that can be
 * measured without a provider.
 */

/** One rule: an id (quoted in docs/04), a target scope, and the pattern that fires it. */
const RULES = [
  {
    id: 'credential',
    scope: 'private',
    policy: 'credentials are never stored, not even as a card',
    // CVV and wallet addresses were added after POC-6's CI run over 3,000 identifier-bearing
    // rows found 16 publications, and every one of them was a payment secret no rule claimed:
    // "the CVV is 412", "provide your Bitcoin address 3D1mKZ…". A credential that is not
    // recognised is not a card the user can dismiss; it is a string that leaves the device.
    pattern:
      /\b(password|passcode|api[ _-]?key|secret|token|private key|passphrase|ssn|social security|\bpin\b|ghp_|sk-|cvv|cvc|seed phrase)\b|\b(bitcoin|litecoin|ethereum|wallet)\s+address\b|\b0x[0-9a-f]{40}\b|\bbc1[a-z0-9]{25,}\b|\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b/i,
  },
  {
    id: 'strong-pii',
    scope: 'private',
    policy: 'identifiers that are regulated by form: email, phone, card, postal address',
    pattern:
      // Account numbers and apartment designators were added after the second CI run: of the four
      // rows it still published, all four were bank accounts in sentences that otherwise read as
      // organisational ("charge your travel to our company account, number 40387..."). An account
      // number is a regulated identifier in the same sense a card number is, so it belongs here
      // rather than in a new rule.
      /[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d ()-]{7,}\d|\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b|\b\d+\s+[A-Z][a-z]+\s+(street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd)\b|\b(account|acct|card)\s*(number|no\.?|#)\s*[\d*]{4,}|\bapt\.?\s*\d+/i,
  },
  {
    id: 'money',
    scope: 'private',
    policy: 'amounts, income, budget, debt',
    pattern:
      /(\$\s?\d|\b\d+\s?(dollars|usd|eur|gbp)\b|salary|income|mortgage|\brent\b|\bdebt\b|budget|\bspent\b|\bpaid\b|\bafford)/i,
  },
  {
    id: 'health',
    scope: 'private',
    policy: 'body, diagnosis, medication, diet, exercise, appointments',
    // `walk`/`sugar`/`calorie`/`intake` were added after the card queue's first measurement (in
    // `cortex`, step 6) found that 3 of the 12 gold-private utterances were never caught by any
    // rule, and all 3 were ordinary exercise and diet phrasing. Measured before shipping: private
    // recall 9/12 -> 12/12, coverage 26.7% -> 31.7%, no change in the 13 frozen regressions.
    //
    // The vitals clause was added after POC-6 ran this rule over 151 sentences from a different
    // corpus and found it silent on measurements: "blood pressure 138 over 86", "liver function
    // test showed ALT 28", "I average 7.5 hours of sleep". Those are health facts by any reading,
    // and being silent about them costs the user a card, not safety -- which is why the gap
    // survived a false-share audit. The addition is justified by the policy, not by the corpus.
    pattern:
      /\b(diagnos\w*|doctor|dentist|therapy|therapist|medication|prescription|symptom|allerg\w*|surgery|clinic|mental health|anxiety|depress\w*)\b|\b(vegan|vegetarian|lacto|gluten[- ]free|diet)\b|\b(jog|walk(ing|s)?|workout|exercise|strength training|wake up at|weight|sugar|calorie|intake)\b|\b(blood pressure|heart rate|cholesterol|liver function|kidney function|\bALT\b|\bAST\b|\bBMI\b|mmHg|blood sugar|blood test|hours of sleep|sober|sobriety)\b/i,
  },
  {
    id: 'family',
    scope: 'private',
    policy: 'family and relationship details',
    pattern:
      /\b(my|our)\s+(wife|husband|partner|girlfriend|boyfriend|son|daughter|kid|kids|child|children|mother|father|mom|dad|parents|family|sister|brother)\b|\banniversary\b/i,
  },
  {
    id: 'career-status',
    scope: 'private',
    policy: 'employment status and its rewards are personal, even when they happen at work',
    // `raise` alone was a bug this POC found: it fires on "raise funds for a food bank", a team
    // event, and calls it a career fact. The word-sense is fixed here; the row it mislabelled is
    // still private afterwards, because it also names colleagues, so the metric did not move --
    // only the reason attached to it did.
    pattern: /\b(promotion|promoted|pay rise|pay raise|resigned|quit|fired|laid off|interview at|new job)\b/i,
  },
  {
    id: 'third-party',
    scope: 'private',
    policy: "other people's information is not the user's to publish",
    pattern:
      /\b(my|a|the)\s+(colleague|colleagues|boss|manager|teammate|co-?worker|friend|neighbou?r|landlord|doctor)\b/i,
  },
  {
    id: 'org-knowledge',
    scope: 'shared',
    // Deliberately narrower than "mentions work". POC-4 measured that "at work" fires on a
    // personal to-do ("meetings scheduled at work, finish a report") which is not organisational
    // knowledge, so the rule requires an *organisational object* rather than a location.
    policy: 'an organisational object a colleague could act on',
    pattern:
      /\b(our team|our company|our org|the company i work|the project|project plan|the client|roadmap|sprint|onboarding|deliverable|team-building|we decided|the department|the board)\b/i,
  },
];

/** Which rule fired, for the audit trail a card would carry. */
export function classify(text) {
  for (const rule of RULES) {
    if (rule.pattern.test(text)) return { scope: rule.scope, rule: rule.id, policy: rule.policy };
  }
  return { scope: 'defer', rule: null, policy: null };
}

/** The write path: `defer` is stored privately, because a deferred decision is not consent. */
export function destination(text) {
  const verdict = classify(text);
  return { ...verdict, destination: verdict.scope === 'shared' ? 'shared' : 'private' };
}

export const RULE_TABLE = RULES;
