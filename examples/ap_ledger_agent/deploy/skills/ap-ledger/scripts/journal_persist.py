"""Create a journal entry (Buchungssatz) with debit/credit lines.

Usage:
  python journal_persist.py --invoice-id 1 --entry-date 2026-01-24 \
    --description "Bareinnahmen 24.01.2026" --fiscal-period-id 1 \
    --lines-json '[{"account_code":"2700","account_name":"Kassa","debit_amount":186.00,"credit_amount":0}]'
"""

import argparse
import json
from decimal import Decimal
from _db import error, get_store, output

from models import JournalEntry, JournalLine, JournalStatus


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a journal entry")
    parser.add_argument("--invoice-id", type=int, help="Related invoice ID")
    parser.add_argument("--entry-date", required=True, help="Booking date YYYY-MM-DD")
    parser.add_argument("--description", required=True, help="Booking description")
    parser.add_argument("--fiscal-period-id", type=int, help="Fiscal period ID")
    parser.add_argument("--lines-json", required=True, help="Journal lines as JSON array")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    store = get_store(args.db_path)
    raw_lines = json.loads(args.lines_json)

    lines = []
    for i, ld in enumerate(raw_lines, start=1):
        debit = Decimal(str(ld.get("debit_amount", 0)))
        credit = Decimal(str(ld.get("credit_amount", 0)))

        if debit <= 0 and credit <= 0:
            error(f"Line {i}: debit_amount oder credit_amount muss > 0 sein.")
        if debit > 0 and credit > 0:
            error(f"Line {i}: Nur debit_amount ODER credit_amount, nicht beide.")

        lines.append(JournalLine(
            line_number=ld.get("line_number", i),
            account_code=ld["account_code"],
            account_name=ld["account_name"],
            debit_amount=debit,
            credit_amount=credit,
            tax_code=ld.get("tax_code"),
            description=ld.get("description"),
        ))

    entry = JournalEntry(
        invoice_id=args.invoice_id,
        entry_date=args.entry_date,
        description=args.description,
        status=JournalStatus.DRAFT,
        fiscal_period_id=args.fiscal_period_id,
        lines=lines,
    )

    if not entry.is_balanced():
        total_debit = sum(l.debit_amount for l in lines)
        total_credit = sum(l.credit_amount for l in lines)
        output({
            "success": False,
            "error": "journal_not_balanced",
            "message": f"Soll ({total_debit}) != Haben ({total_credit}).",
            "total_debit": float(total_debit),
            "total_credit": float(total_credit),
        })
        return

    journal_id = store.persist_journal(entry)
    output({
        "success": True,
        "journal_id": journal_id,
        "status": "draft",
        "description": args.description,
        "line_count": len(lines),
        "message": "Journal-Eintrag erstellt. Verwende journal_post.py zum Buchen.",
    })


if __name__ == "__main__":
    main()
