"""Resolve or list tax codes.

Usage:
  python tax_resolve.py --tax-code DE_19
  python tax_resolve.py --action list
"""

import argparse
from _db import error, get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve tax codes")
    parser.add_argument("--tax-code", help="Tax code to resolve (e.g. DE_19, AT_20)")
    parser.add_argument("--action", choices=["resolve", "list"], default="resolve")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)

    if args.action == "list":
        tax_codes = store.list_tax_codes()
        output({"success": True, "tax_codes": tax_codes})
        return

    if not args.tax_code:
        error("--tax-code is required for resolve action")

    tc = store.resolve_tax(args.tax_code)
    if not tc:
        error(f"Steuercode '{args.tax_code}' nicht gefunden.")

    output({
        "success": True,
        "tax_code": {
            "code": tc.code,
            "rate": float(tc.rate),
            "label": tc.label,
            "description": tc.description,
        },
    })


if __name__ == "__main__":
    main()
