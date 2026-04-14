"""Persist an invoice with line items to the AP Ledger database.

Usage:
  python invoice_persist.py --vendor-name-raw "Tageslosung" --invoice-date 2026-01-24 \
    --total-gross 186.00 --total-net 155.00 --total-tax 31.00 --type receipt \
    --source-type manual --lines-json '[{"description":"Bareinnahmen","gross_amount":186.00,...}]'
"""

import argparse
import json
from decimal import Decimal
from _db import error, get_store, output

from ap_ledger_agent.domain.models import Invoice, InvoiceLine, InvoiceStatus, InvoiceType


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist an invoice")
    parser.add_argument("--vendor-name-raw", required=True, help="Original vendor name")
    parser.add_argument("--vendor-id", type=int, help="Resolved vendor ID")
    parser.add_argument("--invoice-date", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--total-gross", required=True, type=float, help="Total gross EUR")
    parser.add_argument("--total-net", type=float, help="Total net EUR")
    parser.add_argument("--total-tax", type=float, help="Total tax EUR")
    parser.add_argument("--external-ref", help="External invoice number")
    parser.add_argument("--due-date", help="Due date YYYY-MM-DD")
    parser.add_argument("--type", choices=["invoice", "receipt", "credit_note"], default="invoice")
    parser.add_argument("--source-file", help="Path to original file")
    parser.add_argument("--source-type", choices=["photo", "pdf", "manual"])
    parser.add_argument("--extraction-confidence", type=float)
    parser.add_argument("--fiscal-period-id", type=int)
    parser.add_argument("--notes", help="Additional notes")
    parser.add_argument("--lines-json", help="Line items as JSON array")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)

    # Duplicate check
    dupes = store.find_duplicate(
        args.vendor_name_raw, args.invoice_date, Decimal(str(args.total_gross))
    )
    if dupes:
        output({
            "success": False,
            "error": "possible_duplicate",
            "duplicates": dupes,
            "message": f"Mögliches Duplikat: {len(dupes)} ähnliche Belege gefunden.",
        })
        return

    # Parse lines
    lines = []
    if args.lines_json:
        for i, ld in enumerate(json.loads(args.lines_json), start=1):
            lines.append(InvoiceLine(
                position=ld.get("position", i),
                description=ld.get("description", ""),
                quantity=Decimal(str(ld.get("quantity", 1))),
                unit_price=Decimal(str(ld["unit_price"])) if ld.get("unit_price") else None,
                net_amount=Decimal(str(ld.get("net_amount", 0))),
                tax_code=ld.get("tax_code"),
                tax_amount=Decimal(str(ld["tax_amount"])) if ld.get("tax_amount") else None,
                gross_amount=Decimal(str(ld.get("gross_amount", 0))),
                category_code=ld.get("category_code"),
            ))

    invoice = Invoice(
        external_ref=args.external_ref,
        vendor_id=args.vendor_id,
        vendor_name_raw=args.vendor_name_raw,
        invoice_date=args.invoice_date,
        due_date=args.due_date,
        total_gross=Decimal(str(args.total_gross)),
        total_net=Decimal(str(args.total_net)) if args.total_net else None,
        total_tax=Decimal(str(args.total_tax)) if args.total_tax else None,
        type=InvoiceType(args.type),
        status=InvoiceStatus.VALIDATED,
        source_file=args.source_file,
        source_type=args.source_type,
        extraction_confidence=args.extraction_confidence,
        fiscal_period_id=args.fiscal_period_id,
        notes=args.notes,
        lines=lines,
    )

    invoice_id = store.persist_invoice(invoice)
    output({
        "success": True,
        "invoice_id": invoice_id,
        "vendor_name": args.vendor_name_raw,
        "total_gross": args.total_gross,
        "line_count": len(lines),
    })


if __name__ == "__main__":
    main()
