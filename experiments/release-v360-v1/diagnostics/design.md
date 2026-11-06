# v3.6.0 native counters and layout diagnostic

Frozen before execution, 2026-10-24. Run after timed measurements finish.
The v3.6.0 native allocated/malloc_count/free_count/freed fields are distinct
from the deprecated malloc_normal fields. Read both the native free counters
and the derived allocated.total-current difference, using the unchanged A/B
workload. Disable both automatic stats merges. Expect native and derived freed
bytes to agree; sum of native free_count must be 1,000. Do not impose a predicted
per-thread split as the correctness criterion; report it as the observation.

Also repeat the official heap visitor probe for 256 objects of 4 KiB on the
newly built v3.6.0 library. Expect 15 blocks per small-page area based on the
alignment/meta code; verify version and used_total=256 before interpreting.
No performance claims. Preserve stdout/stderr and artifact hashes.
