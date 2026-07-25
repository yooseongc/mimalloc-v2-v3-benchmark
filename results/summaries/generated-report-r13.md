# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier2-thp-never-cpuset-r13.json
- Raw records: 1513
- Valid, de-duplicated records: 1450
- Valid records in analysis scope: 120
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier2-burst-purge-thp-never-r9-cpuset-r13 | burst_purge | 1 | 212 | 15 | 5.567e+04 | 0.002325 |
| tier2-burst-purge-thp-never-r9-cpuset-r13 | burst_purge | 1 | 30403 | 15 | 5.541e+04 | 0.001445 |
| tier2-large-alloc-thp-never-r9-cpuset-r13 | large_alloc | 1 | 212 | 15 | 1333 | 0.0376 |
| tier2-large-alloc-thp-never-r9-cpuset-r13 | large_alloc | 1 | 30403 | 15 | 1307 | 0.05587 |
| tier2-lifetime-mix-thp-never-r9-cpuset-r13 | lifetime_mix | 1 | 212 | 15 | 4.081e+07 | 0.01848 |
| tier2-lifetime-mix-thp-never-r9-cpuset-r13 | lifetime_mix | 1 | 30403 | 15 | 4.137e+07 | 0.01279 |
| tier2-thread-churn-thp-never-r9-cpuset-r13 | thread_churn | 1 | 212 | 15 | 1.288e+04 | 0.06666 |
| tier2-thread-churn-thp-never-r9-cpuset-r13 | thread_churn | 1 | 30403 | 15 | 1.679e+04 | 0.0224 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier2-burst-purge-thp-never-r9-cpuset-r13 | 15 | 0.9953 | 0.9947 .. 0.9974 |
| tier2-large-alloc-thp-never-r9-cpuset-r13 | 15 | 1.002 | 0.9657 .. 1.017 |
| tier2-lifetime-mix-thp-never-r9-cpuset-r13 | 15 | 1.012 | 1.001 .. 1.026 |
| tier2-thread-churn-thp-never-r9-cpuset-r13 | 15 | 1.315 | 1.283 .. 1.398 |
