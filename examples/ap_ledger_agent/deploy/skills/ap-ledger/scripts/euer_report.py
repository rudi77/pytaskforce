"""Generate EUER reports, monthly summaries, and CSV exports.

Usage:
  python euer_report.py --action monthly --year 2026
  python euer_report.py --action euer --year 2026
  python euer_report.py --action csv --year 2026
  python euer_report.py --action open
  python euer_report.py --action categories
"""

import argparse
from _db import error, get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EUER reports")
    parser.add_argument("--action", required=True,
                        choices=["monthly", "euer", "csv", "open", "categories"])
    parser.add_argument("--year", type=int, help="Year to report on")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    if args.action in ("euer", "csv") and not args.year:
        error(f"--year is required for action '{args.action}'")

    store = get_store(args.db_path)

    if args.action == "monthly":
        totals = store.monthly_totals(args.year)
        output({"success": True, "monthly_totals": totals})

    elif args.action == "euer":
        summary = store.euer_summary(args.year)
        output({"success": True, "year": args.year, "euer_summary": summary})

    elif args.action == "csv":
        csv_content = store.export_csv(args.year)
        if not csv_content:
            output({"success": True, "csv": "",
                     "message": f"Keine gebuchten Belege fuer {args.year}."})
        else:
            output({"success": True, "csv": csv_content,
                     "message": f"CSV-Export fuer {args.year} erstellt."})

    elif args.action == "open":
        invoices = store.open_invoices()
        output({"success": True, "open_invoices": invoices})

    elif args.action == "categories":
        categories = store.list_categories()
        output({
            "success": True,
            "categories": [
                {"code": c.code, "name": c.name, "type": c.type.value,
                 "default_tax_code": c.default_tax_code}
                for c in categories
            ],
        })


if __name__ == "__main__":
    main()
