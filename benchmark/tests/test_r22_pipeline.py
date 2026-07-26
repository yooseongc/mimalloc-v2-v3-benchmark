import importlib.util
import json
import pathlib
import hashlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("r22_runner", ROOT / "scripts/run_tcpio_r22.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class R22RunnerTests(unittest.TestCase):
    def test_cpu_list_expansion_including_ranges(self):
        self.assertEqual(RUNNER.expand_cpu_list("0,2,4-6"), [0, 2, 4, 5, 6])

    def test_pairing_keeps_two_allocator_arms_adjacent(self):
        plan = {"randomization_seed": 3, "runs": [
            {"block_id": "a", "policy": "normalized", "repetitions": 2, "allocator_version": "v2"},
            {"block_id": "a", "policy": "normalized", "repetitions": 2, "allocator_version": "v3"},
        ]}
        entries = RUNNER.paired_entries(plan, "normalized")
        self.assertEqual(len(entries), 4)
        for offset in range(0, len(entries), 2):
            self.assertEqual({entry["allocator_version"] for entry in entries[offset:offset + 2]},
                             {"v2", "v3"})

    def test_generated_pilot_manifest_shape(self):
        path = ROOT / "manifests/execution-plan-tcpio-r22a-pilot.json"
        if not path.exists():
            self.skipTest("pilot manifest has not been generated")
        plan = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(plan["design_status"], "Frozen")
        self.assertEqual(plan["required_numa_balancing"],
                         "disabled-or-kernel-unsupported")
        self.assertEqual(sum(run["repetitions"] for run in plan["runs"]), 72)
        self.assertEqual({run["scenario"] for run in plan["runs"]},
                         {"tcp_policy_record", "tcp_policy_record_queue_only"})

    def test_host_state_refusal_reasons(self):
        state = {"numa_balancing": "1", "single_numa_node": False,
                 "thp_mode": "always", "expected_thp_mode": "never"}
        self.assertEqual(len(RUNNER.validate_host(state)), 3)
        unsupported = {"numa_balancing": None, "single_numa_node": True,
                       "thp_mode": "never", "expected_thp_mode": "never"}
        self.assertEqual(RUNNER.validate_host(
            unsupported, "disabled-or-kernel-unsupported"), [])

    def test_sha_and_cpuset_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            library = pathlib.Path(directory) / "lib.so"
            benchmark = pathlib.Path(directory) / "bench"
            library.write_bytes(b"library")
            benchmark.write_bytes(b"benchmark")
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            item = {"cpu_list": "0,2", "allocator_library_path": str(library),
                    "benchmark_path": str(benchmark),
                    "allocator_library_sha256": digest(library),
                    "benchmark_sha256": digest(benchmark)}
            RUNNER.validate_frozen_item(item, "0,2")
            item["benchmark_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "benchmark SHA-256"):
                RUNNER.validate_frozen_item(item, "0,2")
            with self.assertRaisesRegex(ValueError, "cpuset"):
                RUNNER.validate_frozen_item(item, "0-3")


if __name__ == "__main__":
    unittest.main()
