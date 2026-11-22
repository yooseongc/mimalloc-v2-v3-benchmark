# r29 mimalloc v3.5.3 comparison

Design status: Frozen
Frozen at: 2026-09-21T10:32:11.680877+00:00
Design revision: r29-v353-v1
Created: 2026-09-21

## Purpose and hypotheses

Compare v3.5.3 with v3.5.0 (upgrade effect) and v2.1.2 (legacy baseline).
All three builds are rerun; r25/r27/r28 results are historical and never pooled.
The official v3.5.3 source readme describes improved free performance in
v3.5.1, reduced cache contention in v3.5.2, and a first-new-on-thread fix in
v3.5.3. Hypotheses, not conclusions: remote-free throughput may improve;
local throughput may remain similar; memory return may change independently.

Sources: https://github.com/microsoft/mimalloc/releases/tag/v3.5.3 and
https://github.com/microsoft/mimalloc/blob/v3.5.3/readme.md.

## Immutable sources and build

| Version | Commit |
|---|---|
| v2.1.2 | 43ce4bd7fd34bcc730c1c7471c99995597415488 |
| v3.5.0 | 18b08671c9302247bfb682286e6bf3cc1773f801 |
| v3.5.3 | d4881d338125e1cb7c47ba4cfb398d6f7c0c8d45 |

v3.5.3 is an annotated tag: deac3dcf5f0614884013d411a5c07e16bec96c9f
peels to the commit above. Sources remain unmodified. Separate install prefixes,
Release -O3 -DNDEBUG, shared malloc override, secure/tracking disabled, supported
options only; retain upstream architecture/TLS defaults and record CMake caches.
Use the existing Rocky Linux 8 image
sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877.
One unchanged r28 benchmark binary is used for every allocator, SHA-256
cae35ae342d94552be35fec06de5f46a7a108496dbb59debc18f6c201aa6528b.

## Environment and controls

Local Docker Desktop Linux VM; Rocky 8.9 userspace. cpuset 0,2,4,6,8,10,12,14
(one logical CPU per exposed physical core), memory node 0, THP madvise,
network disabled, no CPU quota. No host-wide settings are changed. Capture
kernel/compiler/glibc, image ID, CPU topology, memory/swap, NUMA, THP and perf
availability. VM host load/frequency and Windows scheduling remain uncontrolled.
Artifacts, worker affinity, loaded allocator and operation counts are validated.
Clean MIMALLOC environment, fresh process per arm, same binary/seed/workload.

## Matrix and procedure

Core: inherit exactly the five r27 definitions (local 64 B/8 workers; local
mixed-wide/1 and 8 workers; remote 64 B and mixed-wide/4 producers + 4 consumers).
Primary API malloc/free, first-and-last touch, upstream-default runtime policy.
The three local cells and two remote cells retain batch/order/queue settings
from the source plan. Full values are materialized in plan.json.

Memory: inherit all six enhanced r28 cells, each 512 MiB, 8192 x 64 KiB,
per-page touch, observations at 0/10/100/1000/5000 ms, then same-size reallocation.
Passive default, passive purge_delay=1000, passive purge_delay=0, allocator
activity, mi_collect(false), mi_collect(true). Explicit purge policies are
reported separately from upstream defaults; collect API cells are diagnostics.

Latency: inherit the two r27 tcp_policy_record cells (allocator and service
work), deterministic 1/1024 sampling and five-second post-drain observation.
These are separate from core throughput. Existing workload distributions,
retention, seeds and warm-up counts are fully specified in plan.json.

Before measured execution: correctness, first-new thread diagnostic, all-cell
smoke; three pilot repetitions per core/latency cell using historical operation
counts. Calibrate each cell to at least five seconds (target 10 seconds) for
the fastest pilot median, shared across all versions. Memory observations have
fixed durations. Freeze plan, contract and artifact hashes only after pilot.
Pilot data live under pilot/, smoke under smoke/, measured under measured/.

Measured: 15 complete matched three-version repetitions per cell; increase to
30 for a cell if any pilot throughput CV exceeds 10%. Seeded block/arm ordering
uses 20260921. Repetitions cannot be reduced after viewing results.
Timeout 180 seconds per arm. Default invocation executes one matched block;
--max-blocks 0 explicitly runs all pending blocks. Immutable attempts and locks
support resumption. Never compare unmatched historical runs.

## Analysis and validity

Report median/mean/stdev/CV/min/max/quartiles/IQR and matched ratio bootstrap
95% intervals (10000 draws, deterministic seeds). Throughput ratio >1 favors
the numerator; elapsed/CPU/RSS ratio <1 favors the numerator. Report all three
pairs, particularly v3.5.3/v3.5.0. Memory uses baseline-adjusted returned fraction
and absolute RSS checkpoints, free cost and reuse cost. Zero-denominator ratios
are unavailable; differences remain meaningful. A field called peak_rss_bytes
in the inherited core harness is an end-of-run RSS sample, not peak RSS, and
must not be described as a peak. Tail latency sampling overhead is not subtracted.

Invalid: nonzero exit, timeout, malformed output, allocation/checksum failure,
wrong allocator/version/library/hash, wrong counts/affinity, CPU throttling,
artifact or controlled-environment mismatch. Preserve all failures and report
retries; do not discard slow or fast samples as outliers. Incomplete matched
blocks are excluded from pair comparisons. No perf or unmeasured result is
invented. Confidence intervals do not correct for multiple workload comparisons.

## Resources and limits

Initial matrix: 585 measured arms (225 core, 270 memory, 90 latency), plus
39 smoke and 63 pilot arms. Expect roughly 1.5--3 hours including setup and
potential high-variance repeat increases; update estimate from pilot. Memory
working set is approximately 512 MiB plus allocator overhead, one process at a
time, comfortably below the observed approximately 30 GiB available VM memory.
No concurrent benchmark jobs. Perf may be unavailable. No cross-NUMA, THP
sweep, secure-build sweep or Windows-native performance claims in this revision.

## Amendments

2026-09-21: All 39 smoke and 63 core/latency pilot arms passed. Operation
counts are scaled to ten seconds for the fastest version's pilot median,
rounded upward to a multiple of 32. Cells exceeding 10% pilot throughput CV
receive 30 repetitions; other cells receive 15. See calibration.json for
all observations, counts and the resource estimate. Draft plan/contract
copies preserve the exact smoke/pilot provenance. No measured data existed
when these choices were made.

Inherited-harness limitations established by source inspection before full
measurement: local and remote core paths do not implement warm-up (zero
is recorded); local timing includes small vector setup and thread joins;
remote timing includes shared atomic checksum/count overhead. Memory-return
is single-threaded within the fixed eight-CPU cpuset and does not pin its
main thread to one particular CPU. Core/pipeline workers are pinned by the
harness, but per-worker CPU observations are not exported in every scenario.
These deviations are retained to use one unchanged historical binary and
must be disclosed. Results describe these workloads, not pure allocator
instruction cost. Only pipeline cells have explicit 1% warm-up.

v3.5.3 enables statistics/profiling support and full THP preservation by
default. Matching purge_delay alone is a one-variable policy comparison,
not complete normalization of THP or instrumentation defaults. No fully
normalized allocator-implementation claim is made. perf cycles/instructions
and get_mempolicy are permission-denied; node 0 is the only allowed/exposed
NUMA node. First-new diagnostics passed 1000 threads per version.

Before measured runs, the r29 wrapper was hardened to decode byte output
from subprocess timeouts before durable log writes. A regression test
verifies timeout attempts remain recorded as invalid. Workload commands,
timing and successful-output validation are unchanged. draft-runner.py
preserves the smoke/pilot runner; the measured runner hash is frozen anew.
