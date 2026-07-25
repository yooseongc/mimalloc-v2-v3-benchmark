# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier3-api-r17.json
- Raw records: 1693
- Valid, de-duplicated records: 1600
- Valid records in analysis scope: 90
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier3-api-aligned-local-fixed-r17 | local_churn | 1 | 212 | 15 | 1.176e+07 | 0.02211 |
| tier3-api-aligned-local-fixed-r17 | local_churn | 1 | 30403 | 15 | 1.193e+07 | 0.0507 |
| tier3-api-cpp-new-local-fixed-r17 | local_churn | 1 | 212 | 15 | 1.302e+07 | 0.02167 |
| tier3-api-cpp-new-local-fixed-r17 | local_churn | 1 | 30403 | 15 | 1.352e+07 | 0.02894 |
| tier3-api-realloc-local-fixed-r17 | local_churn | 1 | 212 | 15 | 1.032e+07 | 0.03339 |
| tier3-api-realloc-local-fixed-r17 | local_churn | 1 | 30403 | 15 | 1.066e+07 | 0.02949 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier3-api-aligned-local-fixed-r17 | 15 | 1.03 | 0.9805 .. 1.034 |
| tier3-api-cpp-new-local-fixed-r17 | 15 | 1.041 | 1.015 .. 1.045 |
| tier3-api-realloc-local-fixed-r17 | 15 | 1.04 | 1.032 .. 1.046 |
