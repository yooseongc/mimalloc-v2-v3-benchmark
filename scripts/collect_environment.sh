#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${1:-$root/manifests/environment.json}"
python3 - "$out" <<'PY'
import json, platform, subprocess, sys
def run(command):
    try:
        return subprocess.check_output(command, universal_newlines=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"unavailable": str(exc)}
commands = {
    "gcc": ["gcc", "--version"], "gxx": ["g++", "--version"],
    "cmake": ["cmake", "--version"], "python3": ["python3", "--version"],
    "perf": ["perf", "--version"], "lscpu": ["lscpu"],
    "numactl_hardware": ["numactl", "--hardware"], "rpm_qa": ["rpm", "-qa"]
}
paths = ["/proc/meminfo", "/proc/sys/kernel/numa_balancing",
         "/sys/kernel/mm/transparent_hugepage/enabled",
         "/sys/kernel/mm/transparent_hugepage/defrag"]
proc = {}
for path in paths:
    try:
        with open(path) as handle: proc[path] = handle.read()
    except OSError as exc: proc[path] = {"unavailable": str(exc)}
with open(sys.argv[1], "w") as handle:
    json.dump({"schema_version": 1, "capture_status": "captured",
               "kernel": platform.release(),
               "commands": {key: run(value) for key, value in commands.items()},
               "proc": proc}, handle, indent=2, sort_keys=True)
PY
