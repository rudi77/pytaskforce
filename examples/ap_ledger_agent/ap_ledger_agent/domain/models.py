"""Domain models for the AP Ledger Agent.

Pure Python dataclasses — no external dependencies, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    POSTED = "posted"
    REJECTED = "rejected"


class InvoiceType(str, Enum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CREDIT_NOTE = "credit_note"


class JournalStatus(str, Enum):
    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


class CategoryType(str, Enum):
    EXPENSE = "expense"
    REVENUE = "revenue"


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaxCode:
    """Österreichischer Steuersatz."""

    code: str  # z.B. 'AT_20'
    rate: Decimal  # 0.20
    label: str  # '20% USt'
    description: str = ""


@dataclass(frozen=True)
class Category:
    """Einnahmen-/Ausgabenkategorie."""

    code: str  # z.B. 'waren_farbe'
    name: str  # 'Haarfarben & Chemie'
    type: CategoryType
    description: str = ""
    tax_deductible: bool = True
    default_tax_code: Optional[str] = None


@dataclass(frozen=True)
class FiscalPeriod:
    """Geschäftsperiode (Monat)."""

    id: int
    year: int
    month: int
    label: str  # 'Jänner 2025'
    start_date: str
    end_date: str
    is_closed: bool = False


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass
class Vendor:
    """Lieferant / Geschäftspartner."""

    id: Optional[int] = None
    name: str = ""
    name_normalized: str = ""
    uid_number: Optional[str] = None
    address: Optional[str] = None
    default_category_code: Optional[str] = None
    default_tax_code: Optional[str] = None
    match_keywords: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class InvoiceLine:
    """Belegposition."""

    position: int = 1
    description: str = ""
    quantity: Decimal = Decimal("1")
    unit_price: Optional[Decimal] = None
    net_amount: Decimal = Decimal("0")
    tax_code: Optional[str] = None
    tax_amount: Optional[Decimal] = None
    gross_amount: Decimal = Decimal("0")
    category_code: Optional[str] = None


@dataclass
class Invoice:
    """Beleg (Rechnung, Kassenbon, Gutschrift)."""

    id: Optional[int] = None
    external_ref: Optional[str] = None
    vendor_id: Optional[int] = None
    vendor_name_raw: str = ""
    invoice_date: str = ""  # YYYY-MM-DD
    due_date: Optional[str] = None
    total_gross: Decimal = Decimal("0")
    total_net: Optional[Decimal] = None
    total_tax: Optional[Decimal] = None
    currency: str = "EUR"
    type: InvoiceType = InvoiceType.INVOICE
    status: InvoiceStatus = InvoiceStatus.DRAFT
    source_file: Optional[str] = None
    source_type: Optional[str] = None  # 'photo', 'pdf', 'manual'
    extraction_confidence: Optional[float] = None
    fiscal_period_id: Optional[int] = None
    notes: Optional[str] = None
    lines: list[InvoiceLine] = field(default_factory=list)


@dataclass
class JournalLine:
    """Buchungszeile (Soll oder Haben)."""

    line_number: int = 1
    account_code: str = ""
    account_name: str = ""
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    tax_code: Optional[str] = None
    description: Optional[str] = None


@dataclass
class JournalEntry:
    """Buchungssatz (Journal Entry)."""

    id: Optional[int] = None
    invoice_id: Optional[int] = None
    entry_date: str = ""  # YYYY-MM-DD
    description: str = ""
    status: JournalStatus = JournalStatus.DRAFT
    fiscal_period_id: Optional[int] = None
    posted_at: Optional[str] = None
    posted_by: Optional[str] = None
    lines: list[JournalLine] = field(default_factory=list)

    def is_balanced(self) -> bool:
        """Prüft ob Soll = Haben."""
        total_debit = sum(l.debit_amount for l in self.lines)
        total_credit = sum(l.credit_amount for l in self.lines)
        return abs(total_debit - total_credit) < Decimal("0.01")


@dataclass(frozen=True)
class AuditEntry:
    """Audit-Log Eintrag (unveränderlich)."""

    id: Optional[int] = None
    event_type: str = ""
    entity_type: str = ""
    entity_id: int = 0
    actor: str = "system"
    details: str = "{}"
    created_at: Optional[str] = None
