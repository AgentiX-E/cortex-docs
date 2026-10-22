/**
 * A federated `Storage` over two stores, with the privacy boundary in the table name.
 *
 * ## Why the scope lives in the table name
 *
 * `Storage` in cortex-core is `put(table, key, value, {tags, ttlMs})` -- six methods, no scope
 * field. Adding one would change a contract that every existing backend implements, and it
 * would put a policy word into a storage primitive. A namespace prefix (`private/facts`,
 * `shared/facts`) carries the same information in the place a storage engine already treats as
 * a namespace, which is also how Mem0 (`user_id`/`agent_id`/`run_id`) and Redis Agent Memory
 * (namespaced keys) do it.
 *
 * ## What this file refuses to fake
 *
 * A write that would touch both stores in one unit is **not** implemented. Two independent
 * SQLite files cannot be committed atomically from a browser tab, and a router that pretended
 * otherwise would lose half a write on the failure path -- exactly the class of silent
 * corruption this project's audit tool exists to catch. `transaction` therefore:
 *
 *   - with a single scope: delegates to that store's real transaction;
 *   - with two scopes: throws, and the message names the alternative (write one, then the
 *     other, and reconcile on read).
 */

/**
 * The scope a table belongs to, from its prefix. Unprefixed tables are private: the default
 * must be the safe one, or a caller who forgets the prefix publishes.
 */
export function scopeOf(table) {
  if (table.startsWith('shared/')) return 'shared';
  return 'private';
}

/**
 * Split a table name into the store it routes to and the name it has *inside* that store.
 *
 * The prefix is a routing marker, not part of the namespace: if the private store held
 * `private/facts` while the shared store held `shared/facts`, the same logical table would have
 * two names depending on where it lives, and a cross-store read would have to know both. The
 * first draft of this file made exactly that mistake and `queryAcross` returned nothing.
 */
function split(table) {
  if (table.startsWith('shared/')) return { scope: 'shared', name: table.slice('shared/'.length) };
  if (table.startsWith('private/')) return { scope: 'private', name: table.slice('private/'.length) };
  return { scope: 'private', name: table };
}

export class FederationError extends Error {}

/**
 * @param {{ private: import('./memory-store.mjs').MemoryStore, shared: import('./memory-store.mjs').MemoryStore }} stores
 */
export class FederatedStorage {
  constructor(stores) {
    this.stores = stores;
  }

  store(table) {
    return this.stores[split(table).scope];
  }

  async put(table, key, value, options) {
    const { scope, name } = split(table);
    return this.stores[scope].put(name, key, value, options);
  }

  async get(table, key) {
    const { scope, name } = split(table);
    return this.stores[scope].get(name, key);
  }

  async del(table, key) {
    const { scope, name } = split(table);
    return this.stores[scope].del(name, key);
  }

  async query(table, predicate) {
    const { scope, name } = split(table);
    return this.stores[scope].query(name, predicate);
  }

  /**
   * Query both stores and label every row with where it came from.
   *
   * The label is the point: a prompt assembled from two origins must be able to say which is
   * which, because the read-side policy (docs/02) is "a shareable answer sees shared rows only"
   * and that decision needs the origin to be visible at the assembly site rather than inferred
   * from the table name by whoever remembers to check.
   */
  async queryAcross(table, predicate) {
    const { name } = split(table);
    const [local, shared] = await Promise.all([
      this.stores.private.query(name, predicate),
      this.stores.shared.query(name, predicate),
    ]);
    return [
      ...local.map((value) => ({ origin: 'private', value })),
      ...shared.map((value) => ({ origin: 'shared', value })),
    ];
  }

  async transaction(fn) {
    // The callback decides the scope, so the scope cannot be known before it runs. That is the
    // whole reason a two-store commit cannot be offered: the router would have to guess.
    throw new FederationError(
      'a federated transaction cannot be atomic across two stores: pass a single scope, e.g. ' +
        '`transaction(scope, fn)`, and reconcile cross-scope writes on read. Two SQLite files ' +
        'have no shared commit point, and a router that pretended otherwise would lose half a ' +
        'write on the failure path.',
    );
  }

  /** Explicitly scoped transaction, which is what the product should call. */
  async transactionIn(scope, fn) {
    if (scope !== 'private' && scope !== 'shared') {
      throw new FederationError(`unknown scope ${JSON.stringify(scope)}`);
    }
    return this.stores[scope].transaction(fn);
  }

  async close() {
    await Promise.all([this.stores.private.close(), this.stores.shared.close()]);
  }
}
