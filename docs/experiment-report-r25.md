# r25 fixed-harness mimalloc comparison

Execution status: Complete with Perf counters unavailable

## Executive summary

r25 reran mimalloc v2.1.2, v3.4.3, and v3.5.0 under one frozen measurement
contract and benchmark binary. Core completed 225/225 valid records,
Memory-return 450/450, and Latency 90/90 after one predeclared backpressure
invalid arm was retained and rerun successfully. Perf counters were unavailable
because the kernel denied `task-clock`; no unavailable counter is represented as
zero.

The main v3.5.0/v3.4.3 result is workload-dependent: local throughput was
within +0.4% to +2.0%, while remote-free median throughput was 8.6% lower for
fixed 64 B and 6.5% lower for mixed-wide. Latency p99 was 42.1% higher in the
allocator-only pipeline and 6.5% higher in the service pipeline, despite
throughput being 1.4% and 4.0% higher respectively. Post-free/idle RSS was
essentially equal between v3.5.0 and v3.4.3 in the tested 512 MiB burst arms.

## Frozen environment

* Rocky Linux 8 image: `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`
* Benchmark SHA-256: `69040b1310b1e2f630606631daffd7f8316064a5c7228b6ffd7b0e4493bca2f9`
* CPU: `0,2,4,6,8,10,12,14`; NUMA node 0; THP `madvise`
* Network disabled; fresh process; matched three-version randomized blocks
* Contract: `docs/r25-measurement-contract.md`

## Core median throughput ratios

| Cell | v3.5.0 / v2.1.2 | v3.5.0 / v3.4.3 |
|---|---:|---:|
| local fixed 64 B, 8 threads | 1.0317 | 1.0035 |
| local mixed-wide, 1 thread | 0.9994 | 1.0080 |
| local mixed-wide, 8 threads | 1.0011 | 1.0198 |
| remote fixed 64 B, 4:4 | 0.9809 | 0.9139 |
| remote mixed-wide, 4:4 | 0.9293 | 0.9354 |

Each cell contains 15 complete matched repetitions. Ratio above 1 favors
v3.5.0.

## Latency companion: v3.5.0 / v3.4.3

| Cell | Throughput | p99 latency |
|---|---:|---:|
| isolated allocator pipeline | 1.0137 | 1.4210 |
| isolated service pipeline | 1.0395 | 1.0654 |

Latency used deterministic 1/1024 sampling and reports p50, p90, p95, p99,
p99.9, maximum, and sample count in raw records. Higher latency ratio is worse.
The result demonstrates a throughput/tail-latency trade-off rather than an
unqualified v3.5.0 improvement.

## Memory return

The profile allocated and touched a 512 MiB working set, freed it, and observed
idle points 0, 10, 100, 1000, and 5000 ms. Upstream-default and explicit
`MIMALLOC_PURGE_DELAY=1000` were separate arms. Across idle points of 10 ms or
more, median v3.5.0/v3.4.3 `rss_after_idle` ratios were 0.9997–1.0001 for the
matched-policy arm and approximately 1.0000 for upstream defaults. No material
post-free RSS advantage was observed.

The external sampler ran every 50 ms. Allocation and release could finish
between samples, especially at idle=0; sampled maximum RSS is therefore not a
reliable allocation peak for this burst. The result supports parity in observed
post-free RSS, not a claim that peak committed memory or release half-life is
identical.

## Invalid and unavailable results

One v2.1.2 Latency arm exceeded the frozen 5% aggregate-backpressure limit.
Its immutable invalid record remains in raw data; the arm was rerun under the
same frozen conditions and the complete valid matched repetition is used.
Core and Memory-return had no invalid records.

Perf status: unavailable. `perf stat` failed before measurement with “No
permission to enable task-clock event.” No privileged relaxation was used and
no counter was recorded as zero.

## Artifacts and reproduction

* Plans: `manifests/execution-plan-r25-core.json`,
  `manifests/execution-plan-r25-memory.json`,
  `manifests/execution-plan-r25-latency.json`
* Calibration: `manifests/calibration-r25-core.json`
* Summary: `results/summaries/summary-r25.json`
* Perf availability: `results/summaries/perf-r25-unavailable.json`
* Immutable raw data: `results/raw/` and profile subdirectories

```bash
python3 scripts/analyze_r25.py
```

## Conclusion

For local allocation, v3.5.0 and v3.4.3 are close. For the tested remote-free
patterns, v3.5.0 has lower median throughput, and the latency companion also
shows higher p99 latency. The tested post-free RSS is essentially equal; r25
does not establish superior memory return for v3.5.0. Adoption should therefore
be validated with the application's cross-thread-free rate and tail-latency
budget, not chosen solely from the version number.
