"""
Invoice Data Extraction Utilities

Common helpers for extracting data from invoice dictionaries with multiple
field name fallbacks. Eliminates code duplication across accounting tools.
"""

from typing import Any
import structlog

logger = structlog.get_logger(__name__)


def _unwrap_invoice_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Unwrap nested invoice_data from tool result format.

    Tool results have format: {"success": True, "invoice_data": {...actual data...}}
    This helper extracts the nested invoice_data if present.

    Args:
        data: Input data (may be tool result or direct invoice data)

    Returns:
        Unwrapped invoice data dictionary
    """
    # Check for nested invoice_data from tool result format
    if "invoice_data" in data and isinstance(data.get("invoice_data"), dict):
        nested = data["invoice_data"]
        logger.info(
            "invoice_utils.unwrapped_nested_data",
            original_keys=list(data.keys())[:5],
            nested_keys=list(nested.keys())[:5] if isinstance(nested, dict) else "not_dict",
        )
        return nested
    return data


def extract_supplier_name(invoice_data: dict[str, Any]) -> str:
    """
    Extract supplier name from invoice data.

    Tries multiple field names for robustness across different data sources.
    Handles nested invoice_data from tool result format.

    Args:
        invoice_data: Invoice data dictionary (may be tool result or direct data)

    Returns:
        Supplier name or empty string if not found
    """
    # Unwrap if nested in tool result
    data = _unwrap_invoice_data(invoice_data)

    return (
        data.get("supplier_name")
        or data.get("vendor_name")
        or data.get("lieferant")
        or data.get("supplier")
        or data.get("vendor")
        or ""
    )


def extract_line_items(invoice_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract line items from invoice data with fallback creation.

    If no line_items array exists, attempts to create one from invoice-level fields.
    Handles nested invoice_data from tool result format.

    Args:
        invoice_data: Invoice data dictionary (may be tool result or direct data)

    Returns:
        List of line item dictionaries (may be empty)
    """
    # Unwrap if nested in tool result
    data = _unwrap_invoice_data(invoice_data)

    line_items = data.get("line_items", [])
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
    Handles nested invoice_data from tool result format.

    Args:
        invoice_data: Invoice data dictionary (may be tool result or direct data)

    Returns:
        Description string or empty string if not found
    """
    # Unwrap if nested in tool result
    data = _unwrap_invoice_data(invoice_data)

    return (
        data.get("description")
        or data.get("position_description")
        or data.get("position")
        or data.get("line_item_description")
        or ""
    )


def extract_net_amount(invoice_data: dict[str, Any]) -> float | None:
    """
    Extract net amount from invoice data.
    Handles nested invoice_data from tool result format.

    Args:
        invoice_data: Invoice data dictionary (may be tool result or direct data)

    Returns:
        Net amount as float or None if not found
    """
    # Unwrap if nested in tool result
    data = _unwrap_invoice_data(invoice_data)

    amount = (
        data.get("total_net")
        or data.get("net_amount")
        or data.get("nettobetrag")
        or data.get("amount")
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
    Handles nested invoice_data from tool result format.

    Args:
        invoice_data: Invoice data dictionary (may be tool result or direct data)
        default: Default VAT rate if not found (default: 0.19 = 19%)

    Returns:
        VAT rate as float
    """
    # Unwrap if nested in tool result
    data = _unwrap_invoice_data(invoice_data)

    rate = data.get("vat_rate")
    if rate is not None:
        try:
            return float(rate)
        except (ValueError, TypeError):
            return default
    return default


def extract_vat_amount(invoice_data: dict[str, Any]) -> float | None:
    """
    Extract VAT amount from invoice data.
    Handles nested invoice_data from tool result format.

    Args:
        invoice_data: Invoice data dictionary (may be tool result or direct data)

    Returns:
        VAT amount as float or None if not found
    """
    # Unwrap if nested in tool result
    data = _unwrap_invoice_data(invoice_data)

    amount = data.get("total_vat") or data.get("vat_amount")
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
