#!/usr/bin/env python3
"""Capture r29 build/source/environment provenance, using the Linux container."""
import datetime
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "experiments/r29-v353-v1"


def run(command):
    p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return {"command": command, "exit_code": p.returncode, "output": p.stdout}


def artifact(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    plan = json.loads((DEST / "plan.json").read_text())
    builds = []
    for arm in plan["allocators"]:
        version = arm["version"]
        source = ROOT / "extern" / ("mimalloc-" + version)
        build = ROOT / "build" / ("mimalloc-" + version) / "release"
        prefix = ROOT / "opt" / ("mimalloc-" + version) / "release"
        git = ["git", "-c", "safe.directory=" + str(source), "-C", str(source)]
        commit = run(git + ["rev-parse", "HEAD"])
        status = run(git + ["status", "--porcelain"])
        if commit["exit_code"] or commit["output"].strip() != arm["commit"] or status["exit_code"] or status["output"].strip():
            raise SystemExit("source provenance mismatch: " + version)
        files = [build / "CMakeCache.txt", build / "CMakeFiles/mimalloc.dir/flags.make",
                 build / "CMakeFiles/mimalloc.dir/link.txt"]
        builds.append(dict(arm, source_status=status, source_commit=commit,
                           git_describe=run(git + ["describe", "--tags", "--always"]),
                           configuration=[dict(artifact(f), contents=f.read_text()) for f in files],
                           installed_headers=[artifact(f) for f in sorted(prefix.glob("include/**/mimalloc*.h"))]))
    data = {"captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "container_image_digest": plan["container_image_digest"], "benchmark": plan["benchmark"],
            "builds": builds, "environment": {key: run(cmd) for key, cmd in {
                "kernel": ["uname", "-a"], "glibc": ["ldd", "--version"],
                "compiler": ["gcc", "--version"], "topology": ["lscpu", "-e"],
                "numa": ["numactl", "--show"], "perf_probe": ["perf", "stat", "-e", "cycles,instructions", "true"],
            }.items()}}
    (DEST / "artifacts.json").write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
