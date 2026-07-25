# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-tier3-build-r10.json
- Raw records: 853
- Valid, de-duplicated records: 790
- Valid records in analysis scope: 60
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier3-local-dynamic-tls-local-fixed-r10 | local_churn | 8 | 212 | 15 | 8.844e+07 | 0.1131 |
| tier3-local-dynamic-tls-local-fixed-r10 | local_churn | 8 | 30403 | 15 | 9.07e+07 | 0.1198 |
| tier3-secure-local-fixed-r10 | local_churn | 1 | 212 | 15 | 1.374e+07 | 0.06827 |
| tier3-secure-local-fixed-r10 | local_churn | 1 | 30403 | 15 | 1.469e+07 | 0.05959 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier3-local-dynamic-tls-local-fixed-r10 | 15 | 1.023 | 1.002 .. 1.047 |
| tier3-secure-local-fixed-r10 | 15 | 1.08 | 1.067 .. 1.114 |
