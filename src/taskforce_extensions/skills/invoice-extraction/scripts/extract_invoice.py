#!/usr/bin/env python3
"""Extract structured invoice data from PDF/image documents.

This script performs OCR extraction and parses invoice fields into
a structured JSON format with §14 UStG compliance validation.

Usage:
    python extract_invoice.py /path/to/invoice.pdf
    python extract_invoice.py /path/to/invoice.pdf --output invoice_data.json

Output:
    JSON with invoice_data, missing_fields, and compliant status.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def find_mcp_src_path() -> Path | None:
    """Locate the document extraction MCP src directory."""
    # Try relative to this script
    script_dir = Path(__file__).resolve().parent
    for parent in script_dir.parents:
        candidate = parent / "servers" / "document-extraction-mcp" / "src"
        if candidate.exists():
            return candidate
    # Try from current working directory
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / "servers" / "document-extraction-mcp" / "src"
        if candidate.exists():
            return candidate
    return None


def ensure_mcp_importable() -> None:
    """Ensure document extraction MCP sources are importable."""
    mcp_path = find_mcp_src_path()
    if not mcp_path:
        raise ImportError(
            "document-extraction-mcp src path not found. "
            "Ensure you're running from the pytaskforce project directory."
        )
    if str(mcp_path) not in sys.path:
        sys.path.insert(0, str(mcp_path))


def run_ocr(image_path: str) -> dict[str, Any]:
    """Run OCR extraction on an image or PDF.

    Args:
        image_path: Path to the input file.

    Returns:
        OCR result with regions containing text and bounding boxes.
    """
    ensure_mcp_importable()
    from document_extraction_mcp.tools.ocr import ocr_extract

    return ocr_extract(image_path)


def join_ocr_regions(regions: list[dict]) -> str:
    """Join OCR region text into a single string."""
    if not regions:
        return ""
    return " ".join(
        str(region.get("text", ""))
        for region in regions
        if isinstance(region, dict)
    ).strip()


def match_pattern(text: str, pattern: str) -> str | None:
    """Return the first regex match group for a pattern."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def parse_amount(value: str | None) -> float | None:
    """Parse common European/US amount formats."""
    if not value:
        return None
    cleaned = value.replace(" ", "")
    # Handle European format (1.234,56) vs US format (1,234.56)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            # European: 1.234,56 -> 1234.56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: 1,234.56 -> 1234.56
            cleaned = cleaned.replace(",", "")
    else:
        # Single separator - assume comma is decimal for European
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_date(value: str | None) -> str | None:
    """Normalize date strings to YYYY-MM-DD format."""
    if not value:
        return None
    if "-" in value and len(value) == 10:
        return value  # Already ISO format
    # Handle DD.MM.YYYY or DD/MM/YYYY
    parts = value.replace(".", "/").split("/")
    if len(parts) == 3:
        day, month, year = parts
        if len(year) == 4:
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return value


def extract_invoice_meta(text: str) -> tuple[str | None, str | None]:
    """Extract invoice number and date from text."""
    # German patterns
    invoice_id = match_pattern(
        text,
        r"(?:Rechnungsnummer|Rechnungsnr\.?|Rechnung\s*(?:Nr\.?)?)\s*[:#]?\s*([A-Z0-9][\w-]*)",
    )
    # Fallback to English
    if not invoice_id:
        invoice_id = match_pattern(
            text,
            r"(?:Invoice\s*(?:No\.?|Number|#)?)\s*[:#]?\s*([A-Z0-9][\w-]*)",
        )

    # Date patterns
    invoice_date = match_pattern(
        text,
        r"(?:Rechnungsdatum|Invoice\s*Date)\s*[:#]?\s*"
        r"([0-9]{2}[./][0-9]{2}[./][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
    )

    return invoice_id, invoice_date


def extract_service_date(text: str) -> str | None:
    """Extract service/delivery date from text."""
    service_date = match_pattern(
        text,
        r"(?:Leistungsdatum|Lieferdatum|Leistungszeitraum|Service\s*Date|Delivery\s*Date)"
        r"\s*[:#]?\s*([0-9]{2}[./][0-9]{2}[./][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
    )
    return normalize_date(service_date)


def extract_vat_id(text: str) -> str | None:
    """Extract VAT ID from text."""
    # German USt-IdNr
    vat_id = match_pattern(
        text,
        r"(?:USt-?IdNr\.?|USt-?ID|UID|VAT\s*(?:No\.?|ID|Number)?)\s*[:#]?\s*"
        r"(DE\d{9}|ATU\d{8}|[A-Z]{2}\d{8,12})",
    )
    return vat_id


def extract_totals(text: str) -> dict[str, Any]:
    """Extract total amounts and VAT information."""
    # Total/Gross amount
    total_amount = match_pattern(
        text,
        r"(?:Gesamt|Brutto|Total|Rechnungsbetrag|Amount\s*Due)\s*[:#]?\s*"
        r"([0-9][0-9.,\s]*)",
    )
    # Net amount
    net_amount = match_pattern(
        text,
        r"(?:Netto|Zwischensumme|Subtotal|Net)\s*[:#]?\s*([0-9][0-9.,\s]*)",
    )
    # Tax amount
    tax_amount = match_pattern(
        text,
        r"(?:MwSt\.?|USt\.?|VAT|Steuer|Tax)\s*[:#]?\s*([0-9][0-9.,\s]*)",
    )
    # Tax rate
    tax_rate = match_pattern(
        text,
        r"(?:MwSt\.?|USt\.?|VAT)\s*(?:[:#]?\s*)?([0-9]{1,2}[.,]?[0-9]?)\s*%",
    )

    return {
        "net_amount": parse_amount(net_amount),
        "tax_rate": parse_amount(tax_rate) / 100 if tax_rate else None,
        "tax_amount": parse_amount(tax_amount),
        "total_amount": parse_amount(total_amount),
    }


def extract_currency(text: str) -> str:
    """Extract currency from text."""
    currency = match_pattern(text, r"\b(EUR|USD|CHF|GBP)\b")
    return currency or "EUR"


def extract_supplier_info(text: str) -> dict[str, Any]:
    """Extract supplier information (best effort)."""
    # This is a simplified extraction - real implementation would need
    # more sophisticated NLP or layout analysis
    vat_id = extract_vat_id(text)
    return {
        "name": None,  # Would need NLP/layout analysis
        "address": None,
        "vat_id": vat_id,
        "country": vat_id[:2] if vat_id and len(vat_id) >= 2 else None,
    }


def parse_invoice_from_text(text: str) -> dict[str, Any]:
    """Parse invoice fields from OCR text.

    Args:
        text: Concatenated OCR text.

    Returns:
        Parsed invoice payload.
    """
    normalized_text = " ".join(text.split())
    invoice_id, invoice_date = extract_invoice_meta(normalized_text)
    service_date = extract_service_date(normalized_text)
    totals = extract_totals(normalized_text)
    currency = extract_currency(normalized_text)
    supplier = extract_supplier_info(normalized_text)

    return {
        "invoice_id": invoice_id,
        "invoice_date": normalize_date(invoice_date),
        "service_date": service_date,
        "supplier": supplier,
        "recipient": {},
        "currency": currency,
        "line_items": [],
        "description": None,
        "totals": totals,
    }


def extract_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize and extract invoice fields from payload."""
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


def check_compliance(extracted: dict[str, Any]) -> list[str]:
    """Check §14 UStG mandatory fields and return missing ones.

    Args:
        extracted: Extracted invoice fields.

    Returns:
        List of missing field labels in German.
    """
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


def extract_invoice(invoice_path: str) -> dict[str, Any]:
    """Extract invoice data from a PDF or image file.

    Args:
        invoice_path: Path to the invoice file.

    Returns:
        Dictionary with invoice_data, missing_fields, and compliant status.
    """
    path = Path(invoice_path)
    if not path.exists():
        return {
            "success": False,
            "error": f"File not found: {invoice_path}",
        }

    # Handle JSON files (pre-extracted data)
    if path.suffix.lower() == ".json":
        try:
            with open(path) as f:
                payload = json.load(f)
            extracted = extract_fields(payload)
            missing = check_compliance(extracted)
            return {
                "success": True,
                "invoice_data": extracted,
                "missing_fields": missing,
                "compliant": len(missing) == 0,
            }
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}

    # Run OCR for PDF/images
    try:
        ocr_result = run_ocr(invoice_path)
    except ImportError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"OCR failed: {e}"}

    if "error" in ocr_result:
        return {"success": False, "error": ocr_result["error"]}

    # Parse OCR results
    regions = ocr_result.get("regions", [])
    text = join_ocr_regions(regions)

    if not text.strip():
        return {
            "success": False,
            "error": "No text extracted from document",
        }

    # Parse invoice fields
    payload = parse_invoice_from_text(text)
    extracted = extract_fields(payload)
    missing = check_compliance(extracted)

    return {
        "success": True,
        "invoice_data": extracted,
        "missing_fields": missing,
        "compliant": len(missing) == 0,
        "ocr_info": {
            "region_count": len(regions),
            "text_length": len(text),
        },
    }


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract structured invoice data from PDF/image documents."
    )
    parser.add_argument(
        "invoice_path",
        help="Path to the invoice file (PDF, PNG, JPG, or JSON)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    args = parser.parse_args()

    result = extract_invoice(args.invoice_path)

    indent = 2 if args.pretty else None
    output = json.dumps(result, indent=indent, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Exit with error code if extraction failed
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
