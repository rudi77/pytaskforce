"""SQLite persistence layer for the AP Ledger Agent.

Manages the database connection, initialization, and provides
typed query helpers used by the Taskforce tools.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from ap_ledger_agent.domain.models import (
    Category,
    CategoryType,
    FiscalPeriod,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    InvoiceType,
    JournalEntry,
    JournalLine,
    JournalStatus,
    TaxCode,
    Vendor,
)

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent
_SCHEMA_PATH = _PLUGIN_DIR / "db" / "schema.sql"
_SEED_PATH = _PLUGIN_DIR / "db" / "seed-data.sql"


class SQLiteStore:
    """Thread-safe SQLite store for AP Ledger data.

    Each method opens its own connection to remain safe across
    async tool invocations.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def ensure_initialized(self) -> None:
        """Create schema and seed data if the DB does not exist."""
        if self.db_path.exists():
            return
        logger.info("Initializing AP Ledger database at %s", self.db_path)
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.executescript(_SEED_PATH.read_text(encoding="utf-8"))
            logger.info("Database initialized successfully.")
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Vendor operations
    # ------------------------------------------------------------------

    def resolve_vendor(self, name: str) -> list[Vendor]:
        """Find vendors matching *name* (exact → LIKE → keyword)."""
        normalized = name.strip().lower()
        conn = self._connect()
        try:
            # 1. Exact match
            rows = conn.execute(
                "SELECT * FROM vendors WHERE name_normalized = ? LIMIT 1",
                (normalized,),
            ).fetchall()
            if rows:
                return [self._row_to_vendor(r) for r in rows]

            # 2. LIKE
            rows = conn.execute(
                "SELECT * FROM vendors WHERE name_normalized LIKE ? "
                "OR ? LIKE '%' || name_normalized || '%' LIMIT 3",
                (f"%{normalized}%", normalized),
            ).fetchall()
            if rows:
                return [self._row_to_vendor(r) for r in rows]

            # 3. Keyword search
            all_vendors = conn.execute("SELECT * FROM vendors WHERE match_keywords IS NOT NULL").fetchall()
            matches = []
            for row in all_vendors:
                keywords = (row["match_keywords"] or "").split(",")
                for kw in keywords:
                    if kw.strip().lower() in normalized or normalized in kw.strip().lower():
                        matches.append(self._row_to_vendor(row))
                        break
            return matches[:3]
        finally:
            conn.close()

    def create_vendor(
        self,
        name: str,
        category_code: str | None = None,
        tax_code: str = "AT_20",
        keywords: str | None = None,
    ) -> Vendor:
        """Create a new vendor and return it."""
        normalized = name.strip().lower()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO vendors (name, name_normalized, default_category_code, "
                "default_tax_code, match_keywords) VALUES (?, ?, ?, ?, ?)",
                (name, normalized, category_code, tax_code, keywords),
            )
            conn.commit()
            vendor_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return Vendor(
                id=vendor_id,
                name=name,
                name_normalized=normalized,
                default_category_code=category_code,
                default_tax_code=tax_code,
                match_keywords=keywords,
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Fiscal period operations
    # ------------------------------------------------------------------

    def resolve_period(self, date_str: str) -> FiscalPeriod:
        """Find or create the fiscal period for a given date (YYYY-MM-DD)."""
        year = int(date_str[:4])
        month = int(date_str[5:7])
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM fiscal_periods WHERE year = ? AND month = ? LIMIT 1",
                (year, month),
            ).fetchone()
            if row:
                return self._row_to_period(row)

            # Auto-create
            label = f"{self._month_name(month)} {year}"
            start = f"{year}-{month:02d}-01"
            if month == 12:
                end = f"{year}-12-31"
            else:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                end = f"{year}-{month:02d}-{last_day}"

            conn.execute(
                "INSERT INTO fiscal_periods (year, month, label, start_date, end_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (year, month, label, start, end),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM fiscal_periods WHERE year = ? AND month = ? LIMIT 1",
                (year, month),
            ).fetchone()
            return self._row_to_period(row)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Tax code operations
    # ------------------------------------------------------------------

    def resolve_tax(self, code: str) -> Optional[TaxCode]:
        """Resolve a tax code."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT code, rate, label, description FROM tax_codes "
                "WHERE code = ? AND (valid_to IS NULL OR valid_to >= date('now')) LIMIT 1",
                (code,),
            ).fetchone()
            if not row:
                return None
            return TaxCode(
                code=row["code"],
                rate=Decimal(str(row["rate"])),
                label=row["label"],
                description=row["description"] or "",
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Category operations
    # ------------------------------------------------------------------

    def list_categories(self) -> list[Category]:
        """Return all categories ordered by sort_order."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT code, name, type, description, tax_deductible, "
                "default_tax_code FROM categories ORDER BY sort_order"
            ).fetchall()
            return [
                Category(
                    code=r["code"],
                    name=r["name"],
                    type=CategoryType(r["type"]),
                    description=r["description"] or "",
                    tax_deductible=bool(r["tax_deductible"]),
                    default_tax_code=r["default_tax_code"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Invoice operations
    # ------------------------------------------------------------------

    def persist_invoice(self, invoice: Invoice) -> int:
        """Save an invoice with its lines. Returns the invoice ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN TRANSACTION")
            conn.execute(
                "INSERT INTO invoices ("
                "  external_ref, vendor_id, vendor_name_raw, invoice_date, due_date,"
                "  total_gross, total_net, total_tax, type, status,"
                "  source_file, source_type, extraction_confidence,"
                "  fiscal_period_id, notes"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    invoice.external_ref,
                    invoice.vendor_id,
                    invoice.vendor_name_raw,
                    invoice.invoice_date,
                    invoice.due_date,
                    str(invoice.total_gross),
                    str(invoice.total_net) if invoice.total_net else None,
                    str(invoice.total_tax) if invoice.total_tax else None,
                    invoice.type.value,
                    invoice.status.value,
                    invoice.source_file,
                    invoice.source_type,
                    invoice.extraction_confidence,
                    invoice.fiscal_period_id,
                    invoice.notes,
                ),
            )
            invoice_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for line in invoice.lines:
                conn.execute(
                    "INSERT INTO invoice_lines ("
                    "  invoice_id, position, description, quantity, unit_price,"
                    "  net_amount, tax_code, tax_amount, gross_amount, category_code"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        invoice_id,
                        line.position,
                        line.description,
                        str(line.quantity),
                        str(line.unit_price) if line.unit_price else None,
                        str(line.net_amount),
                        line.tax_code,
                        str(line.tax_amount) if line.tax_amount else None,
                        str(line.gross_amount),
                        line.category_code,
                    ),
                )

            conn.commit()
            return invoice_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def find_duplicate(
        self, vendor_name: str, date: str, amount: Decimal
    ) -> list[dict[str, Any]]:
        """Check for possible duplicate invoices."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, vendor_name_raw, invoice_date, total_gross "
                "FROM invoices "
                "WHERE vendor_name_raw LIKE ? AND invoice_date = ? "
                "AND ABS(total_gross - ?) < 0.01",
                (f"%{vendor_name}%", date, str(amount)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Journal operations
    # ------------------------------------------------------------------

    def persist_journal(self, entry: JournalEntry) -> int:
        """Save a journal entry with its lines. Returns the journal ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN TRANSACTION")
            conn.execute(
                "INSERT INTO journal_entries ("
                "  invoice_id, entry_date, description, status, fiscal_period_id"
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    entry.invoice_id,
                    entry.entry_date,
                    entry.description,
                    entry.status.value,
                    entry.fiscal_period_id,
                ),
            )
            journal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for line in entry.lines:
                conn.execute(
                    "INSERT INTO journal_lines ("
                    "  journal_entry_id, line_number, account_code, account_name,"
                    "  debit_amount, credit_amount, tax_code, description"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        journal_id,
                        line.line_number,
                        line.account_code,
                        line.account_name,
                        str(line.debit_amount),
                        str(line.credit_amount),
                        line.tax_code,
                        line.description,
                    ),
                )

            conn.commit()
            return journal_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def post_journal(self, journal_id: int) -> dict[str, Any]:
        """Transition journal entry from draft to posted."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT status, invoice_id FROM journal_entries WHERE id = ?",
                (journal_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Journal Entry {journal_id} not found")
            if row["status"] != "draft":
                raise ValueError(
                    f"Journal Entry {journal_id} is '{row['status']}', expected 'draft'"
                )

            # Balance check
            bal = conn.execute(
                "SELECT ROUND(SUM(debit_amount), 2) as d, "
                "ROUND(SUM(credit_amount), 2) as c "
                "FROM journal_lines WHERE journal_entry_id = ?",
                (journal_id,),
            ).fetchone()
            if abs((bal["d"] or 0) - (bal["c"] or 0)) > 0.01:
                raise ValueError(
                    f"Unbalanced: Soll={bal['d']}, Haben={bal['c']}"
                )

            conn.execute(
                "UPDATE journal_entries SET status = 'posted', "
                "posted_at = datetime('now'), posted_by = 'agent' "
                "WHERE id = ?",
                (journal_id,),
            )
            if row["invoice_id"]:
                conn.execute(
                    "UPDATE invoices SET status = 'posted', "
                    "updated_at = datetime('now') WHERE id = ?",
                    (row["invoice_id"],),
                )
            conn.commit()

            posted = conn.execute(
                "SELECT je.id, je.entry_date, je.description, je.status, "
                "je.posted_at, i.vendor_name_raw, i.total_gross "
                "FROM journal_entries je "
                "LEFT JOIN invoices i ON i.id = je.invoice_id "
                "WHERE je.id = ?",
                (journal_id,),
            ).fetchone()
            return dict(posted)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def write_audit(
        self,
        event_type: str,
        entity_type: str,
        entity_id: int,
        actor: str = "system",
        details: str = "{}",
    ) -> int:
        """Write an immutable audit log entry. Returns the audit ID."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO audit_log (event_type, entity_type, entity_id, actor, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (event_type, entity_type, entity_id, actor, details),
            )
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def monthly_totals(self, year: int | None = None) -> list[dict[str, Any]]:
        """Return monthly EÜR totals."""
        conn = self._connect()
        try:
            query = "SELECT * FROM v_monthly_totals"
            params: tuple = ()
            if year:
                query += " WHERE year = ?"
                params = (year,)
            query += " ORDER BY year DESC, month DESC"
            return [dict(r) for r in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    def euer_summary(self, year: int) -> list[dict[str, Any]]:
        """Return EÜR category breakdown for a year."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM v_euer_summary WHERE year = ? "
                "ORDER BY month, category_type DESC",
                (year,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def export_csv(self, year: int) -> str:
        """Generate CSV content for a year (for the Steuerberater)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT i.invoice_date, v.name as lieferant, c.name as kategorie,"
                "  il.net_amount as netto, il.tax_amount as ust,"
                "  il.gross_amount as brutto, tc.label as steuersatz "
                "FROM invoices i "
                "JOIN invoice_lines il ON il.invoice_id = i.id "
                "LEFT JOIN vendors v ON v.id = i.vendor_id "
                "LEFT JOIN categories c ON c.code = il.category_code "
                "LEFT JOIN tax_codes tc ON tc.code = il.tax_code "
                "WHERE i.status = 'posted' AND CAST(strftime('%%Y', i.invoice_date) AS INTEGER) = ? "
                "ORDER BY i.invoice_date",
                (year,),
            ).fetchall()

            if not rows:
                return ""

            headers = "datum,lieferant,kategorie,netto,ust,brutto,steuersatz"
            lines = [headers]
            for r in rows:
                line = ",".join(
                    f'"{v}"' if isinstance(v, str) and "," in v else str(v or "")
                    for v in [
                        r["invoice_date"],
                        r["lieferant"],
                        r["kategorie"],
                        r["netto"],
                        r["ust"],
                        r["brutto"],
                        r["steuersatz"],
                    ]
                )
                lines.append(line)
            return "\n".join(lines)
        finally:
            conn.close()

    def open_invoices(self) -> list[dict[str, Any]]:
        """Return invoices in draft/validated status."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, vendor_name_raw, invoice_date, total_gross, status "
                "FROM invoices WHERE status IN ('draft', 'validated') "
                "ORDER BY invoice_date DESC LIMIT 20"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _row_to_vendor(row: sqlite3.Row) -> Vendor:
        return Vendor(
            id=row["id"],
            name=row["name"],
            name_normalized=row["name_normalized"],
            uid_number=row["uid_number"] if "uid_number" in row.keys() else None,
            address=row["address"] if "address" in row.keys() else None,
            default_category_code=row["default_category_code"],
            default_tax_code=row["default_tax_code"],
            match_keywords=row["match_keywords"] if "match_keywords" in row.keys() else None,
        )

    @staticmethod
    def _row_to_period(row: sqlite3.Row) -> FiscalPeriod:
        return FiscalPeriod(
            id=row["id"],
            year=row["year"],
            month=row["month"],
            label=row["label"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            is_closed=bool(row["is_closed"]),
        )

    @staticmethod
    def _month_name(month: int) -> str:
        names = [
            "", "Jänner", "Februar", "März", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember",
        ]
        return names[month] if 1 <= month <= 12 else f"Monat {month}"
