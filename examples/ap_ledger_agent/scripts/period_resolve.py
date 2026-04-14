"""Resolve the fiscal period for a given date.

Usage:
  python period_resolve.py --date 2026-01-24
"""

import argparse
from _db import error, get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve fiscal period for a date")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    if len(args.date) < 10:
        error(f"Invalid date format: '{args.date}'. Expected YYYY-MM-DD")

    store = get_store(args.db_path)
    period = store.resolve_period(args.date)
    output({
        "success": True,
        "period": {
            "id": period.id,
            "year": period.year,
            "month": period.month,
            "label": period.label,
            "start_date": period.start_date,
            "end_date": period.end_date,
            "is_closed": period.is_closed,
        },
    })


if __name__ == "__main__":
    main()
