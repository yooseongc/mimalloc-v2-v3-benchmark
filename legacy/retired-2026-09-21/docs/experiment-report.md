# mimalloc v2.1.2 vs v3.4.3 experiment report

The separate v3.5.3 comparison is tracked in
[the r29 report](experiment-report-r29.md). It reruns v2.1.2/v3.5.0/v3.5.3
and does not reuse historical performance observations.

Execution status: Completed for the approved scope.  
Final-comparison scope: CPU-controlled r12 (THP=madvise) and r13 (THP=never).  
Unexecuted scope: HugeTLB reservation and cross-NUMA. Both are explicitly
out of scope by user decision; cross-NUMA is additionally unavailable on this
one-node host.

Separate diagnostic: r19 measured syscall totals and sampled THP state for
large allocations (12 valid records). It is intentionally excluded from these
primary throughput ratios; see `docs/diagnostic-r19-report.ko.md`.

Separate diagnostic: r20 measured 60 native-large-page-request fixed-worker
remote-free records (15 paired repetitions for each of two size profiles). Its
version-native request variables are not assumed policy-equivalent, so it is
also excluded from primary normalized-policy ratios; see
`docs/native-persistent-r20-report.ko.md`.

Separate diagnostic: r21 repeated the r20 mixed-wide fixed-worker workload
with `MIMALLOC_PURGE_DELAY=1000` for both versions and sampled RSS plus
AnonHugePages through execution (30 valid records). It is kept separate because
the large-page request variables remain version native; see
`docs/purge-matched-r21-report.ko.md`.

## Executive summary

The final-comparison data comprise 600 valid raw records: r12 has 480 records
across Tier 1, Tier 2, and common Tier 3 build/runtime controls; r13 has 120
THP=never records. Every reported block has 15 valid paired v2/v3 repetitions.
Containers were restricted to non-SMT logical CPUs `0,2,4,6,8,10,12,14` on
NUMA node 0. The runner records the kernel's `Cpus_allowed_list` and rejects a
plan/cpuset mismatch.

Results are workload- and host-specific. They do not establish a universal
allocator ranking. Large-allocation and large-page-request cells are especially
variable and must not be generalized from their median alone.

## Sources, builds, and environment

The sources are `microsoft/mimalloc` v2.1.2
(`43ce4bd7fd34bcc730c1c7471c99995597415488`) and v3.4.3
(`152fbf2634aeafca3774df791b0a77683035f076`). Both use a Rocky Linux 8
container, one benchmark executable selected by `LD_PRELOAD`, and no network
during timed execution. Build paths, CMake profiles, library hashes, image
digest, and environment capture are retained in `manifests/`.

The host exposes one NUMA node and 8 physical cores / 16 logical CPUs. It
therefore cannot support a meaningful cross-NUMA experiment. The final matrix
uses the eight physical-core siblings listed above; SMT is intentionally not
part of its primary results.

## Tier 1: core comparison (r12, THP=madvise)

| Workload | Median v3/v2 throughput | 95% CI of mean ratio | Note |
|---|---:|---:|---|
| fixed-small local, 8 threads | 1.032 | 1.024 .. 1.047 | v3 higher in this cell |
| mixed-wide local, 1 thread | 0.990 | 0.972 .. 1.001 | near parity |
| mixed-wide local, 8 threads | 0.998 | 0.973 .. 1.021 | near parity |
| fixed-small remote-free, 4:4 | 1.012 | 0.971 .. 1.089 | interval crosses parity |
| mixed-wide remote-free, 4:4 | 1.011 | 0.956 .. 1.079 | interval crosses parity |

## Tier 2: memory policy

### THP=madvise (r12)

| Scenario | Median v3/v2 throughput | 95% CI of mean ratio |
|---|---:|---:|
| burst/purge | 0.999 | 0.998 .. 1.001 |
| large allocation | 2.334 | 2.334 .. 4.000 |
| lifetime mix | 1.009 | 0.987 .. 1.018 |
| thread churn | 1.309 | 1.301 .. 1.331 |

The v3 large-allocation CV is about 51%; the large ratio is therefore a
high-variance observation rather than a stable recommendation.

### THP=never (r13)

The privileged controller saved `madvise`, applied `never`, completed 120
records, and restored `madvise`. Restoration was independently verified after
container exit.

| Scenario | Median v3/v2 throughput | 95% CI of mean ratio |
|---|---:|---:|
| burst/purge | 0.995 | 0.995 .. 0.997 |
| large allocation | 1.002 | 0.966 .. 1.017 |
| lifetime mix | 1.012 | 1.001 .. 1.026 |
| thread churn | 1.315 | 1.283 .. 1.398 |

### Common purge policy (r12, THP=madvise)

| `MIMALLOC_PURGE_DELAY` | Median v3/v2 throughput | 95% CI of mean ratio |
|---:|---:|---:|
| -1 | 1.002 | 1.001 .. 1.003 |
| 0 | 0.996 | 0.988 .. 1.001 |
| 1000 | 0.998 | 0.996 .. 0.999 |

Delay 0 lowered absolute throughput for both versions; it is a policy effect,
not evidence of a version advantage.

## Tier 3: supported common extensions (r12)

| Control | Median v3/v2 throughput | 95% CI of mean ratio | Interpretation |
|---|---:|---:|---|
| secure build, fixed local 1 thread | 1.090 | 1.073 .. 1.104 | profile-specific |
| local-dynamic-TLS, fixed local 8 threads | 1.012 | 1.002 .. 1.045 | profile-specific |
| large-OS-page request | 0.890 | 0.574 .. 1.407 | actual page grant unverified; high variance |
| `MIMALLOC_USE_NUMA_NODES=1` | 2.295 | 2.014 .. 3.045 | one-node host; fault-sensitive workload |

The large-page request uses each version's documented variable name and is not
presented as proof of actual large-page allocation, because timed-process
`AnonHugePages` was not captured. Secure/TLS rows compare versions within the
same build profile; they are not measurements of profile overhead.

## Tier 3: CPU topology extensions

| CPU domain | Median v3/v2 throughput | 95% CI of mean ratio | Interpretation |
|---|---:|---:|---|
| SMT: 16 logical CPUs, 16 workers (r14) | 1.041 | 0.984 .. 1.092 | interval includes parity |
| Oversubscription: 8 physical CPUs, 16 workers (r16) | 1.050 | 1.035 .. 1.086 | explicit round-robin pinning |

The oversubscription harness revision pins workers round-robin inside the
eight-CPU cpuset; it never allows a worker to escape the fixed CPU domain. The
earlier r15 records failed its pre-execution benchmark SHA validation and are
retained only as invalid audit records.

## Tier 3: secondary allocation APIs (r17)

These blocks use a separate harness revision that adds explicit API selection;
they are not pooled with the primary `malloc/free` results. Each has 15 valid
pairs on the physical-core cpuset.

| API | Median v3/v2 throughput | 95% CI of mean ratio |
|---|---:|---:|
| C++ `new/delete` | 1.041 | 1.015 .. 1.045 |
| 64-byte aligned allocation | 1.030 | 0.981 .. 1.034 |
| `realloc` (half-size then target-size) | 1.040 | 1.032 .. 1.046 |

## Exclusions and limitations

All pre-r12 records remain immutable audit evidence but are excluded from final
ratios because their containers were not launched with the frozen cpuset.
Cross-NUMA is structurally unavailable (one NUMA node) and is explicitly
skipped by user decision. HugeTLB reservation is also explicitly skipped by
user decision; the host currently reserves zero 1GiB huge pages and the common
mimalloc setting would require a host-wide reservation change.
`manifests/execution-plan-tier3-hugetlb-r18.json` and the paired
`scripts/host/set_hugetlb_1g.sh` / `restore_hugetlb_1g.sh` scripts are prepared
but intentionally unexecuted.
Perf counters unavailable to the container are recorded as
unavailable, not as zero.

## Reproduction

Use `manifests/execution-plan-cpuset-r12.json` with Docker cpuset
`0,2,4,6,8,10,12,14` and memory node `0`. Use
`manifests/execution-plan-tier2-thp-never-cpuset-r13.json` only through
`scripts/container/run_thp_never.sh` in the approved privileged controller.
Then run:

```text
python scripts/analyze_results.py --plan manifests/execution-plan-cpuset-r12.json
python scripts/generate_report.py
python scripts/generate_ratio_plot.py
```

Raw records are in `results/raw/`; logs are in `results/logs/`; final scoped
tables are `results/summaries/summary-r12.json` and `summary-r13.json`; the SVG
is `results/plots/throughput-ratios.svg`.
