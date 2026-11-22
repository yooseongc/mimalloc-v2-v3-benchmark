# r27 dev3 snapshot v1 experiment report

Execution status: Smoke complete; measured benchmark not executed
Reason: The complete r27 smoke matrix produced 39/39 valid records, but no
measured repetition has been executed and no performance conclusion is drawn.

Compared builds:

- mimalloc v2.1.2: `43ce4bd7fd34bcc730c1c7471c99995597415488`
- mimalloc v3.5.0: `18b08671c9302247bfb682286e6bf3cc1773f801`
- dev3 snapshot: `622d421f647fc41a2dfe90bc45174770129d78b4`

The full smoke result is Core 15/15, Memory-return 18/18, and Latency 6/6 valid
allocator arms, comprising 13 complete three-build blocks. These short runs
are setup/correctness evidence only and are not performance results. After
measured execution, this report must include the actual
environment, complete matched counts, invalid attempts, throughput, latency,
CPU and RSS metrics, confidence intervals, exclusions, and reproduction
commands. The third allocator must be described as this snapshot, not as the
latest dev3 state at report-reading time.
