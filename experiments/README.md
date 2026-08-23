# Experiment boundary

`ACTIVE` contains the only experiment accepted by
`scripts/run_active_benchmark.py`. The active directory owns its frozen
contract and plan; its output is written under a matching
`results/active/<experiment-id>/` namespace.

Everything outside the active directory is historical material. Historical
plans and runners remain available for reproduction, but the active runner
cannot load them and never scans their result directories.
