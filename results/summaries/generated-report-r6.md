# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-full-core-r6.json
- Raw records: 793
- Valid, de-duplicated records: 730
- Valid records in analysis scope: 150
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier1-full-local-fixed-t8-r6 | local_churn | 8 | 212 | 15 | 9.898e+07 | 0.3145 |
| tier1-full-local-fixed-t8-r6 | local_churn | 8 | 30403 | 15 | 1.034e+08 | 0.3072 |
| tier1-full-local-mixed-wide-t1-r6 | local_churn | 1 | 212 | 15 | 1.709e+07 | 0.2415 |
| tier1-full-local-mixed-wide-t1-r6 | local_churn | 1 | 30403 | 15 | 1.707e+07 | 0.2338 |
| tier1-full-local-mixed-wide-t8-r6 | local_churn | 8 | 212 | 15 | 1.058e+08 | 0.1985 |
| tier1-full-local-mixed-wide-t8-r6 | local_churn | 8 | 30403 | 15 | 1.056e+08 | 0.195 |
| tier1-full-remote-fixed-4x4-r6 | remote_free | 8 | 212 | 15 | 5.467e+06 | 0.1149 |
| tier1-full-remote-fixed-4x4-r6 | remote_free | 8 | 30403 | 15 | 5.801e+06 | 0.08165 |
| tier1-full-remote-mixed-wide-4x4-r6 | remote_free | 8 | 212 | 15 | 5.519e+06 | 0.07923 |
| tier1-full-remote-mixed-wide-4x4-r6 | remote_free | 8 | 30403 | 15 | 5.773e+06 | 0.1081 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier1-full-local-fixed-t8-r6 | 15 | 1.036 | 0.9786 .. 1.106 |
| tier1-full-local-mixed-wide-t1-r6 | 15 | 1.004 | 0.9903 .. 1.016 |
| tier1-full-local-mixed-wide-t8-r6 | 15 | 0.9917 | 0.9767 .. 1.018 |
| tier1-full-remote-fixed-4x4-r6 | 15 | 1.042 | 0.9993 .. 1.117 |
| tier1-full-remote-mixed-wide-4x4-r6 | 15 | 1.025 | 1.004 .. 1.164 |
