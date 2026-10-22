| check | result | detail |
| --- | --- | --- |
| routing follows the prefix, unprefixed is private | PASS | shared/facts -> shared, facts -> private |
| the shared store holds the shared row and not the private one | PASS | 1 row(s) in the shared store: the project plan |
| private query returns only private rows | PASS | 1 row(s) |
| queryAcross labels every row with its origin | PASS | private:my dentist a, shared:the project  |
| delete touches one scope only | PASS | 1 row(s) left |
| an expiring shared row does not expire the private row | PASS | 2 row(s) left after ttl |
| a federated transaction is refused, not faked | PASS | FederationError raised |
| an unknown scope is refused | PASS | "both" rejected: it is not a store |
| a scoped transaction rolls back | PASS | row absent after abort |

Eight checks, no mocks: both halves are a full `Storage` implementation with tags, ttl,
prefix queries and a rollback-capable transaction. What is *not* implemented is a
cross-store commit, and check 7 asserts that the router refuses rather than approximates.
