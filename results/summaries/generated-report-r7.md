# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier2-r7.json
- Raw records: 793
- Valid, de-duplicated records: 730
- Valid records in analysis scope: 120
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier2-burst-purge-r7 | burst_purge | 1 | 212 | 15 | 5.525e+04 | 0.001837 |
| tier2-burst-purge-r7 | burst_purge | 1 | 30403 | 15 | 5.512e+04 | 0.001769 |
| tier2-large-alloc-r7 | large_alloc | 1 | 212 | 15 | 1243 | 0.1025 |
| tier2-large-alloc-r7 | large_alloc | 1 | 30403 | 15 | 2677 | 0.5626 |
| tier2-lifetime-mix-r7 | lifetime_mix | 1 | 212 | 15 | 3.663e+07 | 0.04613 |
| tier2-lifetime-mix-r7 | lifetime_mix | 1 | 30403 | 15 | 3.714e+07 | 0.0416 |
| tier2-thread-churn-r7 | thread_churn | 1 | 212 | 15 | 1.134e+04 | 0.02833 |
| tier2-thread-churn-r7 | thread_churn | 1 | 30403 | 15 | 1.513e+04 | 0.0326 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier2-burst-purge-r7 | 15 | 0.9987 | 0.9963 .. 0.9995 |
| tier2-large-alloc-r7 | 15 | 2.168 | 2.162 .. 3.786 |
| tier2-lifetime-mix-r7 | 15 | 1.011 | 0.9983 .. 1.047 |
| tier2-thread-churn-r7 | 15 | 1.334 | 1.307 .. 1.364 |
