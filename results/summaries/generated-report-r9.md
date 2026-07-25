# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier2-thp-never-r9.json
- Raw records: 793
- Valid, de-duplicated records: 730
- Valid records in analysis scope: 120
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier2-burst-purge-thp-never-r9 | burst_purge | 1 | 212 | 15 | 5.519e+04 | 0.006091 |
| tier2-burst-purge-thp-never-r9 | burst_purge | 1 | 30403 | 15 | 5.493e+04 | 0.004892 |
| tier2-large-alloc-thp-never-r9 | large_alloc | 1 | 212 | 15 | 1275 | 0.05466 |
| tier2-large-alloc-thp-never-r9 | large_alloc | 1 | 30403 | 15 | 1239 | 0.08026 |
| tier2-lifetime-mix-thp-never-r9 | lifetime_mix | 1 | 212 | 15 | 3.715e+07 | 0.07108 |
| tier2-lifetime-mix-thp-never-r9 | lifetime_mix | 1 | 30403 | 15 | 3.739e+07 | 0.04007 |
| tier2-thread-churn-thp-never-r9 | thread_churn | 1 | 212 | 15 | 1.159e+04 | 0.05352 |
| tier2-thread-churn-thp-never-r9 | thread_churn | 1 | 30403 | 15 | 1.562e+04 | 0.04022 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier2-burst-purge-thp-never-r9 | 15 | 0.9958 | 0.9924 .. 0.9975 |
| tier2-large-alloc-thp-never-r9 | 15 | 0.9596 | 0.9269 .. 0.9841 |
| tier2-lifetime-mix-thp-never-r9 | 15 | 1.014 | 0.9844 .. 1.059 |
| tier2-thread-churn-thp-never-r9 | 15 | 1.371 | 1.329 .. 1.383 |
