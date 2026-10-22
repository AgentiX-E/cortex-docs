/**
 * A real in-memory implementation of cortex-core's `Storage`, used as both halves of the POC.
 *
 * It is not a mock: it implements tags, ttl, prefix queries, pagination and transactions, and
 * the federation tests assert against those behaviours. The point of using it instead of two
 * SQLite files is that the federation's *semantics* are what is under test here; POC-1 covers
 * the browser engine, and mixing the two would make a failure ambiguous.
 */
export class MemoryStore {
  #rows = new Map();
  #closed = false;

  #bucket(table) {
    if (!this.#rows.has(table)) this.#rows.set(table, new Map());
    return this.#rows.get(table);
  }

  async put(table, key, value, options = {}) {
    this.#bucket(table).set(key, {
      value,
      tags: [...(options.tags ?? [])],
      expiresAt: options.ttlMs === undefined ? undefined : Date.now() + options.ttlMs,
    });
  }

  async get(table, key) {
    const row = this.#bucket(table).get(key);
    if (row === undefined) return undefined;
    if (row.expiresAt !== undefined && row.expiresAt <= Date.now()) {
      this.#bucket(table).delete(key);
      return undefined;
    }
    return row.value;
  }

  async del(table, key) {
    this.#bucket(table).delete(key);
  }

  async query(table, predicate = {}) {
    const now = Date.now();
    const rows = [...this.#bucket(table).entries()]
      .filter(([, row]) => row.expiresAt === undefined || row.expiresAt > now)
      .filter(([key]) => predicate.keyPrefix === undefined || key.startsWith(predicate.keyPrefix))
      .filter(([, row]) => (predicate.tags ?? []).every((tag) => row.tags.includes(tag)))
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    const start = predicate.offset ?? 0;
    const end = predicate.limit === undefined ? rows.length : start + predicate.limit;
    return rows.slice(start, end).map(([, row]) => row.value);
  }

  async transaction(fn) {
    const snapshot = new Map([...this.#rows].map(([table, rows]) => [table, new Map(rows)]));
    const tx = {
      put: (table, key, value, options) => this.put(table, key, value, options),
      get: (table, key) => this.get(table, key),
      del: (table, key) => this.del(table, key),
    };
    try {
      return await fn(tx);
    } catch (error) {
      this.#rows = snapshot;
      throw error;
    }
  }

  async close() {
    this.#closed = true;
    this.#rows.clear();
  }

  get closed() {
    return this.#closed;
  }
}
