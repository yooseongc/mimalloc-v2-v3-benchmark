# Generated measurement appendix

This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.

## Collection status

- Analysis scope: manifests\execution-plan-cpuset-r12.json
- Raw records: 1393
- Valid, de-duplicated records: 1330
- Valid records in analysis scope: 480
- Duplicate raw records excluded from derivation: 63

## Per-allocator groups

| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |
|---|---|---:|---:|---:|---:|---:|
| tier1-full-local-fixed-t8-r6-cpuset-r12 | local_churn | 8 | 212 | 15 | 9.195e+07 | 0.03637 |
| tier1-full-local-fixed-t8-r6-cpuset-r12 | local_churn | 8 | 30403 | 15 | 9.491e+07 | 0.03456 |
| tier1-full-local-mixed-wide-t1-r6-cpuset-r12 | local_churn | 1 | 212 | 15 | 1.665e+07 | 0.02166 |
| tier1-full-local-mixed-wide-t1-r6-cpuset-r12 | local_churn | 1 | 30403 | 15 | 1.651e+07 | 0.03881 |
| tier1-full-local-mixed-wide-t8-r6-cpuset-r12 | local_churn | 8 | 212 | 15 | 9.996e+07 | 0.03968 |
| tier1-full-local-mixed-wide-t8-r6-cpuset-r12 | local_churn | 8 | 30403 | 15 | 9.833e+07 | 0.02681 |
| tier1-full-remote-fixed-4x4-r6-cpuset-r12 | remote_free | 8 | 212 | 15 | 5.657e+06 | 0.09899 |
| tier1-full-remote-fixed-4x4-r6-cpuset-r12 | remote_free | 8 | 30403 | 15 | 5.932e+06 | 0.07176 |
| tier1-full-remote-mixed-wide-4x4-r6-cpuset-r12 | remote_free | 8 | 212 | 15 | 5.6e+06 | 0.09885 |
| tier1-full-remote-mixed-wide-4x4-r6-cpuset-r12 | remote_free | 8 | 30403 | 15 | 5.806e+06 | 0.09536 |
| tier2-burst-purge-r7-cpuset-r12 | burst_purge | 1 | 212 | 15 | 5.56e+04 | 0.002607 |
| tier2-burst-purge-r7-cpuset-r12 | burst_purge | 1 | 30403 | 15 | 5.555e+04 | 0.001985 |
| tier2-large-alloc-r7-cpuset-r12 | large_alloc | 1 | 212 | 15 | 1334 | 0.04724 |
| tier2-large-alloc-r7-cpuset-r12 | large_alloc | 1 | 30403 | 15 | 3149 | 0.5105 |
| tier2-lifetime-mix-r7-cpuset-r12 | lifetime_mix | 1 | 212 | 15 | 4.053e+07 | 0.01674 |
| tier2-lifetime-mix-r7-cpuset-r12 | lifetime_mix | 1 | 30403 | 15 | 4.055e+07 | 0.02672 |
| tier2-purge--1-r8-cpuset-r12 | burst_purge | 1 | 212 | 15 | 5.558e+04 | 0.002096 |
| tier2-purge--1-r8-cpuset-r12 | burst_purge | 1 | 30403 | 15 | 5.571e+04 | 0.001733 |
| tier2-purge-0-r8-cpuset-r12 | burst_purge | 1 | 212 | 15 | 1.746e+04 | 0.006337 |
| tier2-purge-0-r8-cpuset-r12 | burst_purge | 1 | 30403 | 15 | 1.742e+04 | 0.01369 |
| tier2-purge-1000-r8-cpuset-r12 | burst_purge | 1 | 212 | 15 | 5.56e+04 | 0.002768 |
| tier2-purge-1000-r8-cpuset-r12 | burst_purge | 1 | 30403 | 15 | 5.549e+04 | 0.001767 |
| tier2-thread-churn-r7-cpuset-r12 | thread_churn | 1 | 212 | 15 | 1.248e+04 | 0.02193 |
| tier2-thread-churn-r7-cpuset-r12 | thread_churn | 1 | 30403 | 15 | 1.634e+04 | 0.02111 |
| tier3-large-os-pages-large-alloc-r11-cpuset-r12 | large_alloc | 1 | 212 | 15 | 7507 | 0.3345 |
| tier3-large-os-pages-large-alloc-r11-cpuset-r12 | large_alloc | 1 | 30403 | 15 | 5707 | 0.4589 |
| tier3-local-dynamic-tls-local-fixed-r10-cpuset-r12 | local_churn | 8 | 212 | 15 | 8.978e+07 | 0.02195 |
| tier3-local-dynamic-tls-local-fixed-r10-cpuset-r12 | local_churn | 8 | 30403 | 15 | 9.125e+07 | 0.02464 |
| tier3-numa-nodes-1-large-alloc-r11-cpuset-r12 | large_alloc | 1 | 212 | 15 | 1340 | 0.03962 |
| tier3-numa-nodes-1-large-alloc-r11-cpuset-r12 | large_alloc | 1 | 30403 | 15 | 3089 | 0.4221 |
| tier3-secure-local-fixed-r10-cpuset-r12 | local_churn | 1 | 212 | 15 | 1.385e+07 | 0.01418 |
| tier3-secure-local-fixed-r10-cpuset-r12 | local_churn | 1 | 30403 | 15 | 1.513e+07 | 0.02548 |

## Paired v3 / v2 ratios

| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |
|---|---:|---:|---:|
| tier1-full-local-fixed-t8-r6-cpuset-r12 | 15 | 1.032 | 1.024 .. 1.047 |
| tier1-full-local-mixed-wide-t1-r6-cpuset-r12 | 15 | 0.9903 | 0.9719 .. 1.001 |
| tier1-full-local-mixed-wide-t8-r6-cpuset-r12 | 15 | 0.9983 | 0.9726 .. 1.021 |
| tier1-full-remote-fixed-4x4-r6-cpuset-r12 | 15 | 1.012 | 0.9714 .. 1.089 |
| tier1-full-remote-mixed-wide-4x4-r6-cpuset-r12 | 15 | 1.011 | 0.9564 .. 1.079 |
| tier2-burst-purge-r7-cpuset-r12 | 15 | 0.9994 | 0.9979 .. 1.001 |
| tier2-large-alloc-r7-cpuset-r12 | 15 | 2.334 | 2.334 .. 4 |
| tier2-lifetime-mix-r7-cpuset-r12 | 15 | 1.009 | 0.9872 .. 1.018 |
| tier2-purge--1-r8-cpuset-r12 | 15 | 1.002 | 1.001 .. 1.003 |
| tier2-purge-0-r8-cpuset-r12 | 15 | 0.9963 | 0.9877 .. 1.001 |
| tier2-purge-1000-r8-cpuset-r12 | 15 | 0.9979 | 0.9961 .. 0.9994 |
| tier2-thread-churn-r7-cpuset-r12 | 15 | 1.309 | 1.301 .. 1.331 |
| tier3-large-os-pages-large-alloc-r11-cpuset-r12 | 15 | 0.8901 | 0.574 .. 1.407 |
| tier3-local-dynamic-tls-local-fixed-r10-cpuset-r12 | 15 | 1.012 | 1.002 .. 1.045 |
| tier3-numa-nodes-1-large-alloc-r11-cpuset-r12 | 15 | 2.295 | 2.014 .. 3.045 |
| tier3-secure-local-fixed-r10-cpuset-r12 | 15 | 1.09 | 1.073 .. 1.104 |
