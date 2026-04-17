"""Generate a professional monthly PDF report for an AP-Ledger mandant.

Usage:
  python report_monthly_pdf.py --year 2026 --month 3
  python report_monthly_pdf.py --year 2026 --month 3 --out reports/2026-03.pdf
  python report_monthly_pdf.py --year 2026 --month 3 --customer "Anna Schmidt"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from _db import error, get_store, output
from _pdf import (
    ACCENT,
    BG_ROW_ALT,
    BORDER,
    build_styles,
    fmt_money,
    month_name,
)


def summary_table(summary: dict, styles: dict) -> Table:
    revenue = summary.get("total_revenue") or 0
    expenses = summary.get("total_expenses") or 0
    profit = summary.get("profit") or 0
    tax_collected = summary.get("tax_collected") or 0
    tax_paid = summary.get("tax_paid") or 0
    tax_liability = summary.get("tax_liability") or 0

    rows = [
        ["", "Netto", "USt"],
        ["Einnahmen", fmt_money(revenue), fmt_money(tax_collected)],
        ["Ausgaben", fmt_money(expenses), fmt_money(tax_paid)],
        ["Gewinn (vor Steuern)", fmt_money(profit), ""],
        ["USt-Saldo (Zahllast/Guthaben)", "", fmt_money(tax_liability)],
    ]

    tbl = Table(rows, colWidths=[85 * mm, 40 * mm, 40 * mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
        ("FONT", (0, 3), (0, 4), "Helvetica-Bold", 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, ACCENT),
        ("LINEABOVE", (0, 3), (-1, 3), 0.5, BORDER),
        ("LINEABOVE", (0, 4), (-1, 4), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, 2), [colors.white, BG_ROW_ALT]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tbl


def category_table(
    categories: list[dict], title: str, styles: dict, *, max_rows: int = 10
) -> list:
    if not categories:
        return []

    rows = [["Kategorie", "Anzahl", "Netto", "USt", "Brutto"]]
    total_net = Decimal("0")
    total_tax = Decimal("0")
    total_gross = Decimal("0")
    shown = categories[:max_rows]
    for c in shown:
        net = Decimal(str(c.get("total_net") or 0))
        tax = Decimal(str(c.get("total_tax") or 0))
        gross = Decimal(str(c.get("total_gross") or 0))
        total_net += net
        total_tax += tax
        total_gross += gross
        rows.append([
            c.get("category_name") or c.get("category_code") or "—",
            str(c.get("invoice_count") or 0),
            fmt_money(net),
            fmt_money(tax),
            fmt_money(gross),
        ])

    if len(categories) > max_rows:
        rest_net = sum(Decimal(str(c.get("total_net") or 0)) for c in categories[max_rows:])
        rest_tax = sum(Decimal(str(c.get("total_tax") or 0)) for c in categories[max_rows:])
        rest_gross = sum(Decimal(str(c.get("total_gross") or 0)) for c in categories[max_rows:])
        rest_count = sum((c.get("invoice_count") or 0) for c in categories[max_rows:])
        rows.append([
            f"Weitere ({len(categories) - max_rows})",
            str(rest_count),
            fmt_money(rest_net),
            fmt_money(rest_tax),
            fmt_money(rest_gross),
        ])
        total_net += rest_net
        total_tax += rest_tax
        total_gross += rest_gross

    rows.append([
        "Summe", "",
        fmt_money(total_net), fmt_money(total_tax), fmt_money(total_gross),
    ])

    tbl = Table(rows, colWidths=[75 * mm, 18 * mm, 28 * mm, 25 * mm, 28 * mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("FONT", (0, 1), (-1, -2), "Helvetica", 9),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("BACKGROUND", (0, -1), (-1, -1), BG_ROW_ALT),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, BG_ROW_ALT]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [Paragraph(f"<b>{title}</b>", styles["h2"]), tbl]


def invoice_table(invoices: list[dict], styles: dict) -> list:
    if not invoices:
        return [
            Paragraph("<b>Belege</b>", styles["h2"]),
            Paragraph("Keine gebuchten Belege in diesem Monat.", styles["body"]),
        ]

    rows = [["Datum", "Lieferant", "Kategorie", "Netto", "USt", "Brutto"]]
    for inv in invoices:
        vendor = inv.get("vendor_name") or inv.get("vendor_name_raw") or "—"
        if len(vendor) > 30:
            vendor = vendor[:29] + "…"
        category = inv.get("category_name") or "—"
        if len(category) > 22:
            category = category[:21] + "…"
        rows.append([
            inv.get("invoice_date") or "",
            vendor,
            category,
            fmt_money(inv.get("total_net")),
            fmt_money(inv.get("total_tax")),
            fmt_money(inv.get("total_gross")),
        ])

    tbl = Table(
        rows,
        colWidths=[22 * mm, 48 * mm, 42 * mm, 25 * mm, 20 * mm, 25 * mm],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (2, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_ROW_ALT]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Paragraph("<b>Belege</b>", styles["h2"]), tbl]


def generate_pdf(
    out_path: Path,
    *,
    year: int,
    month: int,
    country: str,
    customer: str | None,
    summary: dict | None,
    categories: list[dict],
    invoices: list[dict],
) -> None:
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Monatsreport {month_name(country, month)} {year}",
        author="AP-Ledger",
    )

    story: list = []
    story.append(Paragraph("Monatsreport", styles["title"]))
    subtitle = f"{month_name(country, month)} {year}"
    if customer:
        subtitle += f" &nbsp;·&nbsp; {customer}"
    story.append(Paragraph(subtitle, styles["subtitle"]))

    story.append(Paragraph("<b>Übersicht</b>", styles["h2"]))
    if summary:
        story.append(summary_table(summary, styles))
    else:
        story.append(Paragraph(
            "Keine gebuchten Belege in diesem Monat.", styles["body"]
        ))

    expenses = [c for c in categories if c.get("category_type") == "expense"]
    revenues = [c for c in categories if c.get("category_type") == "revenue"]

    if expenses:
        story.append(Spacer(1, 8))
        story.extend(category_table(expenses, "Ausgaben nach Kategorie", styles))

    if revenues:
        story.append(Spacer(1, 8))
        story.extend(category_table(revenues, "Einnahmen nach Kategorie", styles))

    story.append(Spacer(1, 8))
    story.extend(invoice_table(invoices, styles))

    generated = datetime.now().strftime("%d.%m.%Y %H:%M")
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Erstellt am {generated} &nbsp;·&nbsp; AP-Ledger",
        styles["footer"],
    ))

    doc.build(story)


def default_output_path(year: int, month: int) -> Path:
    script_dir = Path(__file__).resolve().parent
    plugin_dir = script_dir.parent
    reports_dir = plugin_dir / "reports" / str(year)
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir / f"{year}-{month:02d}_monatsreport.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly PDF report")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True, choices=range(1, 13))
    parser.add_argument("--out", help="Output path (default: reports/<year>/<year>-<mm>_monatsreport.pdf)")
    parser.add_argument("--customer", help="Customer/mandant name to show in header")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    try:
        store = get_store(args.db_path)
        summary = store.monthly_summary(args.year, args.month)
        categories = store.monthly_category_breakdown(args.year, args.month)
        invoices = store.monthly_invoices(args.year, args.month)

        out_path = Path(args.out) if args.out else default_output_path(args.year, args.month)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        generate_pdf(
            out_path,
            year=args.year,
            month=args.month,
            country=store.country,
            customer=args.customer,
            summary=summary,
            categories=categories,
            invoices=invoices,
        )

        output({
            "success": True,
            "path": str(out_path),
            "year": args.year,
            "month": args.month,
            "invoice_count": len(invoices),
            "has_data": summary is not None,
        })
    except Exception as exc:
        error(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
