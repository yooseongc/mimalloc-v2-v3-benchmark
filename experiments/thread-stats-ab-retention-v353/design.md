# v3.5.3 page_full_retain attribution control

Design status: Frozen before execution (2026-09-22)

Purpose: test the source-derived explanation for A=40 / B=960 free-equivalent
objects in the existing 1,000-object, 4 KiB A-alloc/B-free diagnostic.
This is a correctness/causality diagnostic, not a performance comparison.

Keep the upstream library and original A/B probe unchanged. Build a derived probe
whose only addition logs mi_option_get(mi_option_page_full_retain). Keep both
threads alive, explicit API calls, collect_merges_stats=0, purge_delay=1000.
Change only MIMALLOC_PAGE_FULL_RETAIN across -1, 0, 1, 2, 4. Run each with
64 B and 4 KiB, one fresh process per cell; the earlier default has two repeats.
Expected execution: under one minute, less than 10 MiB payload per process.

Predictions made before execution:

| retain | 4 KiB A / B free-equivalent objects | 64 B A / B |
|---:|---:|---:|
| -1 (disable abandonment) | 1000 / 0 | 1000 / 0 |
| 0 | 10 / 990 | 1000 / 0 |
| 1 | 25 / 975 | 1000 / 0 |
| 2 (default) | 40 / 960 | 1000 / 0 |
| 4 | 70 / 930 | 1000 / 0 |

Reason: 15 objects per 4 KiB small-page allocation area; 66 full pages plus
10 objects on the final page. Retain r full pages on A, abandon the rest.
64 B x 1000 fits one small page and does not trigger this abandonment.

Validate loaded version/SHA, actual options, payload contents, A free calls=0,
B allocation calls=0, A allocations=B frees=1000, exact predicted attribution
after both collect, total allocated bytes/count and current=0, final merged
parent freed bytes. Preserve stdout/stderr even on assertion failure. Do not
exclude a mismatch or reinterpret it as passing; investigate and document it.
OS RSS and purge timing are not outcome measures for this diagnostic.
