import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("analysis_r29", ROOT / "scripts/analyze_r29.py")
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


class AnalysisTests(unittest.TestCase):
    def test_checksum_closed_form_at_byte_boundaries(self):
        for count in (0, 1, 255, 256, 257, 65535, 65536, 65537):
            self.assertEqual(ANALYZER.byte_checksum(count),
                             sum((i % 256) + ((i // 256) % 256) for i in range(count)))

    def test_rss_field_is_not_reported_as_peak(self):
        values = ANALYZER.metric_values(dict(operation_count=10, elapsed_ns=100,
                                            peak_rss_bytes=123, profile="core"))
        self.assertEqual(values["end_rss_bytes"], 123)
        self.assertNotIn("peak_rss_bytes", values)

    def test_memory_idle_is_not_throughput(self):
        values = ANALYZER.metric_values(dict(operation_count=10, elapsed_ns=100,
            profile="memory-return", working_set_rss_bytes=1100, rss_before_burst_bytes=100,
            rss_observations=[dict(offset_ms=5000, rss_bytes=600)]))
        self.assertNotIn("throughput_ops_per_second", values)
        self.assertEqual(values["returned_fraction_5000"], .5)

    def test_empty_statistics_are_unavailable(self):
        self.assertEqual(ANALYZER.describe([], "empty"), {"count": 0})


if __name__ == "__main__":
    unittest.main()
