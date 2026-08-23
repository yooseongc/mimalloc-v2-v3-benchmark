# mimalloc v2.1.2 vs v3.4.3 vs v3.5.0 experiment design

Design status: Frozen
Design revision: frozen execution manifests r6--r9 (no repository commit available)
Frozen at: 2026-07-25T09:51:05Z

## 1. Purpose and scope

This study originally compared Microsoft mimalloc `v2.1.2` and `v3.4.3` in the same Rocky Linux 8 OCI container and host allocation domain. Amendment r24 adds `v3.5.0` as a separate three-version epoch. It measures allocation throughput, latency, CPU efficiency, RSS and release of OS memory. It does not claim that any version is universally faster.

Two result families are always reported separately:

1. **Upstream-default**: each Release build and runtime uses its upstream default policy; this quantifies the user-visible version change.
2. **Normalized-policy**: only settings supported by both tags and with equivalent documented meaning are set identically; this reduces policy drift when studying implementation differences.

The primary allocation API is `std::malloc`, `std::free`, and `std::realloc`. One C++17 benchmark executable is used for all compared versions; allocator selection is solely by `LD_PRELOAD`.

## 2. Compared sources

| Name | Repository | Requested tag | Resolved commit |
|---|---|---|---|
| mimalloc v2 | `https://github.com/microsoft/mimalloc.git` | `v2.1.2` | `43ce4bd7fd34bcc730c1c7471c99995597415488` |
| mimalloc v3 | `https://github.com/microsoft/mimalloc.git` | `v3.4.3` | `152fbf2634aeafca3774df791b0a77683035f076` |
| mimalloc v3 current | `https://github.com/microsoft/mimalloc.git` | `v3.5.0` | `18b08671c9302247bfb682286e6bf3cc1773f801` |

`manifests/sources.lock` will additionally record the fetch time, source path, `git describe`, and clean-tree result after sources are fetched. No upstream source is patched for primary results.

## 3. Hypotheses

* H1: v3 differs most from v2 under remote-free and thread-churn patterns, where cross-thread sharing and abandoned allocations matter.
* H2: local fixed-small churn has smaller version deltas and is more sensitive to CPU placement than to allocator version.
* H3: purge delay and THP mode trade lower RSS after a burst against subsequent allocation latency and page faults.
* H4: upstream-default and normalized-policy comparisons can lead to different conclusions; neither is substituted for the other.

These are pre-measurement hypotheses, not acceptance criteria.

## 4. Variables and controls

Independent variables are allocator version, comparison policy, scenario, thread topology/count, size/lifetime profile, touch mode, THP mode, and (Tier 2+) one memory-policy setting at a time. Dependent variables are elapsed time, ops/s, ns/op, allocation/free rates, sampled latency percentiles, CPU time, RSS/HWM/PSS, page faults, NUMA memory, and available perf counters.

The following are held constant within a paired block: container image digest, kernel, benchmark executable and SHA-256, compiler/flags, CPU/memory cpusets, worker-to-CPU map, operation/warm-up count, seed, queue capacity, host THP state, cgroup limits, and benchmark configuration. Runs are fresh processes.

## 5. Build and loading policy

Both libraries are built separately in Release mode with the same compiler and flags. The build script discovers CMake options from each checked-out tag before passing them; unsupported options are never silently supplied. The intended common baseline is `-O3 -DNDEBUG`, `MI_OVERRIDE=ON`, shared library enabled, and diagnostics/security instrumentation disabled where supported. Exact commands, CMake cache, flags, output path, library/header SHA-256, timestamp, and commit are written to `manifests/builds.json`.

Before every run, the harness validates the preloaded allocator through `/proc/<pid>/maps`, absolute library path and SHA-256, and `dlsym(mi_version)`. It rejects a system allocator fallback, mismatched version, mixed install prefixes, or two mimalloc libraries. Verbose allocator output is restricted to validation runs.

## 6. Workloads

All setup, thread creation, affinity, configuration parsing, queues, result buffers, allocator validation, and warm-up occur outside the timed region. Workers synchronize at a start barrier. Each workload performs a fixed operation count determined by pilot testing, aiming for 10--30 s (never below 5 s) per measured run.

| Scenario | Definition | Primary variants |
|---|---|---|
| `local_churn` | Worker allocates and frees its own objects. | one-by-one; batch FIFO/LIFO/random; fixed-small 64 B; fixed-medium 4 KiB; mixed-small 16 B--4 KiB; mixed-wide 16 B--64 KiB |
| `remote_free` | Producers allocate pointers and consumers free them through bounded queues. | 1:1, N:N, 1:N, N:1; queue-only control |
| `lifetime_mix` | Objects survive across cycles. | 70% short, 20% medium, 10% long lived; configured retention depths |
| `burst_purge` | Allocate/touch working set, free, idle, then repeat. | idle 0, 10, 100, 1000, 5000 ms |
| `thread_churn` | Repeated worker creation and exit, with later remote frees. | measured thread-cycle time and retained RSS |
| `large_alloc` | Large allocations with separate touch behavior. | 64 KiB, 256 KiB, 1/2/4/16/64 MiB |

The harness uses fixed seeds, writes actual size/lifetime distributions, stores a deterministic checksum, touches each allocation as configured, and verifies that every allocation is freed exactly once. Per-worker counters are cache-line separated; timed-region logging and global mutexes are forbidden. Latency uses documented batch sampling or a separate latency-focused run rather than timing every allocation.

Touch modes are `none`, `first-byte`, `first-and-last`, `per-cache-line`, `per-page`, and `full-write`. `first-and-last` is the primary throughput mode; `per-page` or `full-write` is required for THP/RSS/page-fault studies.

## 7. CPU, cgroup, NUMA, and memory-page controls

Primary runs use an explicit container cpuset, no CPU quota, one worker per logical CPU, and preferably non-SMT physical cores from one NUMA node. Memory is bound to that node. The worker-to-CPU map, `sched_getaffinity`, `Cpus_allowed_list`, cgroup effective cpuset, `nproc`, NUMA policy, and `cpu.stat` are collected before and after runs. An affinity mismatch or CPU throttling invalidates the run.

THP is host-managed and never changed by a normal benchmark command. Tier 2 runs use separate blocks for `never` and `madvise` (and `always` only if resources permit). The host control scripts save state and require explicit `--apply`; they restore saved state on normal exit/error. Each run records THP files, HugeTLB information, relevant `/proc/vmstat` counters, `smaps_rollup`, status, and `numa_maps`. Actual THP use is judged from `AnonHugePages` and related counters, not merely the requested mode.

## 8. Runtime policy matrix

`MIMALLOC_*` is cleared before every run; the full resulting set is stored. Upstream-default means no equivalent environment variable is injected. For normalized-policy experiments, one common setting is changed per block: `purge_delay` = 0, 1000, or -1; `arena_eager_commit` = 0 or 1; `numa_nodes` = 1; and `large_os_pages` = 0 or 1. The build/runtime scripts must verify availability and semantic correspondence per tag before scheduling each cell. Unsupported or version-only controls are recorded as unavailable, not approximated.

## 9. Execution tiers and matrix

| Tier | Purpose | Minimum cells | Repetitions |
|---|---|---|---|
| 0 | Correctness/smoke | every implemented scenario; both allocators; short fixed configuration | 1--3, not performance evidence |
| Pilot | Calibrate operations and check stability | core local/remote cells at 1 and P threads | >=3 each |
| 1 | Core comparison | `local_churn` and `remote_free`; fixed-small and mixed-wide; 1 and P threads; single NUMA; fixed THP; normalized policy | >=15 valid per cell |
| 2 | Memory policy | THP, purge, burst, lifetime, churn, large allocation, RSS release | >=15 valid core cells |
| 3 | Extended | defaults, secure/TLS, explicit large pages, HugeTLB, NUMA/SMT/oversubscription, APIs, v3-only controls | resource-dependent |

`P` is discovered physical-core availability in the selected cpuset; the sweep is `1, 2, 4, 8, P`, omitting values above P and duplicates. Remote-free worker totals never exceed assigned CPUs. Pilot freezes operation counts and may raise core repetitions to 30 when the coefficient of variation is high.

Allocator order is seed-randomized *within* each paired block (for example, v2/v3 then v3/v2); all v2 runs must not precede all v3 runs. Seeds, block IDs, and planned order are manifests. Warm-up counts are identical within a pair.

## 10. Metrics, validity, and analysis

Each repetition is an immutable JSON/JSONL record under `results/raw/` with the fields specified in `AGENTS.md`, including allocator provenance, topology, policy, elapsed time, latency samples/percentiles, CPU/RSS/fault/perf data, cgroup state, checksum, exit code, and stdout/stderr references. Unsupported metrics are `null`/`unavailable`, never zero.

Invalid runs retain their raw record and an explicit reason. Reasons include allocator-validation failure, checksum/free-count failure, process error/hang, affinity or NUMA mismatch, unexpected `MIMALLOC_*`, cgroup CPU throttling, wrong CPU mapping, and incompatible host setup. Perf permission failure is recorded as unavailable and does not by itself invalidate an otherwise valid non-perf run.

For every cell, analysis reports valid/invalid counts, median, mean, standard deviation, CV, min/max, p25/p75/IQR, and 95% confidence intervals. Primary v3/v2 comparisons use matched block pairs and report throughput, elapsed, peak RSS, and CPU-time ratios with paired bootstrap confidence intervals. Raw records are never deleted; a robust outlier sensitivity analysis may be shown separately, while primary results use all valid runs.

## 11. Environment capture and reproducibility

The Rocky Linux 8 image is pinned by digest in `container/image.lock` after its first pull. Environment capture includes image/digest, RPM inventory, kernel, glibc, compiler/CMake/binutils/Python/perf versions, CPU/microcode/governor/boost status, host load/steal time where available, cgroup configuration, NUMA, THP/HugeTLB, and container command. Measurement runs have networking disabled and perform neither downloads nor package installation.

Reproduction begins with source fetch/lock validation, container build, build manifest generation, environment validation, Tier 0 smoke, pilot, design freeze, then requested tiers. Exact commands will be added to the README once the scripts exist.

## 12. Resource estimate and threats to validity

Pilot duration is measured rather than guessed. Planning estimate: a Tier 1 cell takes roughly 15 × (10--30 s measured time plus setup), multiplied by its paired v2/v3 order; Tier 2 can be several times larger. The runner calculates the final wall-clock estimate from the frozen matrix and persists it before execution. Memory caps are selected after smoke/pilot and must exceed the largest touched working set with headroom.

Threats include host scheduling/noise, thermal/frequency variation, kernel and container coupling, imperfect policy equivalence across major versions, queue overhead in remote-free tests, and benchmark behavior differing from production programs. CPU pinning, paired randomization, fixed inputs, fresh processes, queue-only controls, environment capture, and explicit unavailable/invalid states mitigate but do not eliminate these threats.

## Pre-freeze pilot notes

On 2026-07-25, the first frozen-submatrix attempt used 1,000,000,000 operations
for fixed-small, one-worker `local_churn`. Two different free-order variants
lasted 25.0 s and 35.1 s, exceeding the target upper bound for one variant.
The revised matrix uses 500,000,000 operations and distinct `-r2` block IDs;
the earlier `-r1` records are pilot observations only. A pinned 1:1
`remote_free` pilot on CPUs 0 and 2 lasted about 2.0 s at 25,000,000 operations,
so its revision-2 count is 125,000,000. These pilot observations are not
performance-report results and must be reconfirmed by the frozen runner before
inclusion in analysis.

## Amendments

2026-07-25: revision-3 execution blocks add an explicit
`touch_mode=first-and-last` to the frozen command line. Revision-2 records
remain immutable pilot/reproducibility evidence, but are not pooled with
revision-3 results because the earlier command line relied on the benchmark
default rather than recording the condition explicitly.

2026-07-25: revision-3 explicitly recorded `first-and-last`, but its paired
fixed-small allocate/free sample took approximately 33--35 seconds per
allocator under the current container load. To keep each paired block below
the execution transport limit while retaining the minimum duration, revision-4
uses 200,000,000 operations and new `-r4` block IDs. Revision-3 remains pilot
evidence and is excluded from the final core comparison.

2026-07-25: revision-5 replaces the 1:1-only remote queue with a bounded MPMC
queue and records queue wait/backpressure diagnostics. This is a harness change,
so all preceding revision results remain pilot evidence and are not pooled with
revision-5 core results.

2026-07-25: the r6 core matrix, r7 THP=madvise memory subset, r8 common
purge-delay matrix, and r9 THP=never subset were frozen as separate plans.
The r9 host transition is performed only by the approved privileged container
controller, which saves the active THP mode and restores it through an exit
trap. Tier 3 remains outside this frozen, resource-available execution scope.

2026-07-25: audit found that r6--r11 containers had not received the planned
Docker cpuset. Those records remain immutable audit evidence and are excluded
from final comparison. Revisions r12 (THP=madvise) and r13 (THP=never) repeat
the applicable matrix with Docker `--cpuset-cpus=0,2,4,6,8,10,12,14` and
`--cpuset-mems=0`. The runner records `/proc/self/status`'s
`Cpus_allowed_list` and rejects any frozen-plan mismatch. r13 retains the
save/apply/restore THP controller and verified restoration to `madvise`.

2026-07-25: r14 adds a separate SMT domain (16 logical CPUs / 16 workers).
r16 adds an oversubscription domain (16 workers round-robin pinned within the
eight physical-core CPUs). The initial r15 oversubscription plan is retained as
invalid because its pre-execution binary SHA check correctly rejected a stale
benchmark. r16 uses the rebuilt harness SHA and is analyzed separately from
the primary CPU-controlled matrix.

2026-07-25: r17 adds secondary, explicitly selected allocation APIs to the
harness: C++ `new/delete`, 64-byte `posix_memalign` allocation, and `realloc`
from half target size. It is built under a distinct benchmark SHA and reported
separately from the primary `malloc/free` results.

2026-07-25: cross-NUMA and HugeTLB experiments are explicitly skipped by user
decision. Cross-NUMA is also infeasible in the captured environment because it
has one NUMA node. The prepared HugeTLB scripts and r18 plan remain unexecuted
and are not used for conclusions.

2026-07-25: r19 is a separate, diagnostic-only matrix requested after prior
v3.1.5 observations of elevated system-call activity and unavailable large-page
behavior. It has three paired repetitions per version under host THP=madvise,
the fixed r12 physical-core cpuset, and two policy arms: upstream default and
each version's documented native large-OS-page request. It records `strace`
counts for mmap/munmap/madvise/brk and samples the timed child PID's
smaps_rollup/status while allocations are deliberately held. It is not pooled
with primary throughput results. Missing strace capability is recorded as
unavailable rather than represented as zero.

2026-07-25: r20 is a separate native-request-only performance matrix for the
long-lived fixed-worker use case. It runs 4 producer and 4 consumer workers in
one fixed physical-core cpuset, without strace, using fixed-small and
mixed-wide remote-free task buffers. Both versions use their documented native
large-OS-page request variable. It has 15 paired repetitions per workload and
records elapsed time, user/system CPU time, faults, and observed RSS. Because
the two native request variables are not assumed semantically identical, r20
is not pooled with normalized primary results.

2026-07-25: r21 validates the r20 mixed-wide RSS observation by retaining the
native large-OS-page request but setting `MIMALLOC_PURGE_DELAY=1000` for both
versions. It samples the timed child PID's RSS and AnonHugePages every 100 ms,
without strace, for 15 paired fixed-worker remote-free repetitions. It remains
separate because only purge delay is normalized; the native large-page request
variables are version specific.

2026-07-26: r22 adds a separate, frozen single-NUMA diagnostic for the
`tcpio -> policy -> origin tcpio -> record -> free` ownership pipeline while
host NUMA balancing is disabled. It separates isolated and service-like worker
topologies, allocator-only and service stage work, upstream defaults and a
normalized policy. Its 100 ms process-memory samples, queue-only controls,
paired pilot/final plans, suitability gates, and conclusions are never pooled
with r19--r21. The complete frozen amendment is
`docs/tcpio-r22-design.ko.md`.

2026-07-26: r22 amendment v2 permits a kernel with
`CONFIG_NUMA_BALANCING` compiled out to run without the absent
`/proc/sys/kernel/numa_balancing` control. Such runs record the control as
unavailable and must not be described as an explicit balancing-off or on/off
comparison. ASAN is also removed as an execution prerequisite because the
pinned image lacks its runtime; this is documented as unverified rather than
silently treated as passed. The original r22 v1 plans remain frozen and
separate.

2026-07-26: r22 amendment v3 responds to the v2 pilot's isolated record/return
queue saturation without relaxing the frozen 5% backpressure criterion.
Isolated topology changes from 3 tcpio + 4 policy + 1 record to
3 tcpio + 3 policy + 2 record while retaining eight pinned physical-core
workers. New `r22b-` blocks are never pooled with r22/r22a blocks.

2026-07-26: r22 amendment v4 treats bounded-queue backpressure as an observed
pipeline metric instead of an invalidity reason. This change applies only to
new `r22c-` blocks and does not reclassify earlier records. Exact-once
correctness, provenance, affinity, host-state, throttling/OOM/swap, and record
bank saturation checks remain validity requirements.

2026-07-26: r22 amendment v5 excludes every v2--v4 performance record after a
Docker process audit found two orphaned small-queue benchmark containers on
overlapping CPUs. Raw files remain immutable; exclusion provenance is stored
in `manifests/exclusions-tcpio-r22.json`. New `r22d-` blocks restart smoke and
pilot on a clean host, and calibration/analysis require the exact v5 design
revision. The host controller also terminates its child before restoring THP
on signals.

2026-07-26: r22 amendment v6 recalibrates only the service-like topology after
the v5 final-duration audit found measured runs below the frozen five-second
minimum. The new r22e blocks target 20 seconds using a version-independent
operation count derived from the combined v5 final median rate. Final analysis
selects isolated v5 and service-like v6 as non-overlapping topology cells; it
does not pool repetitions across revisions.

2026-08-14: r23 adds an isolated patch-release comparison between mimalloc
v3.4.3 (`152fbf2634aeafca3774df791b0a77683035f076`) and v3.4.5
(`acf2fdd329f9dc2a7ffe3f12a133fe7175e39378`). Existing v2.1.2/v3.4.3 raw
records, exclusions, hypotheses, and conclusions remain unchanged. The r23
comparison reuses the same Rocky Linux 8 image and benchmark executable and
holds cpuset, NUMA node, THP mode, workload seed, queue capacity, and operation
count equal within each paired block. It begins with correctness/smoke and
three pilot repetitions. Core operation counts are calibrated from the pilot
to target the existing 10--30 second measured duration, then frozen in a new
manifest before at least 15 paired repetitions. Until that calibration is
recorded, the generated core plan remains `Draft` and the runner must reject
it. r23 results are analyzed and reported separately as v3.4.5/v3.4.3 ratios;
they are never pooled with v3/v2 ratios. This amendment was recorded before
any r23 performance result was inspected.

2026-08-14: r23 amendment v2 excludes all initial r23 pilot performance
records after the pre-core Docker audit found five unrelated, unrestricted
containers able to run on the same logical CPUs. The immutable pilot records
remain usable only as correctness evidence. Their derived calibration and core
manifest are marked superseded and must not be executed or reported. A new
`r23a-` pilot must be run under a clean or externally isolated CPU domain;
only that new pilot may calibrate and freeze an r23a core plan. This amendment
was recorded before any core repetition was executed.

2026-08-14: r23a completed after the five overlapping service containers were
stopped for the measurement epoch. The clean pilot produced 30 valid records;
the combined-version duration rule retained four operation counts and changed
only local mixed-wide/8-thread from 400,000,000 to 1,047,000,000 operations.
The resulting frozen core plan completed 150/150 valid records (15 complete
pairs in each of five cells), with measured durations from 14.50 to 20.82
seconds. The stopped containers were restored after completeness validation.
The r23a results are reported only in `docs/v3.4.3-v3.4.5-report.md` and remain
separate from every earlier comparison epoch.

2026-08-22: r24 adds mimalloc v3.5.0
(`18b08671c9302247bfb682286e6bf3cc1773f801`) as a third comparison version.
The original frozen v2.1.2/v3.4.3 design and every existing raw record,
exclusion, hypothesis, and conclusion remain unchanged. r24 uses matched
three-version blocks: each block contains v2.1.2, v3.4.3, and v3.5.0 exactly
once in a seeded random order, under identical benchmark binary, CPU/NUMA,
THP, policy, seed, queue capacity, and operation count. Results report
v3.4.3/v2.1.2 and v3.5.0/v2.1.2 primary ratios plus the
v3.5.0/v3.4.3 upgrade ratio. r24 starts at correctness/smoke and three pilot
repetitions; operation counts and the core manifest remain draft until pilot
calibration is recorded, after which at least 15 complete matched blocks are
required. No r24 result may be pooled with earlier epochs. At amendment time,
v3.5.0 had not been fetched, built, or measured.

2026-08-23: r26 baseline v1 creates a new isolated execution namespace after
r25 completed the fixed three-version comparison. It retains the five r25
Core cells and operation counts, reduces Memory-return to the decision-relevant
0/1000/5000 ms points under upstream-default and purge-delay=1000, and retains
the two r25 latency companion cells. The complete contract is frozen in
`experiments/r26-baseline-v1/contract.md`. Historical r2--r25 manifests,
runners, raw records, exclusions, and conclusions remain unchanged and are
never pooled with r26. The new active runner accepts no arbitrary plan path,
writes only under `results/active/r26-baseline-v1/`, preflights the complete
environment before execution, persists immutable per-attempt records, and
defaults to one matched three-version block per invocation. No r26 result had
been measured when this amendment was recorded.

2026-08-23: r27 supersedes the unexecuted r26 active comparison set without
altering r26's frozen files. Per user direction, r27 compares v2.1.2, v3.5.0,
and the upstream `dev3` branch as resolved at approximately 05:25 UTC to commit
`622d421f647fc41a2dfe90bc45174770129d78b4`. Although `dev3` is a moving ref,
source fetch and all measurements use only that immutable SHA; later branch
movement requires another revision. The snapshot was built in the same pinned
Rocky Linux 8 image and Release profile, produced library SHA-256
`49a1be072b80b98fced4135ae5d835a5fe8576648ca2949a8b9a6a70acdba95d`,
reported `mi_version=30500`, and passed a 100,000-operation fixed-cpuset
correctness smoke before freeze. The r25-calibrated workload counts and r26
isolation/durability semantics are retained. r27 writes only under
`results/active/r27-dev3-snapshot-v1/` and is never pooled with r2--r26.

2026-08-23: r28 is a memory-return-only follow-up prompted before any r28
measurement by review of r25's absolute RSS values. r25 had reported
cross-version post-free parity, but all 450 valid arms also had exactly equal
`rss_after_free` and `rss_after_idle`, retaining essentially the complete
512 MiB working set through five seconds. r28 preserves all r27 Core records
and creates a new namespace rather than changing their interpretation or raw
data. It measures a baseline-adjusted RSS curve at 0/10/100/1000/5000 ms in
one process, followed by a same-size reallocation and fault measurement. Six
one-variable cells separate passive upstream defaults, passive normalized
purge delay 1000, passive immediate purge, periodic ordinary allocator
activity, periodic `mi_collect(false)`, and one forced `mi_collect(true)`.
Direct collect cells are diagnostic and remain separate from ordinary
`LD_PRELOAD` behavior. The complete frozen contract is
`experiments/r28-memory-return-v1/contract.md`; r28 executes no Core or
latency profile and is never pooled with r27 or historical epochs.
