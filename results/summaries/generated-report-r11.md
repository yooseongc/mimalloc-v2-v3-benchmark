# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier3-runtime-r11.json
- Raw records: 913
- Valid, de-duplicated records: 850
- Valid records in analysis scope: 60
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier3-large-os-pages-large-alloc-r11 | large_alloc | 1 | 212 | 15 | 7462 | 0.1434 |
| tier3-large-os-pages-large-alloc-r11 | large_alloc | 1 | 30403 | 15 | 7763 | 0.1049 |
| tier3-numa-nodes-1-large-alloc-r11 | large_alloc | 1 | 212 | 15 | 1350 | 0.02986 |
| tier3-numa-nodes-1-large-alloc-r11 | large_alloc | 1 | 30403 | 15 | 7445 | 0.2178 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier3-large-os-pages-large-alloc-r11 | 15 | 1 | 0.9692 .. 1.063 |
| tier3-numa-nodes-1-large-alloc-r11 | 15 | 5.532 | 4.727 .. 5.905 |
