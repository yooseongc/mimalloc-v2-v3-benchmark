import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "memory_analyzer", ROOT / "scripts" / "analyze_memory_return_r28.py")
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


class MemoryReturnAnalysisTests(unittest.TestCase):
    def record(self, observed):
        return {
            "rss_before_burst_bytes": 100,
            "working_set_rss_bytes": 1100,
            "rss_observations": [
                {"offset_ms": offset, "rss_bytes": rss}
                for offset, rss in observed
            ],
        }

    def test_retained_fraction_is_baseline_adjusted(self):
        record = self.record([(0, 1100), (5000, 600)])
        self.assertEqual(ANALYZER.retained_fraction(record, 0), 1.0)
        self.assertEqual(ANALYZER.retained_fraction(record, 5000), 0.5)
        self.assertEqual(ANALYZER.returned_fraction(record, 5000), 0.5)

    def test_retention_is_not_clamped(self):
        record = self.record([(0, 1200), (5000, 50)])
        self.assertEqual(ANALYZER.retained_fraction(record, 0), 1.1)
        self.assertEqual(ANALYZER.retained_fraction(record, 5000), -0.05)

    def test_missing_checkpoint_is_unavailable(self):
        record = self.record([(0, 1100)])
        self.assertIsNone(ANALYZER.retained_fraction(record, 5000))


if __name__ == "__main__":
    unittest.main()
