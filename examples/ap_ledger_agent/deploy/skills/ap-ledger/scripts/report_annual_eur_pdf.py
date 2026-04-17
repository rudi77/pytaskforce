"""Generate an annual EÜR (Einnahmen-Überschuss-Rechnung) PDF report.

Usage:
  python report_annual_eur_pdf.py --year 2026
  python report_annual_eur_pdf.py --year 2026 --customer "Anna Schmidt"
  python report_annual_eur_pdf.py --year 2026 --out reports/2026_EUR.pdf
"""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
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


def yearly_summary_table(summary: dict) -> Table:
    revenue = summary.get("total_revenue") or 0
    expenses = summary.get("total_expenses") or 0
    profit = summary.get("profit") or 0
    tax_collected = summary.get("tax_collected") or 0
    tax_paid = summary.get("tax_paid") or 0
    tax_liability = summary.get("tax_liability") or 0

    rows = [
        ["", "Netto", "USt"],
        ["Einnahmen (Betriebseinnahmen)", fmt_money(revenue), fmt_money(tax_collected)],
        ["Ausgaben (Betriebsausgaben)", fmt_money(expenses), fmt_money(tax_paid)],
        ["Gewinn / Verlust (vor Steuern)", fmt_money(profit), ""],
        ["USt-Saldo (Zahllast/Guthaben)", "", fmt_money(tax_liability)],
    ]

    tbl = Table(rows, colWidths=[95 * mm, 40 * mm, 40 * mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
        ("FONT", (0, 3), (0, 4), "Helvetica-Bold", 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("LINEABOVE", (0, 3), (-1, 3), 0.5, BORDER),
        ("LINEABOVE", (0, 4), (-1, 4), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, 2), [colors.white, BG_ROW_ALT]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tbl


def monthly_breakdown_table(monthly_rows: list[dict], country: str) -> Table:
    by_month = {r["month"]: r for r in monthly_rows}
    rows = [["Monat", "Einnahmen", "Ausgaben", "Gewinn", "USt-Saldo"]]
    total_rev = Decimal("0")
    total_exp = Decimal("0")
    total_profit = Decimal("0")
    total_tax = Decimal("0")

    for m in range(1, 13):
        row = by_month.get(m)
        if row:
            rev = Decimal(str(row["total_revenue"] or 0))
            exp = Decimal(str(row["total_expenses"] or 0))
            pro = Decimal(str(row["profit"] or 0))
            tax = Decimal(str(row["tax_liability"] or 0))
            total_rev += rev
            total_exp += exp
            total_profit += pro
            total_tax += tax
            rows.append([
                month_name(country, m),
                fmt_money(rev), fmt_money(exp), fmt_money(pro), fmt_money(tax),
            ])
        else:
            rows.append([month_name(country, m), "—", "—", "—", "—"])

    rows.append([
        "Summe",
        fmt_money(total_rev), fmt_money(total_exp),
        fmt_money(total_profit), fmt_money(total_tax),
    ])

    tbl = Table(rows, colWidths=[35 * mm, 35 * mm, 35 * mm, 35 * mm, 35 * mm])
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
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def category_table(categories: list[dict]) -> Table:
    rows = [["Kategorie", "Anzahl", "Netto", "USt", "Brutto"]]
    total_net = Decimal("0")
    total_tax = Decimal("0")
    total_gross = Decimal("0")

    for c in categories:
        net = Decimal(str(c.get("total_net") or 0))
        tax = Decimal(str(c.get("total_tax") or 0))
        gross = Decimal(str(c.get("total_gross") or 0))
        total_net += net
        total_tax += tax
        total_gross += gross
        rows.append([
            c.get("category_name") or c.get("category_code") or "—",
            str(c.get("invoice_count") or 0),
            fmt_money(net), fmt_money(tax), fmt_money(gross),
        ])

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
    return tbl


def invoice_detail_table(invoices: list[dict]) -> Table:
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
    return tbl


def signature_block(styles: dict) -> Table:
    rows = [
        ["Ort, Datum", "", "Unterschrift"],
        ["", "", ""],
    ]
    tbl = Table(rows, colWidths=[70 * mm, 15 * mm, 85 * mm], rowHeights=[5 * mm, 18 * mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
        ("LINEABOVE", (0, 1), (0, 1), 0.5, colors.black),
        ("LINEABOVE", (2, 1), (2, 1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


def generate_pdf(
    out_path: Path,
    *,
    year: int,
    country: str,
    customer: str | None,
    summary: dict,
    monthly_rows: list[dict],
    categories: list[dict],
    invoices: list[dict],
) -> None:
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"EÜR {year}" + (f" — {customer}" if customer else ""),
        author="AP-Ledger",
    )

    story: list = []

    # --- Page 1: Title + Summary + Monthly breakdown ---
    story.append(Paragraph("Einnahmen-Überschuss-Rechnung", styles["title"]))
    subtitle = f"Geschäftsjahr {year}"
    if customer:
        subtitle += f" &nbsp;·&nbsp; {customer}"
    country_label = "Österreich" if country.upper() == "AT" else "Deutschland"
    subtitle += f" &nbsp;·&nbsp; {country_label}"
    story.append(Paragraph(subtitle, styles["subtitle"]))

    has_data = (summary.get("total_revenue") or 0) != 0 or (summary.get("total_expenses") or 0) != 0

    story.append(Paragraph("<b>Jahresübersicht</b>", styles["h2"]))
    story.append(yearly_summary_table(summary))

    story.append(Paragraph("<b>Monatsaufstellung</b>", styles["h2"]))
    story.append(monthly_breakdown_table(monthly_rows, country))

    if not has_data:
        story.append(Spacer(1, 20))
        story.append(Paragraph(
            "Hinweis: Für dieses Geschäftsjahr wurden keine gebuchten Belege gefunden.",
            styles["body"],
        ))

    # --- Page 2: Categories ---
    revenues = [c for c in categories if c.get("category_type") == "revenue"]
    expenses = [c for c in categories if c.get("category_type") == "expense"]

    if revenues or expenses:
        story.append(PageBreak())

        if revenues:
            story.append(Paragraph("<b>Einnahmen nach Kategorie</b>", styles["h2"]))
            story.append(category_table(revenues))
            story.append(Spacer(1, 12))

        if expenses:
            story.append(Paragraph("<b>Ausgaben nach Kategorie</b>", styles["h2"]))
            story.append(category_table(expenses))

    # --- Page 3+: Invoice detail + signature ---
    if invoices:
        story.append(PageBreak())
        story.append(Paragraph(
            f"<b>Belegverzeichnis ({len(invoices)} Belege)</b>", styles["h2"],
        ))
        story.append(invoice_detail_table(invoices))

    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "Ich bestätige die Richtigkeit und Vollständigkeit der vorstehenden Aufstellung.",
        styles["body"],
    ))
    story.append(Spacer(1, 10))
    story.append(signature_block(styles))

    generated = datetime.now().strftime("%d.%m.%Y %H:%M")
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Erstellt am {generated} &nbsp;·&nbsp; AP-Ledger",
        styles["footer"],
    ))

    doc.build(story)


def default_output_path(year: int) -> Path:
    script_dir = Path(__file__).resolve().parent
    plugin_dir = script_dir.parent
    reports_dir = plugin_dir / "reports" / str(year)
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir / f"{year}_euer_jahresreport.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate annual EÜR PDF report")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", help="Output path (default: reports/<year>/<year>_euer_jahresreport.pdf)")
    parser.add_argument("--customer", help="Customer/mandant name shown on title page")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    try:
        store = get_store(args.db_path)
        summary = store.annual_summary(args.year)
        monthly_rows = store.monthly_totals(args.year)
        categories = store.annual_category_breakdown(args.year)
        invoices = store.annual_invoices(args.year)

        out_path = Path(args.out) if args.out else default_output_path(args.year)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        generate_pdf(
            out_path,
            year=args.year,
            country=store.country,
            customer=args.customer,
            summary=summary,
            monthly_rows=monthly_rows,
            categories=categories,
            invoices=invoices,
        )

        output({
            "success": True,
            "path": str(out_path),
            "year": args.year,
            "invoice_count": len(invoices),
            "category_count": len(categories),
            "profit": summary.get("profit"),
            "tax_liability": summary.get("tax_liability"),
        })
    except Exception as exc:
        error(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
