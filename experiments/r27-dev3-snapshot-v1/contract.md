# r27 dev3 snapshot v1 measurement contract

Design status: Frozen
Design revision: r27-dev3-snapshot-v1
Frozen at: 2026-08-23T14:32:57+09:00

## Purpose

r27 replaces the unexecuted r26 comparison set with the three allocator builds
requested for the actual experiment: mimalloc v2.1.2, v3.5.0, and one immutable
snapshot of the upstream `dev3` branch. r26 remains historical and no r26
record is reclassified or pooled with r27.

The moving `dev3` ref was resolved on 2026-08-23 at approximately 05:25 UTC to
commit `622d421f647fc41a2dfe90bc45174770129d78b4` (`fix natural alignment`,
committed 2026-08-22T03:49:29-07:00). Source fetch, build, measurement, and
reporting use that SHA only. A later movement of `dev3` does not change this
experiment; comparing a later HEAD requires a new revision and namespace.

## Compared allocators and environment

- mimalloc v2.1.2, commit `43ce4bd7fd34bcc730c1c7471c99995597415488`
- mimalloc v3.5.0, commit `18b08671c9302247bfb682286e6bf3cc1773f801`
- mimalloc dev3 snapshot, commit
  `622d421f647fc41a2dfe90bc45174770129d78b4`
- Rocky Linux 8 image digest
  `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`
- benchmark SHA-256
  `69040b1310b1e2f630606631daffd7f8316064a5c7228b6ffd7b0e4493bca2f9`
- cpuset `0,2,4,6,8,10,12,14`, memory node 0, THP `madvise`
- network disabled, fresh benchmark process, no CPU quota, no inherited
  `MIMALLOC_*` variables

The dev3 library was built in the same image and Release profile as v3.5.0.
Its library SHA-256 is
`49a1be072b80b98fced4135ae5d835a5fe8576648ca2949a8b9a6a70acdba95d`;
the allocator detector reports version integer 30500. A fixed-cpuset local
correctness smoke completed 100,000 allocations with valid checksum and exact
allocator provenance before this contract was frozen.

Every measured repetition is a matched three-build block. The order of blocks
and allocator arms is deterministic from seed 20260827. Each measured cell
requires 15 complete valid repetitions; incomplete triplets remain immutable
but are excluded from comparative analysis.

## Fixed benchmark contents

### Core processing profile

The r25-calibrated operation counts are retained because v2.1.2 and v3.5.0 are
unchanged and the dev3 snapshot reports the same 3.5.0 API version. The five
cells remain:

1. local fixed 64 B, 8 threads, one-at-a-time FIFO, 1,000,000,000 operations
2. local mixed-wide, 1 thread, batch 32 random free, 200,000,000 operations
3. local mixed-wide, 8 threads, batch 32 random free, 1,047,000,000 operations
4. remote fixed 64 B, 4 producers and 4 consumers, 100,000,000 operations
5. remote mixed-wide, 4 producers and 4 consumers, 100,000,000 operations

All use `malloc/free`, first-and-last touching, and upstream runtime defaults.
The local cell is the low-contention control. The remote cells are primary
because the preceding r25 study found its largest v3.5.0 differences there.

### Memory-return profile

Each cell allocates and touches a 512 MiB working set (8,192 objects of 64 KiB),
frees it, and observes RSS after 0, 1000, or 5000 ms. Upstream defaults and
explicit `MIMALLOC_PURGE_DELAY=1000` are separate arms. This distinguishes
release-policy changes on dev3 from allocator throughput changes.

### Tail-latency companion

Two eight-worker `tcp_policy_record` cells are retained: allocator-only and
service stage work. Both use deterministic 1/1024 sampling, 69,113,376 measured
operations, 691,133 warm-up operations, and a five-second post-drain RSS
observation. They are never pooled with Core throughput.

## Execution and durability rules

- Run the isolated smoke stage before measured profiles; smoke is correctness
  evidence only.
- A normal invocation executes at most one complete matched block. Repeated
  invocations resume from immutable per-attempt records.
- Preflight validates the contract, runner, benchmark and allocator hashes,
  cpuset, memory node, THP, and inherited mimalloc variables before execution.
- Each arm has a 90-second timeout. Timeout, crash, malformed output,
  allocator/operation mismatch, checksum failure, or cgroup throttling makes
  the attempt invalid without deleting it.
- Atomic raw/log/audit writes and a namespace lock prevent partial overwrite
  or concurrent runners from sharing an attempt number.
- Results are written only under
  `results/active/r27-dev3-snapshot-v1/`; r2--r26 paths are never scanned.

## Analysis and validity

Only complete matched triplets are compared. Report distributions, matched
ratios, and confidence intervals for v3.5.0/v2.1.2,
dev3-snapshot/v2.1.2, and dev3-snapshot/v3.5.0. The final ratio is the direct
upgrade signal. The report must call the third build a dev3 snapshot, not an
official release or a permanently current branch result.

## Resource estimate

Core contains 225 measured arms and is expected to require about 60--75
minutes plus setup. Memory-return contains 270 arms; latency contains 90 arms.
The one-block default bounds each invocation and enables safe continuation.

## Amendments

2026-08-23: The first all-profile smoke command stopped before preflight and
before creating any raw record because Rocky Linux 8's Python 3.6 rejected
Python 3.7+ annotation syntax in the runner. The runner was syntax-ported to
Python 3.6 without changing execution, validation, scheduling, or record
semantics; its corrected SHA-256 is frozen in the plan. This setup failure is
not a benchmark attempt or performance observation.

Any later dev3 commit, workload, artifact, environment, operation count,
validity rule, or runner semantic change requires a new design revision and
result namespace.
