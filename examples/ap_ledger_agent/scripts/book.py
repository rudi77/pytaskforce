"""All-in-one booking script: persist invoice + journal + post + audit in one call.

Usage (revenue/Tageslosung):
  python book.py revenue --date 2026-01-24 --bar 186.00
  python book.py revenue --date 2026-01-24 --bar 300.00 --karte 150.00
  python book.py revenue --date 2026-01-24 --bar 186.00 --tax-code DE_19

Usage (expense):
  python book.py expense --vendor "Wella" --date 2026-04-14 --gross 119.00 \
    --category waren_farbe --tax-code DE_19 --payment bar
  python book.py expense --vendor "A1 Telekom" --date 2026-04-14 --gross 39.90 \
    --category telefon_internet --tax-code DE_19 --payment bank
"""

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP

from _db import error, get_store, output

from ap_ledger_agent.domain.models import (
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    InvoiceType,
    JournalEntry,
    JournalLine,
    JournalStatus,
)

# Account mappings
CATEGORY_TO_ACCOUNT = {
    "einnahmen_bar": ("4000", "Erlöse Bareinnahmen"),
    "einnahmen_karte": ("4010", "Erlöse Karteneinnahmen"),
    "einnahmen_gutschein": ("4020", "Erlöse Gutscheine"),
    "einnahmen_sonstige": ("4090", "Sonstige Erlöse"),
    "waren_farbe": ("5100", "Wareneinsatz Haarfarben"),
    "waren_pflege": ("5110", "Wareneinsatz Pflegeprodukte"),
    "waren_verbrauch": ("5120", "Verbrauchsmaterial"),
    "waren_verkauf": ("5130", "Wareneinsatz Verkaufsware"),
    "miete": ("6200", "Mietaufwand"),
    "betriebskosten": ("6210", "Betriebskosten"),
    "versicherung": ("6300", "Versicherungsaufwand"),
    "telefon_internet": ("6400", "Telefon & Internet"),
    "werbung": ("6600", "Werbeaufwand"),
    "fortbildung": ("6700", "Fortbildungskosten"),
    "geraete": ("6800", "Werkzeuge & Geräte"),
    "buero": ("6820", "Bürobedarf"),
    "kfz": ("6900", "KFZ-Kosten"),
    "bank": ("6950", "Bankgebühren"),
    "steuerberater": ("6960", "Steuerberatung"),
    "reinigung": ("6970", "Reinigungskosten"),
    "sonstige_ausgaben": ("6990", "Sonstige Betriebsausgaben"),
}

VORSTEUER_ACCOUNTS = {
    "AT_20": ("2500", "Vorsteuer 20%"),
    "DE_19": ("2500", "Vorsteuer 19%"),
    "AT_10": ("2501", "Vorsteuer 10%"),
    "DE_7": ("2501", "Vorsteuer 7%"),
    "AT_13": ("2502", "Vorsteuer 13%"),
}


def _log_failure(store, booking_type: str, err: str, date: str = "") -> None:
    """Best-effort audit log for failed bookings (separate connection)."""
    try:
        store.write_audit(
            "booking_failed", "invoice", 0, "agent",
            json.dumps({"type": booking_type, "error": err, "date": date}),
        )
    except Exception:
        pass  # must not mask the original error


def _round2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_tax_rate(store, tax_code: str) -> Decimal:
    tc = store.resolve_tax(tax_code)
    if not tc:
        error(f"Unknown tax code: {tax_code}")
    return tc.rate


def _split_tax(gross: Decimal, tax_rate: Decimal) -> tuple[Decimal, Decimal]:
    """Split a gross amount into (net, tax). Single source of truth for rounding."""
    net = _round2(gross / (1 + tax_rate))
    return net, _round2(gross - net)


def _revenue_journal_lines(
    gross: Decimal, net: Decimal, tax: Decimal,
    debit_account: str, debit_name: str,
    credit_account: str, credit_name: str,
    start_ln: int,
) -> list[JournalLine]:
    """Build the 3 journal lines for a single revenue stream (bar or karte)."""
    return [
        JournalLine(line_number=start_ln, account_code=debit_account, account_name=debit_name,
                     debit_amount=gross, credit_amount=Decimal("0")),
        JournalLine(line_number=start_ln + 1, account_code=credit_account, account_name=credit_name,
                     debit_amount=Decimal("0"), credit_amount=net),
        JournalLine(line_number=start_ln + 2, account_code="3500", account_name="Umsatzsteuer",
                     debit_amount=Decimal("0"), credit_amount=tax),
    ]


def book_revenue(args) -> None:
    store = get_store(args.db_path)

    bar = Decimal(str(args.bar or 0))
    karte = Decimal(str(args.karte or 0))
    if bar <= 0 and karte <= 0:
        error("Mindestens --bar oder --karte muss > 0 sein")

    tax_rate = _get_tax_rate(store, args.tax_code)
    total_gross = bar + karte
    period = store.resolve_period(args.date)

    # Build invoice lines + journal lines from the same net/tax values
    invoice_lines: list[InvoiceLine] = []
    journal_lines: list[JournalLine] = []
    ln = 1

    if bar > 0:
        net, tax = _split_tax(bar, tax_rate)
        invoice_lines.append(InvoiceLine(
            position=len(invoice_lines) + 1, description="Bareinnahmen", quantity=Decimal("1"),
            net_amount=net, tax_code=args.tax_code, tax_amount=tax,
            gross_amount=bar, category_code="einnahmen_bar",
        ))
        journal_lines.extend(_revenue_journal_lines(
            bar, net, tax, "2700", "Kassa", "4000", "Erloese Bar", ln))
        ln += 3

    if karte > 0:
        net, tax = _split_tax(karte, tax_rate)
        invoice_lines.append(InvoiceLine(
            position=len(invoice_lines) + 1, description="Karteneinnahmen", quantity=Decimal("1"),
            net_amount=net, tax_code=args.tax_code, tax_amount=tax,
            gross_amount=karte, category_code="einnahmen_karte",
        ))
        journal_lines.extend(_revenue_journal_lines(
            karte, net, tax, "2800", "Bank", "4010", "Erloese Karte", ln))
        ln += 3

    total_net = sum(l.net_amount for l in invoice_lines)
    total_tax = sum(l.tax_amount for l in invoice_lines)

    invoice = Invoice(
        vendor_name_raw="Tageslosung", invoice_date=args.date,
        total_gross=total_gross, total_net=total_net, total_tax=total_tax,
        type=InvoiceType.RECEIPT, status=InvoiceStatus.VALIDATED,
        source_file=getattr(args, "source_file", None),
        source_type="photo" if getattr(args, "source_file", None) else "manual",
        fiscal_period_id=period.id, lines=invoice_lines,
    )
    entry = JournalEntry(
        invoice_id=0, entry_date=args.date,
        description=f"Tageslosung {args.date}",
        status=JournalStatus.DRAFT, fiscal_period_id=period.id,
        lines=journal_lines,
    )

    # Atomic: invoice + journal + post + audit in one transaction
    invoice_id = journal_id = 0
    try:
        with store.transaction() as conn:
            invoice_id = store.persist_invoice(invoice, conn=conn)
            entry.invoice_id = invoice_id
            journal_id = store.persist_journal(entry, conn=conn)
            store.post_journal(journal_id, conn=conn)
            store.write_audit("invoice_posted", "invoice", invoice_id, "agent",
                              json.dumps({"type": "revenue", "gross": float(total_gross)}),
                              conn=conn)
    except Exception as e:
        _log_failure(store, "revenue", str(e), args.date)
        error(f"Buchung fehlgeschlagen: {e}")

    parts = []
    if bar > 0:
        parts.append(f"{float(bar):.2f}EUR bar")
    if karte > 0:
        parts.append(f"{float(karte):.2f}EUR Karte")

    output({
        "success": True,
        "invoice_id": invoice_id,
        "journal_id": journal_id,
        "status": "posted",
        "date": args.date,
        "total_gross": float(total_gross),
        "total_net": float(total_net),
        "total_tax": float(total_tax),
        "summary": f"Tageslosung {args.date}: {' + '.join(parts)} = {float(total_gross):.2f}EUR",
    })


def book_expense(args) -> None:
    store = get_store(args.db_path)

    gross = Decimal(str(args.gross))
    tax_rate = _get_tax_rate(store, args.tax_code)
    net = _round2(gross / (1 + tax_rate)) if tax_rate > 0 else gross
    tax = _round2(gross - net)

    period = store.resolve_period(args.date)

    # Vendor resolve or create
    vendors = store.resolve_vendor(args.vendor)
    if vendors:
        vendor_id = vendors[0].id
        category = args.category or vendors[0].default_category_code or "sonstige_ausgaben"
    else:
        category = args.category or "sonstige_ausgaben"
        vendor = store.create_vendor(args.vendor, category_code=category, tax_code=args.tax_code)
        vendor_id = vendor.id

    account_code, account_name = CATEGORY_TO_ACCOUNT.get(category, ("6990", "Sonstige Ausgaben"))

    # Invoice
    invoice = Invoice(
        vendor_id=vendor_id, vendor_name_raw=args.vendor, invoice_date=args.date,
        total_gross=gross, total_net=net, total_tax=tax,
        type=InvoiceType.INVOICE, status=InvoiceStatus.VALIDATED,
        source_file=args.source_file,
        source_type=args.source_type or "photo",
        fiscal_period_id=period.id, external_ref=args.ref,
        lines=[InvoiceLine(
            position=1, description=args.description or args.vendor,
            quantity=Decimal("1"), net_amount=net, tax_code=args.tax_code,
            tax_amount=tax, gross_amount=gross, category_code=category,
        )],
    )
    # Journal
    payment_account = "2700" if args.payment == "bar" else "2800"
    payment_name = "Kassa" if args.payment == "bar" else "Bank"

    journal_lines = [
        JournalLine(line_number=1, account_code=account_code, account_name=account_name,
                    debit_amount=net, credit_amount=Decimal("0"), tax_code=args.tax_code),
    ]
    ln = 2
    if tax > 0:
        vst_code, vst_name = VORSTEUER_ACCOUNTS.get(args.tax_code, ("2500", "Vorsteuer"))
        journal_lines.append(JournalLine(
            line_number=ln, account_code=vst_code, account_name=vst_name,
            debit_amount=tax, credit_amount=Decimal("0"),
        ))
        ln += 1
    journal_lines.append(JournalLine(
        line_number=ln, account_code=payment_account, account_name=payment_name,
        debit_amount=Decimal("0"), credit_amount=gross,
    ))

    entry = JournalEntry(
        invoice_id=0, entry_date=args.date,
        description=f"{args.vendor} {args.date}",
        status=JournalStatus.DRAFT, fiscal_period_id=period.id,
        lines=journal_lines,
    )

    # Atomic: invoice + journal + post + audit in one transaction
    invoice_id = journal_id = 0
    try:
        with store.transaction() as conn:
            invoice_id = store.persist_invoice(invoice, conn=conn)
            entry.invoice_id = invoice_id
            journal_id = store.persist_journal(entry, conn=conn)
            store.post_journal(journal_id, conn=conn)
            store.write_audit("invoice_posted", "invoice", invoice_id, "agent",
                              json.dumps({"vendor": args.vendor, "gross": float(gross)}),
                              conn=conn)
    except Exception as e:
        _log_failure(store, "expense", str(e), args.date)
        error(f"Buchung fehlgeschlagen: {e}")

    output({
        "success": True,
        "invoice_id": invoice_id,
        "journal_id": journal_id,
        "status": "posted",
        "date": args.date,
        "vendor": args.vendor,
        "category": category,
        "total_gross": float(gross),
        "total_net": float(net),
        "total_tax": float(tax),
        "summary": f"{args.vendor} {float(gross):.2f}EUR -> {category} ({payment_name})",
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="All-in-one booking")
    sub = parser.add_subparsers(dest="action", required=True)

    # Revenue
    rev = sub.add_parser("revenue", help="Book revenue (Tageslosung)")
    rev.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    rev.add_argument("--bar", type=float, default=0, help="Cash amount")
    rev.add_argument("--karte", type=float, default=0, help="Card amount")
    rev.add_argument("--tax-code", default=None, help="Tax code (auto-detected from DB if omitted)")
    rev.add_argument("--source-file", help="Path to archived receipt file")
    rev.add_argument("--db-path", help="Override database path")

    # Expense
    exp = sub.add_parser("expense", help="Book expense")
    exp.add_argument("--vendor", required=True, help="Vendor name")
    exp.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    exp.add_argument("--gross", required=True, type=float, help="Gross amount")
    exp.add_argument("--category", help="Category code (auto from vendor if omitted)")
    exp.add_argument("--tax-code", default=None, help="Tax code")
    exp.add_argument("--payment", choices=["bar", "bank"], default="bank", help="Payment method")
    exp.add_argument("--description", help="Line item description")
    exp.add_argument("--ref", help="External reference / invoice number")
    exp.add_argument("--source-file", help="Path to archived receipt file")
    exp.add_argument("--source-type", choices=["photo", "pdf", "manual"], default="photo")
    exp.add_argument("--db-path", help="Override database path")

    args = parser.parse_args()

    try:
        # Auto-detect default tax code from DB if not specified
        if not args.tax_code:
            store = get_store(args.db_path)
            codes = store.list_tax_codes()
            # Find the standard rate (highest non-zero rate)
            standard = max((c for c in codes if c["rate"] > 0), key=lambda c: c["rate"], default=None)
            if standard:
                args.tax_code = standard["code"]
            else:
                error("No tax codes found in DB. Initialize the database first.")

        if args.action == "revenue":
            book_revenue(args)
        elif args.action == "expense":
            book_expense(args)
    except SystemExit:
        raise  # let error() exit normally
    except Exception as e:
        error(f"Unerwarteter Fehler: {e}")


if __name__ == "__main__":
    main()
