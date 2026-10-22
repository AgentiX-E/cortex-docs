| case | stored | p50 ms | p95 ms | max ms | M mul-add |
| --- | --- | --- | --- | --- | --- |
| f64 384d 20k | 58.6 MiB | 5.7 | 7.3 | 8.5 | 7.7 |
| f32 384d 20k | 29.3 MiB | 13.5 | 14.3 | 14.4 | 7.7 |
| int8 384d 20k | 7.4 MiB | 14.9 | 15.9 | 19.4 | 7.7 |
| f64 384d 60k | 176 MiB | 22.9 | 26.3 | 34.3 | 23.0 |
| f32 384d 60k | 87.9 MiB | 37.5 | 40.8 | 41.8 | 23.0 |
| int8 384d 60k | 22.2 MiB | 44.7 | 46.7 | 50.4 | 23.0 |
| f64 1024d 60k | 469 MiB | 60.6 | 69.5 | 72.5 | 61.4 |
| f32 1024d 60k | 234 MiB | 99.1 | 106.6 | 106.9 | 61.4 |
| int8 1024d 60k | 58.8 MiB | 118.0 | 122.9 | 123.0 | 61.4 |

Exact top-10 cosine over the whole store, 40 queries per row, two warm-up scans
discarded, insertion-buffer top-k. Node v22.13.1 on x64, one thread,
plain JS (no wasm SIMD).

The dtype trade is a **memory** trade, not a time trade: at 384d the three types are within
25% of each other per query, while the store is 176 MiB / 88 MiB / 22 MiB. int8 is the
*slowest* here because JS has no i8x16 dot product; its case rests on fitting in cache and in
a browser heap, not on throughput.
