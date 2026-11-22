import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "active_runner", ROOT / "scripts" / "run_memory_return_r28.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
BASE = RUNNER.BASE


class ActiveBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This suite tests the frozen r28 memory contract, regardless of which
        # experiment is currently selected for new measurements.
        cls.plan_path = ROOT / "experiments/r28-memory-return-v1/plan.json"
        cls.plan = json.loads(cls.plan_path.read_text(encoding="utf-8"))
        RUNNER.validate_plan(cls.plan_path, cls.plan)

    def test_active_plan_is_memory_only_and_has_fixed_size(self):
        measured = BASE.expand_entries(self.plan, {"memory-return"}, "measured")
        smoke = BASE.expand_entries(self.plan, {"memory-return"}, "smoke")
        counts = {}
        for item in measured:
            counts[item["profile"]] = counts.get(item["profile"], 0) + 1
        self.assertEqual(counts, {"memory-return": 270})
        self.assertEqual(len(smoke), 18)
        self.assertEqual({item["expected_operation_count"] for item in measured}, {8192})
        self.assertEqual({item["idle_ms"] for item in measured}, {5000})

    def test_default_schedule_preserves_one_matched_block(self):
        entries = BASE.expand_entries(self.plan, {"memory-return"}, "measured")
        first = BASE.scheduled_blocks(entries, set(), self.plan["randomization_seed"], 1)
        second = BASE.scheduled_blocks(entries, set(), self.plan["randomization_seed"], 1)
        self.assertEqual([[BASE.run_identity(x) for x in b] for b in first],
                         [[BASE.run_identity(x) for x in b] for b in second])
        self.assertEqual(len(first), 1)
        self.assertEqual({item["version"] for item in first[0]},
                         set(self.plan["comparison_versions"]))

    def test_partial_block_resumes_only_missing_allocator_arms(self):
        entries = BASE.expand_entries(self.plan, {"memory-return"}, "measured")
        selected = BASE.scheduled_blocks(entries, set(), self.plan["randomization_seed"], 1)[0]
        completed = {BASE.run_identity(selected[0])}
        resumed = BASE.scheduled_blocks(entries, completed, self.plan["randomization_seed"], 1)
        self.assertEqual(len(resumed), 1)
        self.assertEqual({item["block_id"] for item in resumed[0]},
                         {selected[0]["block_id"]})
        self.assertEqual({item["repetition"] for item in resumed[0]},
                         {selected[0]["repetition"]})
        self.assertEqual(len(resumed[0]), 2)

    def test_command_records_enhanced_memory_controls(self):
        entry = BASE.expand_entries(self.plan, {"memory-return"}, "measured")[0]
        command = BASE.command_for(entry)
        self.assertEqual(command[command.index("--seed") + 1],
                         str(self.plan["randomization_seed"]))
        self.assertEqual(command[command.index("--memory-return-mode") + 1], "passive")
        self.assertEqual(command[command.index("--memory-action-interval-ms") + 1], "10")
        self.assertEqual(command[command.index("--reallocate-after-observe") + 1], "1")

    def test_resume_state_is_scoped_to_supplied_raw_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = pathlib.Path(directory) / "active"
            legacy = pathlib.Path(directory) / "legacy"
            raw.mkdir()
            legacy.mkdir()
            record = {"block_id": "b", "repetition": 1,
                      "allocator_version": "v2.1.2", "attempt": 1, "valid": True}
            (legacy / "legacy.json").write_text(json.dumps(record), encoding="utf-8")
            valid, attempts = BASE.prior_state(raw)
            self.assertEqual(valid, set())
            self.assertEqual(dict(attempts), {})

    def test_memory_output_uses_explicit_allocation_count(self):
        item = BASE.expand_entries(self.plan, {"memory-return"}, "measured")[0]
        output = {"valid": True, "allocator_version": item["mi_version"],
                  "allocator_library_path": item["library_path"],
                  "elapsed_ns": 1, "operation_count": 8192, "checksum": 1,
                  "memory_return_mode": "passive", "memory_action_count": 0,
                  "memory_action_elapsed_ns": 0,
                  "rss_before_burst_bytes": 1, "working_set_rss_bytes": 10,
                  "rss_after_free_bytes": 10, "rss_after_idle_bytes": 10,
                  "rss_observations": [{"offset_ms": offset, "rss_bytes": 10}
                                       for offset in (0, 10, 100, 1000, 5000)],
                  "allocation_elapsed_ns": 1, "free_elapsed_ns": 1,
                  "reallocation_count": 8192, "reallocation_elapsed_ns": 1,
                  "reallocation_minor_faults": 0}
        self.assertIsNone(RUNNER.validate_output(item, output, 0, 0))
        output["operation_count"] = 1
        self.assertIn("operation count", RUNNER.validate_output(item, output, 0, 0))

    def test_memory_output_rejects_missing_checkpoint(self):
        item = BASE.expand_entries(self.plan, {"memory-return"}, "measured")[0]
        output = {"valid": True, "allocator_version": item["mi_version"],
                  "allocator_library_path": item["library_path"],
                  "elapsed_ns": 1, "operation_count": 8192, "checksum": 1,
                  "memory_return_mode": "passive", "memory_action_count": 0,
                  "memory_action_elapsed_ns": 0,
                  "rss_before_burst_bytes": 1, "working_set_rss_bytes": 10,
                  "rss_after_free_bytes": 10, "rss_after_idle_bytes": 10,
                  "rss_observations": [{"offset_ms": 0, "rss_bytes": 10}],
                  "allocation_elapsed_ns": 1, "free_elapsed_ns": 1,
                  "reallocation_count": 8192, "reallocation_elapsed_ns": 1,
                  "reallocation_minor_faults": 0}
        self.assertIn("schedule", RUNNER.validate_output(item, output, 0, 0))


if __name__ == "__main__":
    unittest.main()
