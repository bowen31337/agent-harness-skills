#!/usr/bin/env python3
"""Print a human-readable summary of perf-report.json to stdout.

Called by .gitlab-ci.yml when the performance gate fails.
Usage: python3 .harness/perf_summary.py [path/to/perf-report.json]
"""
import json
import sys

report_path = sys.argv[1] if len(sys.argv) > 1 else "perf-report.json"

try:
    with open(report_path) as fh:
        r = json.load(fh)
except Exception as e:
    print(f"Could not parse {report_path}: {e}")
    sys.exit(0)

s = r.get("summary", {})
print(f"  Rules evaluated : {s.get('total_gates', '?')}")
print(f"  Passed          : {s.get('passed_gates', '?')}")
print(f"  Blocking (error): {s.get('blocking_failures', '?')}")
print()

for f in r.get("failures", []):
    sev = f.get("severity", "?").upper()
    rule = f.get("rule_id") or f.get("message", "unknown")
    span = (f"  span={f['span_name']}") if f.get("span_name") else ""
    measured = f.get("measured_ms")
    limit = f.get("threshold_ms")
    timing = f"  ({measured} ms vs {limit} ms limit)" if measured and limit else ""
    print(f"  [{sev}] {rule}{span}{timing}")
    if f.get("suggestion"):
        print(f"    -> {f['suggestion']}")
