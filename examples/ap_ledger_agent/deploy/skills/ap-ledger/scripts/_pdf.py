"""Shared PDF helpers for AP-Ledger report scripts.

Provides brand colors, paragraph styles, money/date formatting,
and localized month names for AT/DE reports.
"""

from __future__ import annotations

from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

ACCENT = colors.HexColor("#1e40af")
TEXT_DARK = colors.HexColor("#0f172a")
TEXT_MUTED = colors.HexColor("#64748b")
BG_ROW_ALT = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#cbd5e1")

MONTH_NAMES = {
    "AT": [
        "", "Jänner", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ],
    "DE": [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ],
}


def month_name(country: str, month: int) -> str:
    names = MONTH_NAMES.get((country or "AT").upper(), MONTH_NAMES["AT"])
    return names[month] if 1 <= month <= 12 else f"Monat {month}"


def fmt_money(value: float | Decimal | int | None) -> str:
    """Format as German-style currency string (1.234,56 €). Returns em dash for None."""
    if value is None:
        return "—"
    formatted = f"{Decimal(str(value)):,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def build_styles() -> dict:
    """Return a dict of reusable paragraph styles."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontSize=22, textColor=TEXT_DARK,
            alignment=0, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontSize=12, textColor=TEXT_MUTED,
            spaceAfter=20,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontSize=14, textColor=ACCENT,
            spaceBefore=16, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontSize=10, textColor=TEXT_DARK,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"], fontSize=9, textColor=TEXT_MUTED,
        ),
        "footer": ParagraphStyle(
            "Footer", parent=base["Normal"], fontSize=8, textColor=TEXT_MUTED,
            alignment=2,
        ),
    }
