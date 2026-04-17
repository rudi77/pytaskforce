"""Export all archived Belege for a period as a ZIP with an index CSV.

Usage:
  python export_belege_zip.py --year 2026
  python export_belege_zip.py --year 2026 --month 3
  python export_belege_zip.py --year 2026 --out /tmp/belege_2026.zip
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import zipfile
from pathlib import Path

from _db import error, get_store, output


def normalize_in_zip_path(source_file: str, year: int) -> str:
    """Derive the path inside the ZIP from an absolute source_file path.

    Preserves the belege/YYYY/MM/filename.ext structure if possible,
    otherwise falls back to belege/YYYY/_unsorted/filename.ext.
    """
    if not source_file:
        return ""
    path = Path(source_file)
    parts = path.parts
    if "belege" in parts:
        idx = parts.index("belege")
        return "/".join(parts[idx:])
    return f"belege/{year}/_unsorted/{path.name}"


def build_index_csv(invoices: list[dict], year: int) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "datum", "lieferant", "kategorie",
        "netto", "ust", "brutto",
        "datei_im_zip", "datei_vorhanden", "hinweis",
    ])
    for inv in invoices:
        source = inv.get("source_file") or ""
        zip_path = normalize_in_zip_path(source, year) if source else ""
        file_present = bool(source) and Path(source).exists()
        note = ""
        if not source:
            note = "Kein Beleg hinterlegt"
        elif not file_present:
            note = f"Datei fehlt am Ablageort: {source}"

        writer.writerow([
            inv.get("id", ""),
            inv.get("invoice_date", ""),
            inv.get("vendor_name") or inv.get("vendor_name_raw") or "",
            inv.get("category_name") or "",
            f"{inv.get('total_net') or 0:.2f}",
            f"{inv.get('total_tax') or 0:.2f}",
            f"{inv.get('total_gross') or 0:.2f}",
            zip_path if file_present else "",
            "ja" if file_present else "nein",
            note,
        ])
    return buf.getvalue()


def build_readme(year: int, month: int | None, customer: str | None, stats: dict) -> str:
    period = f"{year}" if month is None else f"{year}-{month:02d}"
    lines = [
        f"Belegverzeichnis {period}",
        "=" * 40,
        "",
    ]
    if customer:
        lines.append(f"Mandant: {customer}")
    lines.extend([
        f"Zeitraum: {period}",
        f"Gebuchte Belege: {stats['total']}",
        f"Mit archivierter Datei: {stats['with_file']}",
        f"Ohne Datei (fehlen im Archiv): {stats['missing']}",
        "",
        "Inhalt:",
        "  belegverzeichnis.csv  — Liste aller Belege des Zeitraums",
        "  belege/YYYY/MM/       — Originaldateien (Fotos, PDFs)",
        "",
        "Hinweis: Belege ohne archivierte Datei sind in der CSV aufgeführt,",
        "aber fehlen im ZIP. Der Grund wird in der Spalte 'hinweis' genannt.",
        "",
    ])
    return "\n".join(lines)


def default_output_path(year: int, month: int | None) -> Path:
    # Respect AP_LEDGER_ROOT for per-customer isolation (see report_monthly_pdf).
    root_env = os.environ.get("AP_LEDGER_ROOT")
    base = Path(root_env) if root_env else Path(__file__).resolve().parent.parent
    exports_dir = base / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{year}" if month is None else f"{year}-{month:02d}"
    return exports_dir / f"belege_{stem}.zip"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Belege as ZIP with index CSV")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, choices=range(1, 13),
                        help="If omitted, exports the full year")
    parser.add_argument("--out", help="Output ZIP path (default: exports/belege_<period>.zip)")
    parser.add_argument(
        "--customer",
        default=os.environ.get("AP_LEDGER_CUSTOMER_NAME"),
        help="Mandant name in README (default: $AP_LEDGER_CUSTOMER_NAME)",
    )
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    try:
        store = get_store(args.db_path)
        if args.month:
            invoices = store.monthly_invoices(args.year, args.month)
        else:
            invoices = store.annual_invoices(args.year)

        out_path = Path(args.out) if args.out else default_output_path(args.year, args.month)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        missing = 0
        with_file = 0
        added_paths: set[str] = set()

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for inv in invoices:
                source = inv.get("source_file") or ""
                if not source:
                    missing += 1
                    continue
                src_path = Path(source)
                if not src_path.exists():
                    missing += 1
                    continue

                zip_path = normalize_in_zip_path(source, args.year)
                if zip_path in added_paths:
                    with_file += 1
                    continue
                zf.write(src_path, zip_path)
                added_paths.add(zip_path)
                with_file += 1

            stats = {
                "total": len(invoices),
                "with_file": with_file,
                "missing": missing,
            }
            zf.writestr("belegverzeichnis.csv", build_index_csv(invoices, args.year))
            zf.writestr("README.txt", build_readme(args.year, args.month, args.customer, stats))

        output({
            "success": True,
            "path": str(out_path),
            "year": args.year,
            "month": args.month,
            "invoice_count": len(invoices),
            "files_included": with_file,
            "files_missing": missing,
        })
    except Exception as exc:
        error(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
