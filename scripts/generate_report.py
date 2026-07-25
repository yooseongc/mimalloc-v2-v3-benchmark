#!/usr/bin/env python3
"""Render measured summary facts only; never synthesize unmeasured results."""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
summary_path = ROOT / "results/summaries/summary.json"
if not summary_path.exists():
    raise SystemExit("no analysis summary exists")
data = json.loads(summary_path.read_text())
lines = ["# Generated measurement appendix", "",
         "This appendix is generated only from immutable raw records. A block with fewer than 15 valid paired repetitions is preliminary and must not be used for an allocator recommendation.", "",
         "## Collection status", "",
         "- Analysis scope: %s" % data.get("analysis_scope", "all-valid-records"),
         "- Raw records: %s" % data["raw_records"],
         "- Valid, de-duplicated records: %s" % data["valid_records"],
         "- Valid records in analysis scope: %s" % data.get("scoped_valid_records", data["valid_records"]),
         "- Duplicate raw records excluded from derivation: %s" % len(data["duplicate_records_excluded"]), "",
         "## Per-allocator groups", "",
         "| Block | Scenario | Threads | Version | Valid reps | Median ops/s | CV |", "|---|---|---:|---:|---:|---:|---:|"]
for group in data["groups"]:
    key = group["key"]
    stats = group["throughput_ops_per_second"]
    def number(value):
        return "unavailable" if value is None else ("%.4g" % value)
    lines.append("| %s | %s | %s | %s | %s | %s | %s |" %
                 (key[0], key[1], key[2], key[-1], group["valid_repetitions"],
                  number(stats.get("median")), number(stats.get("coefficient_of_variation"))))
lines.extend(["", "## Paired v3 / v2 ratios", "",
              "| Block | Paired reps | Median throughput ratio | 95% CI of mean ratio |", "|---|---:|---:|---:|"])
for pair in data["paired_v3_over_v2"]:
    stats = pair["throughput_ratio_v3_over_v2"]
    ci = stats.get("mean_95ci_normal")
    ci_text = "unavailable" if ci is None else "%.4g .. %.4g" % (ci[0], ci[1])
    lines.append("| %s | %s | %s | %s |" % (pair["block_id"], pair["paired_repetitions"],
                 number(stats.get("median")), ci_text))
out = ROOT / "results/summaries/generated-report.md"
out.write_text("\n".join(lines) + "\n")
