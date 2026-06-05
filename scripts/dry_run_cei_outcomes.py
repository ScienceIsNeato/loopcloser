#!/usr/bin/env python3
"""Dry-run the CEI outcomes-results adapter (parse-only, no database writes).

Parses the CEI FY25 workbook and prints entity counts, cleaning diagnostics,
and a few sample records so the parse can be sanity-checked before any import.

Usage:
    python scripts/dry_run_cei_outcomes.py [path/to/workbook.xlsx]
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.adapters.cei_outcomes_results_adapter import CEIOutcomesResultsAdapter

DEFAULT_FILE = "data/cei/FY25 BTT Division Outcomes Results.xlsx"
DEMO_INSTITUTION_ID = "cei-demo-dry-run"


def _sample(rows: List[Dict[str, Any]], n: int = 3) -> str:
    return json.dumps(rows[:n], indent=2, default=str)


def main() -> int:
    file_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return 1

    adapter = CEIOutcomesResultsAdapter()

    print("=" * 70)
    print("COMPATIBILITY")
    print("=" * 70)
    ok, msg = adapter.validate_file_compatibility(file_path)
    print(f"  compatible: {ok}")
    print(f"  message:    {msg}")
    print(f"  data types: {adapter.detect_data_types(file_path)}")
    if not ok:
        return 1

    print("\n" + "=" * 70)
    print("PARSE (dry run — no writes)")
    print("=" * 70)
    result = adapter.parse_file(file_path, {"institution_id": DEMO_INSTITUTION_ID})
    stats = adapter.last_parse_stats

    print("\nEntity counts:")
    for key, rows in result.items():
        print(f"  {key:22s} {len(rows):>6d}")

    print("\nCleaning diagnostics:")
    for key in (
        "granular_total_rows",
        "rollup_rows_dropped",
        "shifted_rows_repaired",
        "rows_dropped_unknown_term",
        "measurements",
        "program_rows",
        "mapping_entries",
    ):
        if key in stats:
            print(f"  {key:28s} {stats[key]:>6d}")

    print("\nIntegrity checks:")
    bad = [
        so
        for so in result["section_outcomes"]
        if so["students_passed"] > so["students_took"]
    ]
    print(f"  section_outcomes with passed>took: {len(bad)}")
    took_total = sum(so["students_took"] for so in result["section_outcomes"])
    passed_total = sum(so["students_passed"] for so in result["section_outcomes"])
    rate = (passed_total / took_total) if took_total else 0
    print(
        f"  total took={took_total}  passed={passed_total}  overall pass rate={rate:.3f}"
    )
    s_count = sum(1 for so in result["section_outcomes"] if so["result"] == "S")
    print(f"  satisfactory (S) outcomes: {s_count}/{len(result['section_outcomes'])}")

    print("\nSamples:")
    for key in (
        "programs",
        "program_outcomes",
        "courses",
        "clos",
        "users",
        "terms",
        "sections",
        "section_outcomes",
        "plo_mapping_entries",
    ):
        print(f"\n  --- {key} ---")
        print(_sample(result[key]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
