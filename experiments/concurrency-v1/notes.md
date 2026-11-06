# Execution and interpretation notes

The frozen design and runner were not edited after primary measurement began.
These notes clarify limitations; they do not change hypotheses, work counts, order,
or result exclusion rules.

- Initial smoke input used a 1 MiB ring. For 4 KiB objects and two pairs,
  two 256-object batches require at least 2 MiB. The program rejected the input.
  The failed record is retained at results/concurrency-v1/smoke/009.json.
  The complete corrected 2 MiB smoke suite is smoke-v2 (24 valid runs).
- Live requested bytes are inferred from two monotonically published counters
  per pair. A partially processed batch is not published. Reads of producer and
  consumer counters are not one atomic snapshot. The usual quantization is a
  batch per worker, but scheduling between reads means there is no strict fixed
  upper bound on snapshot skew. Do not use this estimate for precise instantaneous
  peaks. The ring enforces the requested cap independently; exact initial and final
  counts are checked.
- The retained control removes malloc/free and pointer replacement during the
  timed window, while also fixing the reused address set. It cannot identify the
  isolated instruction cost of malloc/free. Compare it as a whole alternate flow,
  without subtracting times.
- Busy wait counters report loop iterations, not time. CPU measurements include
  that work. Per-worker CPU costs and live occupancy can locate a broad imbalance
  but cannot attribute a regression to one allocator commit or function.
- Manual concurrency review: slot release/acquire publishes pointers and data;
  no producer rewrites a slot before the consumer releases it. Final non-atomic
  counters are read only after the done release/acquire sequence. The ready
  sequence completes prefilling before go. Main reads progress only at batch
  boundaries; workers do not read clocks or perform global atomic increments per
  object. The emitted checksum and full-payload smoke keep payload use observable.
