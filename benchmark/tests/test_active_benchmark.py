import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "active_runner", ROOT / "scripts" / "run_active_benchmark.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ActiveBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan_path, cls.plan = RUNNER.active_plan()
        RUNNER.validate_plan(cls.plan_path, cls.plan)

    def test_active_plan_has_fixed_profile_sizes(self):
        measured = RUNNER.expand_entries(
            self.plan, {"core", "memory-return", "latency"}, "measured")
        smoke = RUNNER.expand_entries(
            self.plan, {"core", "memory-return", "latency"}, "smoke")
        counts = {}
        for item in measured:
            counts[item["profile"]] = counts.get(item["profile"], 0) + 1
        self.assertEqual(counts, {"core": 225, "memory-return": 270, "latency": 90})
        self.assertEqual(len(smoke), 39)

    def test_default_schedule_preserves_one_matched_block(self):
        entries = RUNNER.expand_entries(self.plan, {"core"}, "measured")
        first = RUNNER.scheduled_blocks(entries, set(), self.plan["randomization_seed"], 1)
        second = RUNNER.scheduled_blocks(entries, set(), self.plan["randomization_seed"], 1)
        self.assertEqual([[RUNNER.run_identity(x) for x in b] for b in first],
                         [[RUNNER.run_identity(x) for x in b] for b in second])
        self.assertEqual(len(first), 1)
        self.assertEqual({item["version"] for item in first[0]},
                         set(self.plan["comparison_versions"]))

    def test_partial_block_resumes_only_missing_allocator_arms(self):
        entries = RUNNER.expand_entries(self.plan, {"core"}, "measured")
        selected = RUNNER.scheduled_blocks(entries, set(), self.plan["randomization_seed"], 1)[0]
        completed = {RUNNER.run_identity(selected[0])}
        resumed = RUNNER.scheduled_blocks(entries, completed, self.plan["randomization_seed"], 1)
        self.assertEqual(len(resumed), 1)
        self.assertEqual({item["block_id"] for item in resumed[0]},
                         {selected[0]["block_id"]})
        self.assertEqual({item["repetition"] for item in resumed[0]},
                         {selected[0]["repetition"]})
        self.assertEqual(len(resumed[0]), 2)

    def test_command_records_seed_and_warmup(self):
        entry = RUNNER.expand_entries(self.plan, {"latency"}, "measured")[0]
        command = RUNNER.command_for(entry)
        self.assertEqual(command[command.index("--seed") + 1],
                         str(self.plan["randomization_seed"]))
        self.assertEqual(command[command.index("--warmup-count") + 1], "691133")
        self.assertEqual(command[command.index("--latency-sample-rate") + 1], "1024")

    def test_resume_state_is_scoped_to_supplied_raw_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = pathlib.Path(directory) / "active"
            legacy = pathlib.Path(directory) / "legacy"
            raw.mkdir()
            legacy.mkdir()
            record = {"block_id": "b", "repetition": 1,
                      "allocator_version": "v2.1.2", "attempt": 1, "valid": True}
            (legacy / "legacy.json").write_text(json.dumps(record), encoding="utf-8")
            valid, attempts = RUNNER.prior_state(raw)
            self.assertEqual(valid, set())
            self.assertEqual(dict(attempts), {})

    def test_memory_output_uses_explicit_allocation_count(self):
        item = RUNNER.expand_entries(self.plan, {"memory-return"}, "measured")[0]
        output = {"valid": True, "allocator_version": item["mi_version"],
                  "allocator_library_path": item["library_path"],
                  "elapsed_ns": 1, "operation_count": 8192, "checksum": 1}
        self.assertIsNone(RUNNER.validate_output(item, output, 0, 0))
        output["operation_count"] = 1
        self.assertIn("operation count", RUNNER.validate_output(item, output, 0, 0))


if __name__ == "__main__":
    unittest.main()
