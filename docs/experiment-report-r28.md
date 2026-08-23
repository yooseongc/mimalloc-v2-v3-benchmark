# r28 enhanced memory-return report

Execution status: Not executed
Reason: The r28 memory-return-only contract and harness are frozen, but the
correctness smoke and measured repetitions have not yet been executed.

Compared builds:

- mimalloc v2.1.2: `43ce4bd7fd34bcc730c1c7471c99995597415488`
- mimalloc v3.5.0: `18b08671c9302247bfb682286e6bf3cc1773f801`
- dev3 snapshot: `622d421f647fc41a2dfe90bc45174770129d78b4`

The report will distinguish absolute passive retention from cross-version
parity. It will present baseline-adjusted returned fractions at 0, 10, 100,
1000, and 5000 ms; compare passive, allocator-activity, normal collect, forced
collect, and purge-policy cells; and report the next-burst elapsed time and
fault cost. No smoke value will be presented as a measured result.
