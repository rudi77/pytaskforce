"""
Invoice Data Extraction Utilities

Common helpers for extracting data from invoice dictionaries with multiple
field name fallbacks. Eliminates code duplication across accounting tools.
"""

from typing import Any


def extract_supplier_name(invoice_data: dict[str, Any]) -> str:
    """
    Extract supplier name from invoice data.

    Tries multiple field names for robustness across different data sources.

    Args:
        invoice_data: Invoice data dictionary

    Returns:
        Supplier name or empty string if not found
    """
    return (
        invoice_data.get("supplier_name")
        or invoice_data.get("vendor_name")
        or invoice_data.get("lieferant")
        or invoice_data.get("supplier")
        or invoice_data.get("vendor")
        or ""
    )


def extract_line_items(invoice_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract line items from invoice data with fallback creation.

    If no line_items array exists, attempts to create one from invoice-level fields.

    Args:
        invoice_data: Invoice data dictionary

    Returns:
        List of line item dictionaries (may be empty)
    """
    line_items = invoice_data.get("line_items", [])
    if line_items:
        return line_items

    # Fallback: create line_items from invoice-level fields
    description = extract_description(invoice_data)
    if description:
        return [{"description": description}]

    return []


def extract_description(invoice_data: dict[str, Any]) -> str:
    """
    Extract description from invoice data.

    Tries multiple field names for robustness.

    Args:
        invoice_data: Invoice data dictionary

    Returns:
        Description string or empty string if not found
    """
    return (
        invoice_data.get("description")
        or invoice_data.get("position_description")
        or invoice_data.get("position")
        or invoice_data.get("line_item_description")
        or ""
    )


def extract_net_amount(invoice_data: dict[str, Any]) -> float | None:
    """
    Extract net amount from invoice data.

    Args:
        invoice_data: Invoice data dictionary

    Returns:
        Net amount as float or None if not found
    """
    amount = (
        invoice_data.get("total_net")
        or invoice_data.get("net_amount")
        or invoice_data.get("nettobetrag")
        or invoice_data.get("amount")
    )
    if amount is not None:
        try:
            return float(amount)
        except (ValueError, TypeError):
            return None
    return None


def extract_vat_rate(invoice_data: dict[str, Any], default: float = 0.19) -> float:
    """
    Extract VAT rate from invoice data.

    Args:
        invoice_data: Invoice data dictionary
        default: Default VAT rate if not found (default: 0.19 = 19%)

    Returns:
        VAT rate as float
    """
    rate = invoice_data.get("vat_rate")
    if rate is not None:
        try:
            return float(rate)
        except (ValueError, TypeError):
            return default
    return default


def extract_vat_amount(invoice_data: dict[str, Any]) -> float | None:
    """
    Extract VAT amount from invoice data.

    Args:
        invoice_data: Invoice data dictionary

    Returns:
        VAT amount as float or None if not found
    """
    amount = invoice_data.get("total_vat") or invoice_data.get("vat_amount")
    if amount is not None:
        try:
            return float(amount)
        except (ValueError, TypeError):
            return None
    return None


# Constants for rule creation
AUTO_RULE_PRIORITY = 75
HITL_RULE_PRIORITY = 90
MAX_ITEM_PATTERNS = 5
MAX_PATTERN_LENGTH = 50
MIN_PATTERN_LENGTH = 3
