| metric | value | note |
| --- | --- | --- |
| rows written | 10000 | KV table with a tag index, one transaction |
| write throughput | 56850 rows/s | 176 ms for the insert batch |
| checkpoint | 1 ms | flush to OPFS, without it a killed tab loses the batch |
| point read | 0.047 ms | 200 lookups, primary key |
| tag query | 3.20 ms | 100 rows via the tags index |
| full scan | 60 ms | 10000 rows back through the JS boundary |
| digest, launch 1 | 128079214 | FNV-1a over every payload |
| digest, launch 2 | 128079214 | new browser process, same profile |
| persisted across restart | YES | rows 10000 vs 10000 |
| profile size on disk | 10.9 MiB | includes Chromium's own profile files |
| vector scan 20k x 384, in tab | 5.6 ms p50 | p95 9.8 ms, 29.3 MiB held |
| vector scan 60k x 384, in tab | 22.3 ms p50 | p95 33.4 ms, 87.9 MiB held |
| vector scan 20k x 1024, in tab | 18.7 ms p50 | p95 25.1 ms, 78.1 MiB held |

SQLite 3.54.1 via `@sqlite.org/sqlite-wasm`, `opfs-sahpool` VFS inside a module Worker,
Chromium headless, no cross-origin isolation headers.
Phase 1 writes and closes the browser; phase 2 is a new process reading the same profile.
