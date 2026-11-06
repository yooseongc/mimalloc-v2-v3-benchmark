# Profiling diagnostic v1

2026-11-01. Namespace: profiling-diagnostic-v1. Design status: Draft before smoke/pilot.

Preserve all frozen experiments. Reuse the active concurrent observation executable and
its validation controller without editing either. Revalidate recorded binary/library hashes.
Compare v3.6.0 and v3.6.1, 1024/4096-byte objects, two producer/consumer pairs,
128 MiB outstanding limit, full writes and checksum validation, existing 512-object batches.
This is a diagnostic of the basic concurrent workload, not the separate 256 KiB handoff experiment.

Modes: OFF; 512 KiB sampling with exit-only snapshot; 4 MiB sampling with exit-only
snapshot; 512 KiB sampling with 1 GiB allocation-triggered snapshots (upstream defaults).
Use text heap profiles for dependency-free inspection. Text output costs cannot be equated
with the default protobuf writer. Profile files include setup and shutdown allocations.
Use non-retained workload, 0.1 second idle. Exit snapshot lies outside benchmark elapsed time;
record whole-process controller wall time as a separate, observation-inclusive diagnostic.

Smoke: 256 MiB payload, all version/size/mode combinations, full content verification.
Pilot: OFF, 1 GiB payload, both versions/sizes. Freeze identical object counts per size
targeting 2 seconds for the fastest pilot, rounded to 512 objects. Three randomized blocks,
seed 20261101. Exploratory medians/ranges only, no significance claims.
Secondary policy controls: v3.6.1 OFF, page_reclaim_on_free=1 OR stats_merge_threshold=512KiB,
one setting at a time, three repeats per size. No combined-factor attribution.

Keep existing loader, CPU affinity, checksum, pointer count, final live count, swap and
throttling checks. Each run has 180 second controller timeout; stop on invalid run and
preserve failures. ON runs must produce nonempty profiles with sampled allocations.
Freeze plan JSON with source/controller/runner hashes before measured runs.
Collect environment, tool availability, CPU/RSS, raw profiles and maps, plus profile hashes.
Probe perf without changing host permissions; report unavailable if unsupported.
No network, package installs, host setting changes or upstream modifications.
Expected duration: 5–15 minutes; sampling changes allocation layout and is not a neutral observer.

Questions: Does the OFF regression reproduce? How much does sampling perturb this workload?
Does the profile add information beyond known allocation sites/live counts? Do either policy
controls narrow the gap? Heap profiles do not locate CPU bottlenecks or measure purged pages.
