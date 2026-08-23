# Historical experiment archive boundary

The repository-root `config/`, `manifests/`, historical scripts, reports, and
`results/raw/` records belong to development epochs r2--r25. They are retained
in their original paths so published reproduction links and immutable raw-data
provenance do not break.

They are logically read-only for current work:

- do not add their records to `results/active/`;
- do not pass their manifests to the active runner (the runner has no such
  option);
- do not pool their summaries with r26;
- use the epoch-specific runner only when explicitly reproducing that epoch.

The current experiment is selected exclusively by `experiments/ACTIVE`.
