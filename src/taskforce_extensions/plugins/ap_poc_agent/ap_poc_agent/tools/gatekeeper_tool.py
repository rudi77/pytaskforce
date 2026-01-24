"""Gatekeeper tool for invoice extraction and compliance checks."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from ap_poc_agent.tools.data_loader import load_json_file


class GatekeeperTool:
    """Extract structured invoice data and validate §14 UStG fields."""

    @property
    def name(self) -> str:
        """Return tool name."""
        return "gatekeeper_extract_invoice"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Extract key invoice fields from a JSON invoice payload or file. "
            "Performs a §14 UStG compliance check and returns missing fields."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "invoice_path": {
                    "type": "string",
                    "description": "Path to JSON invoice file",
                },
                "invoice_payload": {
                    "type": "object",
                    "description": "Invoice payload as JSON object",
                },
                "ocr_text": {
                    "type": "string",
                    "description": "Raw OCR text extracted from the invoice",
                },
                "ocr_blocks": {
                    "type": "array",
                    "description": "OCR blocks with text fields",
                    "items": {"type": "object"},
                },
            },
            "anyOf": [
                {"required": ["invoice_path"]},
                {"required": ["invoice_payload"]},
                {"required": ["ocr_text"]},
                {"required": ["ocr_blocks"]},
            ],
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        has_path = "invoice_path" in kwargs
        has_payload = "invoice_payload" in kwargs
        has_ocr_text = "ocr_text" in kwargs
        has_ocr_blocks = "ocr_blocks" in kwargs
        if not any([has_path, has_payload, has_ocr_text, has_ocr_blocks]):
            return False, "invoice_path, invoice_payload, ocr_text, or ocr_blocks is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Extract invoice fields and check compliance."""
        try:
            payload = _resolve_invoice_payload(kwargs)
        except (FileNotFoundError, ImportError, ValueError) as error:
            return _error_result(error)

        extracted = _extract_fields(payload)
        missing_fields = _missing_required_fields(extracted)

        return {
            "success": True,
            "invoice_data": extracted,
            "missing_fields": missing_fields,
            "compliant": not missing_fields,
        }


def _resolve_invoice_payload(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Resolve invoice payload from kwargs."""
    if "invoice_payload" in kwargs:
        if not isinstance(kwargs["invoice_payload"], dict):
            raise ValueError("invoice_payload must be an object")
        return kwargs["invoice_payload"]
    if "ocr_text" in kwargs or "ocr_blocks" in kwargs:
        return _payload_from_ocr(
            kwargs.get("ocr_text"),
            kwargs.get("ocr_blocks"),
        )
    invoice_path = str(kwargs["invoice_path"])
    if _is_json_path(invoice_path):
        return load_json_file(invoice_path)
    return _payload_from_file(invoice_path)


def _extract_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized invoice fields from payload."""
    return {
        "invoice_id": payload.get("invoice_id") or payload.get("invoice_number"),
        "invoice_date": payload.get("invoice_date"),
        "service_date": payload.get("service_date"),
        "supplier_name": payload.get("supplier", {}).get("name"),
        "supplier_address": payload.get("supplier", {}).get("address"),
        "supplier_vat_id": payload.get("supplier", {}).get("vat_id"),
        "supplier_country": payload.get("supplier", {}).get("country"),
        "recipient_name": payload.get("recipient", {}).get("name"),
        "recipient_address": payload.get("recipient", {}).get("address"),
        "currency": payload.get("currency", "EUR"),
        "line_items": payload.get("line_items", []),
        "net_amount": payload.get("totals", {}).get("net_amount"),
        "tax_rate": payload.get("totals", {}).get("tax_rate"),
        "tax_amount": payload.get("totals", {}).get("tax_amount"),
        "total_amount": payload.get("totals", {}).get("total_amount"),
        "description": payload.get("description"),
    }


def _payload_from_ocr(ocr_text: str | None, ocr_blocks: Any) -> dict[str, Any]:
    """Build a minimal invoice payload from OCR output."""
    text = ocr_text or ""
    if not text and isinstance(ocr_blocks, list):
        text = " ".join(
            str(block.get("text", ""))
            for block in ocr_blocks
            if isinstance(block, dict)
        )
    return _parse_invoice_from_text(text)


def _payload_from_file(invoice_path: str) -> dict[str, Any]:
    """Extract OCR payload from a file via the MCP tools."""
    _ensure_mcp_on_path()
    from document_extraction_mcp.tools.ocr import ocr_extract

    ocr_result = ocr_extract(invoice_path)
    if "error" in ocr_result:
        raise ValueError(ocr_result["error"])
    return _payload_from_ocr(
        _join_ocr_regions(ocr_result.get("regions", [])),
        ocr_result.get("regions", []),
    )


def _ensure_mcp_on_path() -> None:
    """Ensure document extraction MCP sources are importable."""
    mcp_path = _find_mcp_src_path()
    if not mcp_path:
        raise ImportError("document-extraction-mcp src path not found")
    if str(mcp_path) not in sys.path:
        sys.path.insert(0, str(mcp_path))


def _find_mcp_src_path() -> Path | None:
    """Locate the document extraction MCP src directory."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "servers" / "document-extraction-mcp" / "src"
        if candidate.exists():
            return candidate
    return None


def _join_ocr_regions(regions: Any) -> str:
    """Join OCR region text into a single string."""
    if not isinstance(regions, list):
        return ""
    return " ".join(
        str(region.get("text", ""))
        for region in regions
        if isinstance(region, dict)
    ).strip()


def _parse_invoice_from_text(text: str) -> dict[str, Any]:
    """Parse basic invoice fields from OCR text."""
    normalized_text = " ".join(text.split())
    invoice_id, invoice_date = _extract_invoice_meta(normalized_text)
    totals = _extract_totals(normalized_text)
    currency = _match_pattern(normalized_text, r"\b(EUR|USD|CHF)\b")

    return {
        "invoice_id": invoice_id,
        "invoice_date": _normalize_date(invoice_date),
        "service_date": None,
        "supplier": {},
        "recipient": {},
        "currency": currency or "EUR",
        "line_items": [],
        "description": "Extracted from OCR text",
        "totals": totals,
    }


def _is_json_path(invoice_path: str) -> bool:
    """Check if the path points to a JSON file."""
    return invoice_path.lower().endswith(".json")


def _extract_invoice_meta(text: str) -> tuple[str | None, str | None]:
    """Extract invoice identifiers and dates."""
    invoice_id = _match_pattern(
        text,
        r"(?:Rechnungsnummer|Rechnungsnr\.?|Rechnung|Invoice)\b\s*[:#]?\s*([A-Z0-9-]+)",
    )
    invoice_date = _match_pattern(
        text,
        r"(?:Rechnungsdatum|Invoice Date)\s*[:#]?\s*([0-9]{2}[./][0-9]{2}[./][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
    )
    return invoice_id, invoice_date


def _extract_totals(text: str) -> dict[str, Any]:
    """Extract total amounts and VAT information."""
    total_amount = _match_pattern(text, r"(?:Gesamt|Brutto|Total)\s*[:#]?\s*([0-9.,]+)")
    net_amount = _match_pattern(text, r"(?:Netto|Net)\s*[:#]?\s*([0-9.,]+)")
    tax_amount = _match_pattern(text, r"(?:MwSt|USt|VAT)\s*[:#]?\s*([0-9.,]+)")
    tax_rate = _match_pattern(text, r"(?:MwSt|USt|VAT)\s*([0-9]{1,2}[.,]?[0-9]?)%?")
    return {
        "net_amount": _parse_amount(net_amount),
        "tax_rate": _parse_amount(tax_rate) / 100 if tax_rate else None,
        "tax_amount": _parse_amount(tax_amount),
        "total_amount": _parse_amount(total_amount),
    }


def _match_pattern(text: str, pattern: str) -> str | None:
    """Return the first regex match group for a pattern."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _parse_amount(value: str | None) -> float | None:
    """Parse common European/US amount formats."""
    if not value:
        return None
    cleaned = value.replace(" ", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_date(value: str | None) -> str | None:
    """Normalize date strings to YYYY-MM-DD when possible."""
    if not value:
        return None
    if "-" in value:
        return value
    parts = value.replace(".", "/").split("/")
    if len(parts) == 3:
        day, month, year = parts
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return value


def _missing_required_fields(extracted: dict[str, Any]) -> list[str]:
    """Return missing mandatory fields per §14 UStG."""
    required_fields = {
        "invoice_id": "Rechnungsnummer",
        "invoice_date": "Rechnungsdatum",
        "supplier_name": "Lieferant",
        "supplier_address": "Lieferantenadresse",
        "supplier_vat_id": "USt-IdNr",
        "recipient_name": "Leistungsempfänger",
        "recipient_address": "Empfängeradresse",
        "service_date": "Leistungsdatum",
        "description": "Leistungsbeschreibung",
        "net_amount": "Nettobetrag",
        "tax_rate": "Steuersatz",
        "tax_amount": "Steuerbetrag",
        "total_amount": "Bruttobetrag",
    }
    missing = []
    for key, label in required_fields.items():
        if not extracted.get(key):
            missing.append(label)
    return missing


def _error_result(error: Exception) -> dict[str, Any]:
    """Format an error result."""
    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
    }
