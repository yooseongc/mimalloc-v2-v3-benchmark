# r28 enhanced memory-return report

Execution status: Complete

## Executive summary

r28 completed 270/270 valid measured arms: six memory-return cells, three
allocator builds, and 15 complete matched repetitions per cell. There were no
invalid attempts, retries, cgroup throttling events, plan-hash mixtures, or
allocator provenance mismatches.

The principal result is absolute, not merely relative: under upstream defaults
all three builds retained 100% of the baseline-adjusted 512 MiB working set
through five seconds of passive idle. A 64 B malloc/touch/free pulse every
10 ms also produced 0% observed return. Setting `MIMALLOC_PURGE_DELAY=0`
returned 99.6--99.9% immediately, but made the next 512 MiB burst 6.6--14.2
times slower than each version's passive-default result and moved the purge
cost into `free()`.

Periodic `mi_collect(false)` exposed a major-version semantic difference. It
did not return observable RSS on v2.1.2, while v3.5.0 and the dev3 snapshot
returned about 99.6% sometime after the one-second checkpoint and by the
five-second checkpoint. `mi_collect(true)` returned 93.9% on v2.1.2 and about
99.6% on both v3 builds immediately. Within every cell, dev3 and v3.5.0 had no
conclusive difference in returned fraction or next-burst elapsed time.

## Frozen environment and artifacts

- mimalloc v2.1.2: `43ce4bd7fd34bcc730c1c7471c99995597415488`
- mimalloc v3.5.0: `18b08671c9302247bfb682286e6bf3cc1773f801`
- dev3 snapshot: `622d421f647fc41a2dfe90bc45174770129d78b4`
- Rocky Linux 8 image:
  `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`
- benchmark SHA-256:
  `cae35ae342d94552be35fec06de5f46a7a108496dbb59debc18f6c201aa6528b`
- cpuset `0,2,4,6,8,10,12,14`; NUMA memory node 0; THP `madvise`
- network disabled; fresh process per arm; matched seeded randomization
- contract: `experiments/r28-memory-return-v1/contract.md`

The 270 records contain one plan hash and three expected allocator commits.

## Measurement sequence

Each arm allocated 8,192 objects of 64 KiB, touched every 4 KiB page, recorded
RSS before and after freeing, and then sampled RSS at 0, 10, 100, 1000, and
5000 ms. It subsequently allocated and touched the same 512 MiB again to
measure reuse elapsed time and faults. Returned fraction subtracts each
process's baseline RSS from both the fully touched and observed RSS values.

The `working RSS` value below is a fully touched checkpoint immediately before
free, not a process-lifetime peak. The older misleading Core field named
`peak_rss_bytes` is not used.

## Five-second return result

| Cell | v2.1.2 returned | v3.5.0 returned | dev3 returned |
|---|---:|---:|---:|
| passive, upstream default | 0.00% | 0.00% | 0.00% |
| passive, purge delay 1000 | 0.00% | 0.00% | 0.00% |
| passive, purge delay 0 | 99.85% | 99.61% | 99.61% |
| allocator activity, upstream default | 0.00% | 0.00% | 0.00% |
| `mi_collect(false)`, upstream default | 0.00% | 99.61% | 99.61% |
| `mi_collect(true)`, upstream default | 93.94% | 99.61% | 99.51% |

For passive defaults, median RSS remained 516.25 MiB on v2.1.2 and 519.57
MiB on both v3 builds. With purge delay 0, five-second median RSS was 4.14 MiB
on v2.1.2 and 7.53 MiB on both v3 builds. Forced collection left 34.55 MiB on
v2.1.2, 7.38 MiB on v3.5.0, and 8.00 MiB on dev3.

Purge delay 0 had already reached these returned fractions at the post-free
zero-millisecond checkpoint. Forced collection reached its result in the one
explicit collect call before the zero-millisecond observation. Normal collect
showed 0% at 1000 ms and about 99.6% at 5000 ms on v3, so this design brackets
but does not locate the exact transition within that interval.

The purge-delay-0 v3.5.0/v2.1.2 returned-fraction difference was -0.244
percentage points (paired bootstrap 95% CI -0.366 to -0.244 points), which is
small relative to near-complete return. dev3/v3.5.0 was +0.021 points with a
CI spanning -0.268 to +0.316 points. For forced collect, v3.5.0 returned 5.67
points more than v2.1.2 (95% CI +5.57 to +5.69 points); dev3 and v3.5.0 again
overlapped.

## Return/reuse trade-off

| Cell | v2 next burst / faults | v3.5 next burst / faults | dev3 next burst / faults |
|---|---:|---:|---:|
| passive default | 22.30 ms / 7,822 | 50.68 ms / 1,739 | 46.95 ms / 1,739 |
| passive purge 1000 | 2.90 ms / 7 | 50.88 ms / 1,739 | 50.04 ms / 1,739 |
| passive purge 0 | 318.03 ms / 131,146 | 341.92 ms / 130,950 | 334.98 ms / 130,950 |
| allocator activity | 22.04 ms / 7,822 | 48.87 ms / 1,867 | 53.05 ms / 1,867 |
| normal collect | 2.96 ms / 7 | 81.12 ms / 1,661 | 85.23 ms / 1,661 |
| forced collect | 310.45 ms / 123,331 | 114.38 ms / 1,661 | 137.25 ms / 1,661 |

Against each version's passive-default matched repetitions, purge delay 0 made
the next burst 14.24x slower on v2.1.2 (95% CI 11.96--15.25), 6.63x on
v3.5.0 (6.15--6.92), and 7.03x on dev3 (6.81--7.42). It also raised free time
from below 0.4 ms to median 73.84 ms on v2.1.2, 33.18 ms on v3.5.0, and 32.28
ms on dev3. Immediate RSS return therefore has a clear free/reuse cost.

Normal collection made the v3.5.0 and dev3 next bursts 1.57x and 1.79x slower
than passive default respectively, while achieving near-complete five-second
return. Forced collection raised those ratios to 2.34x and 2.59x. On v2.1.2,
normal collection returned no RSS and made the next burst faster, whereas
forced collection took 61.19 ms itself, returned less RSS than v3, and made
the next burst 13.32x slower.

Identical RSS does not imply an identical reuse path. On v2.1.2, passive
default and passive purge-delay-1000 both retained 100%, yet the latter reduced
the next burst from 22.30 to 2.90 ms and minor faults from 7,822 to 7. This
result is why RSS, elapsed time, and faults must be interpreted together.

The direct dev3/v3.5.0 next-burst ratios had confidence intervals containing
1.0 in all six cells: passive default 0.946 (0.890--1.001), purge 1000 0.993
(0.894--1.036), purge 0 1.016 (0.928--1.056), allocator activity 1.062
(0.979--1.159), normal collect 1.133 (0.732--1.479), and forced collect 1.128
(0.789--1.271). r28 therefore does not establish a dev3 memory-return or
reuse regression/improvement relative to v3.5.0.

## Hypotheses

- H1 is supported: passive idle alone returned no observable RSS.
- H2 is rejected for the 64 B allocator pulse. Normal collect supports H2 for
  v3 by five seconds but not for v2.1.2.
- H3 is supported for immediate purge and forced collect: faster return traded
  against free/collect work and subsequent reuse cost.
- H4 is not supported: dev3 and v3.5.0 remained statistically compatible in
  the tested retention and reuse comparisons.

## Interpretation and limitations

For a service that becomes completely quiet after a burst, waiting five
seconds is not sufficient to reduce RSS under the tested defaults. Small
ongoing malloc/free traffic also did not trigger return. Applications needing
an RSS drop must choose an explicit policy/action, but purge delay 0 is the
most expensive tested choice for the next full burst. On v3, normal collection
is the tested compromise: delayed near-complete return with a smaller reuse
penalty than immediate purge or forced collection.

The direct collect cells use mimalloc API calls and are diagnostic; they are
not ordinary interposed `malloc/free` behavior. The workload is one
single-threaded fully freed burst, not fragmentation, remote free, thread exit,
or cgroup pressure. RSS is `/proc/self/status` `VmRSS`; r28 did not collect PSS
or AnonHugePages, and THP was fixed at `madvise`. The allocator-activity pulse
is deliberately small and does not represent production traffic. Absolute
allocation timing varied across blocks, so all absolute raw values are retained
and no single timing number should be treated as universal.

## Artifacts and reproduction

- Frozen plan: `experiments/r28-memory-return-v1/plan.json`
- Tracked summary: `results/summaries/summary-r28-memory-return.json`
- Immutable raw records: `results/active/r28-memory-return-v1/measured/raw/`
- Smoke records: `results/active/r28-memory-return-v1/smoke/raw/`

```bash
scripts/container/run_active.sh --stage measured --profile memory-return --execute --max-blocks 0
python3 scripts/analyze_memory_return_r28.py
```

## Conclusion

The earlier parity wording hid the main behavior: all tested versions retain
the complete 512 MiB during passive idle. r28 establishes which actions change
that result and quantifies their cost. v3.5.0 and the pinned dev3 snapshot are
effectively equivalent here; policy/action choice has a much larger effect
than the difference between those two builds.
