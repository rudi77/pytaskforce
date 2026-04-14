"""Correct an existing invoice in the AP Ledger database.

Usage:
  python invoice_correct.py --invoice-id 1 --total-gross 156.00 --total-net 130.00 \
    --total-tax 26.00 --reason "Betrag korrigiert"
"""

import argparse
import json
from _db import error, get_store, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Correct an existing invoice")
    parser.add_argument("--invoice-id", required=True, type=int, help="Invoice ID to correct")
    parser.add_argument("--total-gross", type=float, help="Corrected gross amount")
    parser.add_argument("--total-net", type=float, help="Corrected net amount")
    parser.add_argument("--total-tax", type=float, help="Corrected tax amount")
    parser.add_argument("--reason", default="", help="Reason for correction")
    parser.add_argument("--lines-json", help="Corrected lines as JSON array")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)

    # Verify invoice exists
    invoice = store.get_invoice(args.invoice_id)
    if not invoice:
        error(f"Invoice {args.invoice_id} not found")

    lines = json.loads(args.lines_json) if args.lines_json else None

    result = store.correct_invoice(
        invoice_id=args.invoice_id,
        total_gross=args.total_gross,
        total_net=args.total_net,
        total_tax=args.total_tax,
        lines=lines,
        reason=args.reason,
    )
    output({"success": True, **result})


if __name__ == "__main__":
    main()
