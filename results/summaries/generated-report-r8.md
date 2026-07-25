# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-purge-r8.json
- Raw records: 793
- Valid, de-duplicated records: 730
- Valid records in analysis scope: 90
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier2-purge--1-r8 | burst_purge | 1 | 212 | 15 | 5.526e+04 | 0.003626 |
| tier2-purge--1-r8 | burst_purge | 1 | 30403 | 15 | 5.53e+04 | 0.003815 |
| tier2-purge-0-r8 | burst_purge | 1 | 212 | 15 | 1.631e+04 | 0.0293 |
| tier2-purge-0-r8 | burst_purge | 1 | 30403 | 15 | 1.627e+04 | 0.01611 |
| tier2-purge-1000-r8 | burst_purge | 1 | 212 | 15 | 5.524e+04 | 0.002207 |
| tier2-purge-1000-r8 | burst_purge | 1 | 30403 | 15 | 5.508e+04 | 0.002878 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier2-purge--1-r8 | 15 | 1 | 0.9991 .. 1.004 |
| tier2-purge-0-r8 | 15 | 0.9986 | 0.9821 .. 1.005 |
| tier2-purge-1000-r8 | 15 | 0.9974 | 0.9962 .. 0.9999 |
