| metric | value | note |
| --- | --- | --- |
| gold private | 12 | must never reach the shared store |
| gold shared | 8 | may, after confirmation |
| gold defer | 40 | decision handed to the user |
| false-share | 0 / 12 | Wilson 95% upper 24.2% |
| false-private | 4 / 8 | recoverable by one tap |
| coverage | 26.7% | decided by rules; the rest are cards |
| exact 3-way agreement | 85.0% | context, not a goal |
| stability over 10 passes | identical | deterministic by construction |

### Where each rule fired

| rule | fired | gold private | gold shared | gold defer |
| --- | --- | --- | --- | --- |
| defer | 44 | 3 | 3 | 38 |
| health | 6 | 5 | 0 | 1 |
| org-knowledge | 4 | 0 | 4 | 0 |
| money | 4 | 3 | 0 | 1 |
| family | 1 | 1 | 0 | 0 |
| third-party | 1 | 0 | 1 | 0 |

Rules in table order: credential -> strong-pii -> money -> health -> family -> career-status -> third-party -> org-knowledge. Private rules run first,
so a sentence that is organisational *and* personal stays private.
