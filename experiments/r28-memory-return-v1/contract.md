# r28 enhanced memory-return measurement contract

Design status: Frozen
Design revision: r28-memory-return-v1
Frozen at: 2026-08-23T16:49:35+09:00

## Purpose

r28 is a memory-return-only follow-up to r27. It does not alter or pool the
r27 Core records. The follow-up exists because r25 observed that every one of
450 burst arms had identical RSS immediately after `free()` and after the idle
period, but the report reduced that absolute retention result to relative
cross-version parity. r28 distinguishes passive idle, ordinary allocator
activity, normal collection, forced collection, and purge policy while also
measuring the cost of reusing the working set.

The compared builds remain exactly:

- mimalloc v2.1.2, commit `43ce4bd7fd34bcc730c1c7471c99995597415488`
- mimalloc v3.5.0, commit `18b08671c9302247bfb682286e6bf3cc1773f801`
- mimalloc dev3 snapshot, commit
  `622d421f647fc41a2dfe90bc45174770129d78b4`

The dev3 name denotes this immutable snapshot, not the moving branch state.

## Hypotheses

- H1: sleeping after the final `free()` does not by itself cause material RSS
  return in the tested allocator/process state.
- H2: continued allocator activity or `mi_collect(false)` permits expired
  delayed purges to run and reduces baseline-adjusted retained RSS.
- H3: `MIMALLOC_PURGE_DELAY=0` and `mi_collect(true)` return RSS sooner but
  increase the next burst's allocation time and minor faults.
- H4: dev3 changes one or more of the retention/reuse trade-offs relative to
  v3.5.0 under otherwise identical conditions.

## Frozen environment and artifacts

- Rocky Linux 8 image digest:
  `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`
- cpuset `0,2,4,6,8,10,12,14`; memory node 0; THP `madvise`
- network disabled; fresh process; no inherited `MIMALLOC_*` variables
- one fixed benchmark executable and one fixed runner for all three builds
- deterministic matched-triplet randomization seed `20260828`
- 15 complete valid repetitions per cell

Exact executable, runner, dependency, and library SHA-256 values are frozen in
`plan.json`. The runner rejects any mismatch before starting a benchmark arm.

## Workload and observation timeline

Every arm performs the following sequence in one process:

1. Read baseline `VmRSS` and cumulative fault counters.
2. Allocate 8,192 objects of 64 KiB (512 MiB total) with `malloc`.
3. Touch every 4 KiB page and record RSS immediately before freeing.
4. Free all 8,192 objects and record RSS immediately after `free()`.
5. Apply the cell-specific observation action and record RSS at offsets
   0, 10, 100, 1000, and 5000 ms from the observation start.
6. Allocate and touch the same 512 MiB working set again, recording elapsed
   time, minor/major faults, and resident RSS, then free it.

The fully touched RSS immediately before free is an observed working-set
checkpoint, not a claim of process-lifetime peak RSS. No field from the older
Core harness named `peak_rss_bytes` is used in r28 analysis.

## Cells

Each cell changes one item from passive upstream defaults:

| Cell | Runtime policy | Observation action |
|---|---|---|
| `passive-default` | upstream default | sleep only |
| `passive-purge1000` | `MIMALLOC_PURGE_DELAY=1000` | sleep only |
| `passive-purge0` | `MIMALLOC_PURGE_DELAY=0` | sleep only |
| `activity-default` | upstream default | allocate, touch, and free 64 B every 10 ms |
| `collect-normal-default` | upstream default | call `mi_collect(false)` every 10 ms |
| `collect-force-default` | upstream default | call `mi_collect(true)` once immediately after the post-free reading |

The collect cells are direct-API diagnostics. They are reported separately
from normal `LD_PRELOAD + malloc/free` behavior and are not described as an
upstream-default application result.

## Metrics and interpretation

For checkpoint `t`, analysis computes:

```text
retained_fraction(t) = (RSS(t) - baseline_RSS)
                       / (working_set_RSS - baseline_RSS)
returned_fraction(t) = 1 - retained_fraction(t)
```

Unclamped values are retained so measurement noise is visible. The report
includes absolute RSS, retained/returned fractions at every checkpoint,
allocation/free/action CPU time, next-burst elapsed time, and next-burst page
faults. A median returned fraction of at least 10% by 5000 ms is considered a
material return signal; at least 90% is considered near-complete return. These
thresholds classify effect size and do not replace confidence intervals.

The primary comparisons are matched v3.5.0/v2.1.2,
dev3-snapshot/v2.1.2, and dev3-snapshot/v3.5.0 within each cell. Mode effects
are also reported within each version relative to `passive-default`. Results
use all valid complete triplets, paired bootstrap 95% confidence intervals,
and no retrospective outlier deletion.

## Validity and durability

- Smoke is correctness evidence only and precedes measured execution.
- Every arm must report the exact allocator path/version, 8,192 primary and
  8,192 reallocation objects, the five frozen RSS offsets, expected action
  count, nonzero checksum, and zero outstanding objects.
- Timeout, crash, malformed output, artifact/provenance mismatch, missing
  checkpoint, operation mismatch, or cgroup throttling makes an immutable
  invalid attempt.
- Raw records are written only under
  `results/active/r28-memory-return-v1/`; r27 and historical raw data are never
  scanned or rewritten.

## Resource estimate and limitation

Six cells times three builds times 15 repetitions produce 270 measured arms.
Each observes five seconds and performs two 512 MiB bursts, for an expected
wall time of roughly 30--45 minutes plus smoke and analysis.

The workload tests one large, single-threaded, fully freed burst. It does not
represent partial fragmentation, remote frees, thread exit, cgroup pressure,
swap, or a continuously serving application. The allocator-activity pulse is
a controlled trigger probe, not a production traffic model.

## Amendments

Any change to the source commits, binary, runner, workload size, timeline,
action cadence, policy, validity rules, or analysis definitions requires a new
revision and result namespace.
