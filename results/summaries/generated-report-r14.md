# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier3-smt-r14.json
- Raw records: 1543
- Valid, de-duplicated records: 1480
- Valid records in analysis scope: 30
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier3-smt-local-fixed-r14 | local_churn | 16 | 212 | 15 | 1.144e+08 | 0.0633 |
| tier3-smt-local-fixed-r14 | local_churn | 16 | 30403 | 15 | 1.191e+08 | 0.05525 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier3-smt-local-fixed-r14 | 15 | 1.041 | 0.9835 .. 1.092 |
