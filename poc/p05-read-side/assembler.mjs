/**
 * The read side: who may see which rows when an evidence window is assembled.
 *
 * ## Why this is a separate component from the router
 *
 * `FederatedStorage` (POC-3) decides *where a table lives*. It says nothing about *who is
 * asking*. A shared task ("draft a note to the team") and a private task ("what did I decide
 * about my own finances") read the same tables and must not get the same rows. That decision
 * belongs to whoever assembles `sessions` for the reader, which is why it lives here and not in
 * `cortex-memory`: the memory layer receives evidence as a parameter, and giving it a notion of
 * "private" would put a policy word inside a component whose whole test surface is
 * single-variable prompts.
 *
 * ## The two rules this file exists to hold
 *
 * 1. A shared window is built from the shared store only. The private store is not queried, so
 *    a private row cannot appear "by accident of a filter someone forgot".
 * 2. Every row in a shared window must declare `visibility: 'shared'`. A row that declares
 *    otherwise is a **writer** bug, and the assembler throws rather than filtering it out:
 *    filtering would keep the boundary looking intact while the writer stayed broken, which is
 *    the failure mode this project's audit tooling exists to catch. Fail closed, loudly.
 *
 * Rule 2 cannot be earned by rule 1: rule 1 is about which store is read, rule 2 is about what
 * a row says about itself. They fail independently, so both are tested independently -- including
 * a fault injection that proves the guard can fire at all (a check that cannot fail is not a
 * check; POC-3's first draft had `async () => true` and it was deleted, not commented out).
 */

/** Raised when a row in a shared window does not declare itself shared. */
export class ScopeViolation extends Error {
  constructor(message) {
    super(message);
    this.name = 'ScopeViolation';
  }
}

export class ReadSideAssembler {
  #federation;
  #guard;

  /**
   * @param {import('../p03-federation/federated.mjs').FederatedStorage} federation
   * @param {{ guard?: boolean }} [options] `guard: false` exists only for the A5 ablation;
   *   nothing in the product may construct it that way.
   */
  constructor(federation, { guard = true } = {}) {
    this.#federation = federation;
    this.#guard = guard;
  }

  /**
   * Assemble the rows a task of the given scope is allowed to see.
   *
   * @param {{ task: 'private' | 'shared', table?: string }} request
   * @returns {Promise<Array<{ origin: 'private' | 'shared', key: string, value: unknown }>>}
   */
  async assemble({ task, table = 'facts' }) {
    if (task !== 'private' && task !== 'shared') {
      throw new ScopeViolation(`unknown task scope ${JSON.stringify(task)}: expected private or shared`);
    }

    const rows =
      task === 'shared' ? await this.#sharedOnly(table) : await this.#bothStores(table);

    if (task === 'shared' && this.#guard) {
      const offending = rows.filter((row) => row.value?.visibility !== 'shared');
      if (offending.length > 0) {
        const keys = offending.map((row) => row.key).join(', ');
        throw new ScopeViolation(
          `shared window would carry ${offending.length} row(s) that do not declare themselves ` +
            `shared (${keys}). This is a write-side defect, not a read-side one: the assembler ` +
            `refuses to launch a prompt rather than silently drop the rows, because dropping them ` +
            `would hide the defect while making the boundary look intact.`,
        );
      }
    }

    return rows;
  }

  /** Shared tasks read one store. Nothing else is queried, so nothing else can leak. */
  async #sharedOnly(table) {
    const rows = await this.#federation.query(`shared/${table}`, {});
    return rows.map((value) => ({ origin: 'shared', key: value.id, value }));
  }

  /**
   * Private tasks read both stores and dedupe by id, preferring the owner's copy.
   *
   * The `origin` label is not decoration: a private window mixes "my note" with "the team's
   * note", and the prompt (or the UI, or the citation list) has to be able to say which is
   * which. POC-3 asserts the router attaches it; this asserts it survives the merge.
   */
  async #bothStores(table) {
    const across = await this.#federation.queryAcross(`private/${table}`, {});
    const byId = new Map();
    for (const row of across) {
      const key = row.value.id;
      const seen = byId.get(key);
      if (seen === undefined || (seen.origin === 'shared' && row.origin === 'private')) {
        byId.set(key, { origin: row.origin, key, value: row.value });
      }
    }
    return [...byId.values()];
  }
}
