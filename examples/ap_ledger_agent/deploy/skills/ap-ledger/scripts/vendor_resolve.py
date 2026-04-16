"""Resolve or create a vendor in the AP Ledger database.

Usage:
  python vendor_resolve.py --vendor-name "Wella Austria"
  python vendor_resolve.py --action create --vendor-name "New Vendor" --category-code material
"""

import argparse
from _db import error, get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve or create a vendor")
    parser.add_argument("--vendor-name", required=True, help="Vendor name to search/create")
    parser.add_argument("--action", choices=["search", "create"], default="search")
    parser.add_argument("--category-code", help="Default category code (for create)")
    parser.add_argument("--tax-code", default="AT_20", help="Default tax code (for create)")
    parser.add_argument("--keywords", help="Match keywords (for create)")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)

    if args.action == "create":
        vendor = store.create_vendor(
            name=args.vendor_name,
            category_code=args.category_code,
            tax_code=args.tax_code,
            keywords=args.keywords,
        )
        output({
            "success": True,
            "action": "created",
            "vendor": {
                "id": vendor.id,
                "name": vendor.name,
                "default_category_code": vendor.default_category_code,
                "default_tax_code": vendor.default_tax_code,
            },
        })
    else:
        vendors = store.resolve_vendor(args.vendor_name)
        output({
            "success": True,
            "found": len(vendors),
            "vendors": [
                {
                    "id": v.id,
                    "name": v.name,
                    "default_category_code": v.default_category_code,
                    "default_tax_code": v.default_tax_code,
                    "match_keywords": v.match_keywords,
                }
                for v in vendors
            ],
        })


if __name__ == "__main__":
    main()
