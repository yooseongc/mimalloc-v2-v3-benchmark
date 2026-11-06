import importlib.util
import json
import pathlib
import unittest
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("r29", ROOT / "scripts/run_comparison_r29.py")
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "experiments/r29-v353-v1/plan.json"
        self.plan = json.loads(self.path.read_text())

    def test_draft_cannot_execute_measured(self):
        self.plan["design_status"] = "Draft"
        with self.assertRaisesRegex(ValueError, "frozen design"):
            RUN.validate_plan(self.path, self.plan, "measured")

    def test_pilot_has_three_repetitions_for_every_arm(self):
        entries = RUN.entries_for(self.plan, {"core", "latency"}, "pilot")
        self.assertEqual(len(entries), 63)
        self.assertEqual({i["repetition"] for i in entries}, {1, 2, 3})
        self.assertEqual({i["version"] for i in entries}, {"v2.1.2", "v3.5.0", "v3.5.3"})

    def test_wrong_library_and_short_measurements_rejected(self):
        item = RUN.entries_for(self.plan, {"core"}, "measured")[0]
        output = dict(valid=True, allocator_version=item["mi_version"],
                      allocator_library_path=item["library_path"], elapsed_ns=4_000_000_000,
                      operation_count=item["operation_count"], checksum=1)
        self.assertIn("five-second", RUN.validate_output(item, output, 0, 0))
        output["elapsed_ns"] = 10_000_000_000
        output["allocator_library_path"] = "/wrong/libmimalloc.so"
        self.assertIn("library", RUN.validate_output(item, output, 0, 0))

    def test_memory_validation_is_not_bypassed(self):
        item = RUN.entries_for(self.plan, {"memory-return"}, "smoke")[0]
        output = dict(valid=True, allocator_version=item["mi_version"],
                      allocator_library_path=item["library_path"], elapsed_ns=6_000_000_000,
                      operation_count=item["expected_operation_count"], checksum=1)
        self.assertIn("enhanced memory", RUN.validate_output(item, output, 0, 0))

    def test_timeout_with_byte_output_is_durable(self):
        item = RUN.entries_for(self.plan, {"core"}, "pilot")[0]
        error = RUN.BASE.subprocess.TimeoutExpired(["benchmark"], 180,
                                                   output=b"partial output", stderr=b"error output")
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as directory:
            destination = pathlib.Path(directory)
            with patch.object(RUN.BASE.subprocess, "run", side_effect=error):
                row = RUN.BASE.execute_one(item, 1, destination / "raw", destination / "logs", "test-hash")
            self.assertFalse(row["valid"])
            self.assertIn("timeout", row["invalid_reason"])
            self.assertEqual(len(list((destination / "raw").glob("*.json"))), 1)
            self.assertEqual((ROOT / row["stdout_path"]).read_text(), "partial output")


if __name__ == "__main__":
    unittest.main()
