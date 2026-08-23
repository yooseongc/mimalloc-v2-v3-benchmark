# r26 baseline v1 measurement contract

Design status: Frozen
Design revision: r26-baseline-v1
Frozen at: 2026-08-23T14:03:00+09:00

## Purpose

r26 establishes one small, authoritative benchmark surface after the r2--r25
development epochs accumulated multiple runners, plans, and result layouts.
It does not reinterpret or pool historical records. The selected cells come
from the completed r25 fixed-harness experiment and retain workloads that
separated the versions or represent important controls.

## Compared allocators and environment

- mimalloc v2.1.2, commit `43ce4bd7fd34bcc730c1c7471c99995597415488`
- mimalloc v3.4.3, commit `152fbf2634aeafca3774df791b0a77683035f076`
- mimalloc v3.5.0, commit `18b08671c9302247bfb682286e6bf3cc1773f801`
- Rocky Linux 8 image digest
  `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`
- benchmark SHA-256
  `69040b1310b1e2f630606631daffd7f8316064a5c7228b6ffd7b0e4493bca2f9`
- cpuset `0,2,4,6,8,10,12,14`, memory node 0, THP `madvise`
- network disabled, fresh benchmark process, no CPU quota, no inherited
  `MIMALLOC_*` variables

Every repetition is a matched three-version block. The order of blocks and
allocator arms is deterministic from seed 20260823. All measured cells have
15 valid complete repetitions; incomplete triplets are retained but excluded
from comparative analysis.

## Fixed benchmark contents

### Core processing profile

The five r25 cells are retained with their r25 pilot-calibrated operation
counts (combined-version median measured duration was 13.98--18.97 seconds):

1. local fixed 64 B, 8 threads, one-at-a-time FIFO, 1,000,000,000 operations
2. local mixed-wide, 1 thread, batch 32 random free, 200,000,000 operations
3. local mixed-wide, 8 threads, batch 32 random free, 1,047,000,000 operations
4. remote fixed 64 B, 4 producers and 4 consumers, 100,000,000 operations
5. remote mixed-wide, 4 producers and 4 consumers, 100,000,000 operations

All use `malloc/free`, first-and-last touching, and upstream runtime defaults.
The local fixed cell is the low-contention control; the remote cells are kept
because r25 found the largest v3.5.0/v3.4.3 throughput differences there.

### Memory-return profile

Each cell allocates and touches a 512 MiB working set (8,192 objects of 64 KiB),
frees it, and observes RSS at the selected idle interval. Upstream defaults and
explicit `MIMALLOC_PURGE_DELAY=1000` are separate policy arms. Idle points are
0, 1000, and 5000 ms: immediate state, the matched purge boundary, and the
settled endpoint. The earlier 10 and 100 ms points are intentionally omitted
because r25 found no material version separation and the reduced matrix lowers
execution cost without changing the stated question.

### Tail-latency companion

Two eight-worker `tcp_policy_record` cells are retained: allocator-only stage
work and service-like stage work. Both use deterministic 1/1024 latency
sampling, 69,113,376 measured operations, 691,133 warm-up operations, and a
five-second post-drain RSS observation. This profile is never pooled with Core
throughput.

## Execution and durability rules

- Run smoke before measured profiles; smoke is correctness evidence only.
- A normal invocation executes at most one complete matched block. Repeated
  invocations resume from immutable per-attempt records.
- Preflight validates contract, artifact hashes, cpuset, memory node, THP, and
  the absence of inherited mimalloc variables before starting a benchmark.
- The plan pins the active runner SHA-256 as well as the benchmark and
  allocator hashes; changing runner semantics therefore cannot silently resume
  this result namespace.
- Each arm has a 90-second process timeout. Timeout, crash, malformed output,
  allocator mismatch, operation-count mismatch, or cgroup CPU throttling makes
  that attempt invalid but does not erase it.
- Stdout, stderr, audit, and raw record writes use atomic replacement. A later
  valid retry does not overwrite an invalid attempt.
- Results are written only to `results/active/r26-baseline-v1/`; historical
  directories are never scanned for resume or analysis.

## Analysis and validity

Comparisons use only repetitions containing one valid record for every
version. Report medians, dispersion, matched ratios, and confidence intervals
for v3.4.3/v2.1.2, v3.5.0/v2.1.2, and v3.5.0/v3.4.3. Higher throughput and
lower elapsed time/latency/RSS are interpreted in their respective directions.
No historical result is silently reclassified as r26 evidence.

## Resource estimate

Core contains 225 measured arms and is expected to require about 60--75
minutes plus setup. Memory return contains 270 arms; latency contains 90 arms.
The one-block default bounds each invocation and allows safe continuation.

## Amendments

None. Any workload, artifact, environment, operation count, validity rule, or
runner semantic change requires a dated amendment, a new design revision, and
a new result namespace.
