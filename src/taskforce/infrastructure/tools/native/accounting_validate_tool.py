"""
Compliance validation tool for German invoice requirements.

Validates invoices against §14 UStG (Umsatzsteuergesetz) mandatory fields
(Pflichtangaben). Also handles Kleinbetragsrechnung (§33 UStDV) for
invoices under 250 EUR.

Adapted from examples/accounting_agent for use as a native BaseTool.
"""

from __future__ import annotations

import re
from typing import Any

from taskforce.infrastructure.tools.base_tool import BaseTool


def _normalize_vat_id(raw: str | None) -> str | None:
    """Normalize VAT ID by removing prefixes and whitespace.

    Examples:
        "USt-IDNr. DE 99999999" -> "DE99999999"
        "UID ATU12345678" -> "ATU12345678"
        "12/345/67890" -> "12/345/67890" (German tax number)
    """
    if not raw:
        return None
    s = str(raw).strip()

    # Remove common prefixes (USt-ID, USt-IdNr., VAT ID, UID, etc.)
    s = re.sub(r"(?i)\b(ust[-\s]?id(nr)?\.?|vat\s?id\.?|uid)\b[:\s]*", "", s).strip()

    # Remove all whitespace
    s = re.sub(r"\s+", "", s)

    # Extract EU VAT-ID candidate (e.g., DE99999999, ATU12345678)
    m = re.search(r"\b[A-Z]{2}[0-9A-Za-z+*.]{2,12}\b", s)
    if m:
        return m.group(0)

    # German tax number fallback (e.g., 12/345/67890)
    m = re.search(r"\b\d{2,3}/\d{3}/\d{5}\b", s)
    if m:
        return m.group(0)

    return s


# §14 Abs. 4 UStG mandatory fields
_MANDATORY_FIELDS: dict[str, dict[str, str]] = {
    "supplier_name": {
        "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
        "description": "Name und Anschrift des leistenden Unternehmers",
        "severity": "error",
    },
    "supplier_address": {
        "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
        "description": "Anschrift des leistenden Unternehmers",
        "severity": "error",
    },
    "recipient_name": {
        "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
        "description": "Name und Anschrift des Leistungsempfängers",
        "severity": "error",
    },
    "vat_id": {
        "legal_ref": "§14 Abs. 4 Nr. 2 UStG",
        "description": "Steuernummer oder USt-IdNr. des Lieferanten",
        "severity": "error",
    },
    "invoice_date": {
        "legal_ref": "§14 Abs. 4 Nr. 3 UStG",
        "description": "Ausstellungsdatum der Rechnung",
        "severity": "error",
    },
    "invoice_number": {
        "legal_ref": "§14 Abs. 4 Nr. 4 UStG",
        "description": "Fortlaufende Rechnungsnummer",
        "severity": "error",
    },
    "quantity_description": {
        "legal_ref": "§14 Abs. 4 Nr. 5 UStG",
        "description": "Menge und Art der Lieferung/Leistung",
        "severity": "error",
    },
    "delivery_date": {
        "legal_ref": "§14 Abs. 4 Nr. 6 UStG",
        "description": "Zeitpunkt der Lieferung/Leistung",
        "severity": "warning",
    },
    "net_amount": {
        "legal_ref": "§14 Abs. 4 Nr. 7 UStG",
        "description": "Entgelt (Nettobetrag)",
        "severity": "error",
    },
    "vat_rate": {
        "legal_ref": "§14 Abs. 4 Nr. 8 UStG",
        "description": "Anzuwendender Steuersatz",
        "severity": "error",
    },
    "vat_amount": {
        "legal_ref": "§14 Abs. 4 Nr. 8 UStG",
        "description": "Auf das Entgelt entfallender Steuerbetrag",
        "severity": "error",
    },
}

# Reduced requirements for Kleinbetragsrechnung (§33 UStDV)
_SMALL_INVOICE_THRESHOLD = 250.0
_SMALL_INVOICE_REQUIRED = {
    "supplier_name",
    "invoice_date",
    "quantity_description",
    "gross_amount",
    "vat_rate",
}


def _map_invoice_fields(invoice_data: dict[str, Any]) -> dict[str, Any]:
    """Map common extraction field names to compliance field names.

    Handles alternative field names from different extraction tools
    (e.g. total_net -> net_amount, sender_name -> supplier_name).
    """
    data = invoice_data.copy()

    # Amount mappings
    if "net_amount" not in data:
        data["net_amount"] = data.get("total_net")
    if "gross_amount" not in data:
        data["gross_amount"] = data.get("total_gross")
    if "vat_amount" not in data:
        data["vat_amount"] = data.get("total_vat")

    # VAT ID mapping and normalization
    if "vat_id" not in data:
        data["vat_id"] = data.get("supplier_vat_id")
    data["vat_id"] = _normalize_vat_id(data.get("vat_id"))

    # Supplier name fallback
    if "supplier_name" not in data and "sender_name" in data:
        data["supplier_name"] = data["sender_name"]

    # Derive quantity_description from line_items
    if "quantity_description" not in data:
        line_items = data.get("line_items", [])
        if isinstance(line_items, list) and line_items:
            descs = ", ".join(str(i.get("description", "")) for i in line_items[:3])
            data["quantity_description"] = f"Positionen: {descs}"

    # Derive vat_rate from vat_breakdown
    if not data.get("vat_rate"):
        vb = data.get("vat_breakdown") or []
        if isinstance(vb, list) and vb:
            rates = []
            for item in vb:
                r = item.get("rate")
                if r is not None:
                    rates.append(float(r))
            if rates:
                data["vat_rate"] = ",".join(str(r) for r in sorted(set(rates)))

    return data


def _check_vat_consistency(
    data: dict[str, Any],
) -> list[dict[str, str]]:
    """Check VAT amount consistency against net amount and rate."""
    warnings: list[dict[str, str]] = []
    net = float(data.get("net_amount", 0) or 0)
    vat = float(data.get("vat_amount", 0) or 0)

    vb = data.get("vat_breakdown") or []

    if isinstance(vb, list) and vb:
        # Multi-rate via vat_breakdown
        expected_vat = 0.0
        for item in vb:
            item_net = float(item.get("net_amount", 0) or 0)
            item_rate = float(item.get("rate", 0) or 0)
            expected_vat += item_net * item_rate

        if abs(expected_vat - vat) > 0.05:
            warnings.append(
                {
                    "field": "vat_calculation",
                    "message": (
                        f"MwSt-Check (multi-rate): {vat:.2f} (Ist) " f"vs {expected_vat:.2f} (Soll)"
                    ),
                    "legal_reference": "§14 Abs. 4 Nr. 8 UStG",
                }
            )
    else:
        # Single-rate fallback
        rate = 0.0
        rate_str = str(data.get("vat_rate", "") or "")
        if rate_str and "," not in rate_str:
            try:
                rate = float(rate_str)
            except ValueError:
                pass

        if rate == 0 and data.get("line_items"):
            try:
                rate = float(data["line_items"][0].get("vat_rate", 0))
            except (KeyError, IndexError, TypeError, ValueError):
                pass

        if net > 0 and rate > 0:
            expected_vat = net * rate
            if abs(expected_vat - vat) > 0.05:
                warnings.append(
                    {
                        "field": "vat_calculation",
                        "message": (
                            f"MwSt-Check: {vat:.2f} (Ist) " f"vs {expected_vat:.2f} (Soll)"
                        ),
                        "legal_reference": "§14 Abs. 4 Nr. 8 UStG",
                    }
                )

    return warnings


class AccountingValidateTool(BaseTool):
    """Validate invoice compliance with §14 UStG mandatory fields.

    Checks all Pflichtangaben required by German tax law and returns
    a detailed compliance report. Handles Kleinbetragsrechnung
    (§33 UStDV) with reduced requirements for invoices under 250 EUR.
    """

    tool_name = "accounting_validate"
    tool_description = (
        "Validate invoice data against §14 UStG Pflichtangaben. "
        "Returns compliance status, missing fields, warnings, and "
        "legal references. Also handles Kleinbetragsrechnung (§33 UStDV)."
    )
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "invoice_data": {
                "type": "object",
                "description": (
                    "Structured invoice data. Expected fields: "
                    "supplier_name, supplier_address, vat_id, "
                    "invoice_number, invoice_date, net_amount, "
                    "vat_rate, vat_amount, gross_amount, "
                    "quantity_description, delivery_date, recipient_name. "
                    "Alternative names (total_net, sender_name, etc.) "
                    "are mapped automatically."
                ),
            },
            "strict_mode": {
                "type": "boolean",
                "description": ("If true, warnings are treated as errors. Default: false."),
            },
        },
        "required": ["invoice_data"],
    }
    tool_supports_parallelism = True

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Validate invoice data and return compliance result."""
        invoice_data: dict[str, Any] = kwargs["invoice_data"]
        strict_mode: bool = kwargs.get("strict_mode", False)

        data = _map_invoice_fields(invoice_data)

        missing_fields: list[str] = []
        warnings: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []

        # Determine if Kleinbetragsrechnung
        gross_amount = float(data.get("gross_amount", 0) or 0)
        is_small_invoice = 0 < gross_amount <= _SMALL_INVOICE_THRESHOLD

        if is_small_invoice:
            required_fields = _SMALL_INVOICE_REQUIRED
            legal_basis = "§33 UStDV (Kleinbetragsrechnung)"
        else:
            required_fields = set(_MANDATORY_FIELDS.keys())
            legal_basis = "§14 Abs. 4 UStG"

        # Check each required field
        for field in required_fields:
            field_config = _MANDATORY_FIELDS.get(field, {})
            legal_ref = field_config.get("legal_ref", "")
            description = field_config.get("description", field)
            severity = field_config.get("severity", "error")

            value = data.get(field)

            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)
                issue = {
                    "field": field,
                    "message": f"Pflichtangabe fehlt: {description}",
                    "legal_reference": legal_ref,
                }
                if severity == "warning" and not strict_mode:
                    warnings.append(issue)
                else:
                    errors.append(issue)

        # VAT consistency check (only for non-small invoices)
        if not is_small_invoice:
            warnings.extend(_check_vat_consistency(data))

        is_compliant = len(errors) == 0

        # Summary
        if is_compliant and not warnings:
            summary = "Rechnung erfuellt alle Pflichtangaben gemaess §14 UStG."
        elif not is_compliant:
            summary = f"Rechnung nicht konform: " f"{len(errors)} fehlende Pflichtangabe(n)."
            if warnings:
                summary += f" {len(warnings)} Hinweis(e)."
        else:
            summary = (
                f"Rechnung grundsaetzlich konform. " f"{len(warnings)} Hinweis(e) zur Pruefung."
            )

        return {
            "success": True,
            "is_compliant": is_compliant,
            "missing_fields": missing_fields,
            "warnings": warnings,
            "errors": errors,
            "legal_basis": legal_basis,
            "is_small_invoice": is_small_invoice,
            "summary": summary,
        }
