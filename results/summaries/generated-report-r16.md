# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier3-oversubscription-r16.json
- Raw records: 1603
- Valid, de-duplicated records: 1510
- Valid records in analysis scope: 30
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier3-oversubscription-local-fixed-r16 | local_churn | 16 | 212 | 15 | 8.966e+07 | 0.03507 |
| tier3-oversubscription-local-fixed-r16 | local_churn | 16 | 30403 | 15 | 9.428e+07 | 0.02353 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier3-oversubscription-local-fixed-r16 | 15 | 1.05 | 1.035 .. 1.086 |
