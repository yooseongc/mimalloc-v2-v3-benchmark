# Experiment boundary

`ACTIVE` contains the only experiment accepted by
the dispatcher `scripts/container/run_active.sh` (r29 uses
`scripts/run_comparison_r29.py`). The active directory owns its
contract and plan; its output is written under a matching
`results/active/<experiment-id>/` namespace.

Everything outside the active directory is historical material. Historical
plans and runners remain available for reproduction, but the active runner
cannot load them and never scans their result directories.
