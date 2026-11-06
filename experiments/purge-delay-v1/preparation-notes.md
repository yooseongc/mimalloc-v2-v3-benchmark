# Preparation record

Before freezing plan.json or running any observation process, the first generated
common-binary build failed with GCC's `-Werror=misleading-indentation`: an abort guard
and return were on the same line. Explicit braces and a newline fixed the warning.
Preparation then passed. No measured result was discarded or replaced.

The four header probes all resolved the option IDs to 15 (purge_delay),
24 (arena_purge_mult), and 5 (purge_decommits). Runtime getters independently
verified the default and explicitly requested values in every observation process.
