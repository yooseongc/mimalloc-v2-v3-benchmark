#!/usr/bin/env python3
"""Render a compact SVG of measured paired throughput ratios only."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
# Only the CPU-controlled recheck revisions are final-comparison evidence.
inputs = [ROOT / "results" / "summaries" / name for name in ("summary-r12.json", "summary-r13.json", "summary-r14.json", "summary-r16.json", "summary-r17.json")]
inputs = [path for path in inputs if path.exists()]
rows = []
for path in inputs:
    data = json.loads(path.read_text())
    for pair in data.get("paired_v3_over_v2", []):
        stats = pair["throughput_ratio_v3_over_v2"]
        if stats.get("median") is not None:
            rows.append((pair["block_id"], stats["median"], stats.get("mean_95ci_normal")))

if not rows:
    raise SystemExit("no measured paired summaries found")

width, left, right, top, step = 1040, 330, 60, 55, 34
height = top + len(rows) * step + 50
scale_min, scale_max = 0.90, 2.25
plot_width = width - left - right
def x(value):
    return left + (value - scale_min) / (scale_max - scale_min) * plot_width

parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
         '<style>text{font:13px sans-serif;fill:#202124}.small{font-size:11px;fill:#5f6368}.axis{stroke:#9aa0a6}.ci{stroke:#5f6368;stroke-width:2}.dot{fill:#1a73e8}</style>',
         '<rect width="100%" height="100%" fill="white"/>',
         '<text x="20" y="27" style="font-size:18px;font-weight:600">Measured median throughput ratio (v3.4.3 / v2.1.2)</text>']
for tick in (0.9, 1.0, 1.25, 1.5, 2.0, 2.25):
    px = x(tick)
    parts.extend([f'<line class="axis" x1="{px:.1f}" y1="42" x2="{px:.1f}" y2="{height-30}"/>',
                  f'<text class="small" x="{px-10:.1f}" y="{height-10}">{tick:g}</text>'])
for i, (label, median, ci) in enumerate(rows):
    y = top + i * step
    parts.append(f'<text x="10" y="{y+4}">{escape(label)}</text>')
    if ci:
        parts.append(f'<line class="ci" x1="{x(ci[0]):.1f}" y1="{y}" x2="{x(ci[1]):.1f}" y2="{y}"/>')
    parts.append(f'<circle class="dot" cx="{x(median):.1f}" cy="{y}" r="5"/>')
    parts.append(f'<text class="small" x="{x(median)+8:.1f}" y="{y+4}">{median:.3f}</text>')
parts.append('</svg>')
(ROOT / "results" / "plots" / "throughput-ratios.svg").write_text("\n".join(parts))
