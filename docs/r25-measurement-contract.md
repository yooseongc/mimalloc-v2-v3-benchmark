# r25 fixed measurement contract

Design status: Frozen
Design revision: r25-contract-v1
Frozen at: 2026-08-22T12:35:13+09:00

## Scope

r25 is the authoritative, non-pooled comparison of mimalloc v2.1.2, v3.4.3,
and v3.5.0. Earlier epochs remain immutable historical evidence. All r25
profiles use benchmark SHA-256
`69040b1310b1e2f630606631daffd7f8316064a5c7228b6ffd7b0e4493bca2f9`,
Rocky Linux 8 image
`sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`,
cpuset `0,2,4,6,8,10,12,14`, NUMA node 0, THP `madvise`, network disabled,
fresh processes, seed 20260825, and matched three-version blocks.

## Frozen profiles

1. Core: five r24 workload cells; elapsed, throughput, CPU time, faults,
   peak/final RSS fields; three pilot and 15 core repetitions.
2. Latency: `tcp_policy_record`, sample rate 1/1024, p50/p90/p95/p99/p99.9/max,
   sample count, CPU, faults, peak RSS, and post-drain RSS at 0–5000 ms.
3. Memory return: `burst_purge`, 512 MiB touched working set, idle points
   0/10/100/1000/5000 ms; RSS after free/idle plus 50 ms sampled Rss, Pss,
   Private_Dirty and AnonHugePages. Upstream-default and purge-delay=1000 are
   separate arms.
4. Perf companion: core fixed-small local and remote cells; task-clock, cycles,
   instructions, branches, branch-misses, cache references/misses, context
   switches and page faults. Unavailable counters are reported unavailable.

Diagnostic instrumentation is never pooled with Core throughput. Every profile
uses identical fields and settings across all three versions. Missing fields,
wrong allocator/SHA/cpuset/THP, crash, checksum failure, OOM, throttling, or an
incomplete three-version repetition invalidate the matched block.

## Amendments

None. Changes require a dated amendment and a new block prefix; existing raw
records are never reclassified or overwritten.
