#!/usr/bin/env python3
"""
Compliance validation for German invoices (§14 UStG).

Standalone script adapted from accounting_agent.tools.compliance_checker_tool.
Validates invoice data against mandatory field requirements.

Usage:
    python compliance.py --input invoice.json [--rules compliance_rules.yaml]
    echo '{"supplier_name": "..."}' | python compliance.py

Output: JSON compliance result to stdout.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


# --- Default Rules (§14 Abs. 4 UStG) ---

DEFAULT_MANDATORY_FIELDS = {
    "supplier_name": {
        "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
        "description": "Name des leistenden Unternehmers",
        "severity": "error",
    },
    "supplier_address": {
        "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
        "description": "Anschrift des leistenden Unternehmers",
        "severity": "error",
    },
    "vat_id": {
        "legal_ref": "§14 Abs. 4 Nr. 2 UStG",
        "description": "USt-IdNr. oder Steuernummer",
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

SMALL_INVOICE_THRESHOLD = 250.0
SMALL_INVOICE_REQUIRED = {
    "supplier_name",
    "invoice_date",
    "quantity_description",
    "gross_amount",
    "vat_rate",
}


def normalize_vat_id(raw: str | None) -> str | None:
    """Normalize VAT ID by removing prefixes and whitespace."""
    if not raw:
        return None
    s = str(raw).strip()
    s = re.sub(r"(?i)\b(ust[-\s]?id(nr)?\.?|vat\s?id\.?|uid)\b[:\s]*", "", s).strip()
    s = re.sub(r"\s+", "", s)

    # EU VAT-ID (e.g., DE99999999, ATU12345678)
    m = re.search(r"\b[A-Z]{2}[0-9A-Za-z\+\*\.]{2,12}\b", s)
    if m:
        return m.group(0)

    # German tax number (e.g., 12/345/67890)
    m = re.search(r"\b\d{2,3}/\d{3}/\d{5}\b", s)
    if m:
        return m.group(0)

    return s


def normalize_invoice_data(data: dict[str, Any]) -> dict[str, Any]:
    """Map extraction field names to compliance field names."""
    d = data.copy()

    # Amount mappings
    if "net_amount" not in d:
        d["net_amount"] = d.get("total_net")
    if "gross_amount" not in d:
        d["gross_amount"] = d.get("total_gross")
    if "vat_amount" not in d:
        d["vat_amount"] = d.get("total_vat")

    # VAT ID mapping
    if "vat_id" not in d:
        d["vat_id"] = d.get("supplier_vat_id")
    d["vat_id"] = normalize_vat_id(d.get("vat_id"))

    # Supplier name fallback
    if "supplier_name" not in d and "sender_name" in d:
        d["supplier_name"] = d.get("sender_name")

    # Quantity/description from line items
    if "quantity_description" not in d:
        line_items = d.get("line_items", [])
        if line_items and isinstance(line_items, list) and len(line_items) > 0:
            descs = [str(i.get("description", "")) for i in line_items[:5]]
            d["quantity_description"] = ", ".join(filter(None, descs))

    # VAT rate from vat_breakdown or line_items
    if not d.get("vat_rate"):
        vb = d.get("vat_breakdown") or []
        if isinstance(vb, list) and len(vb) > 0:
            rates = []
            for item in vb:
                r = item.get("rate")
                if r is not None:
                    rates.append(float(r))
            if rates:
                d["vat_rate"] = ",".join(str(r) for r in sorted(set(rates)))
        # Fallback: extract from line_items
        if not d.get("vat_rate"):
            line_items = d.get("line_items", [])
            if isinstance(line_items, list):
                rates = []
                for item in line_items:
                    r = item.get("vat_rate")
                    if r is not None:
                        rates.append(float(r))
                if rates:
                    d["vat_rate"] = ",".join(str(r) for r in sorted(set(rates)))

    return d


def load_rules(rules_path: str | None) -> dict[str, Any]:
    """Load compliance rules from YAML file or use defaults."""
    if not rules_path:
        return DEFAULT_MANDATORY_FIELDS

    path = Path(rules_path)
    if not path.exists():
        return DEFAULT_MANDATORY_FIELDS

    try:
        with open(path, encoding="utf-8") as f:
            rules = yaml.safe_load(f) or {}
        loaded = rules.get("mandatory_fields", {})
        return loaded if loaded else DEFAULT_MANDATORY_FIELDS
    except yaml.YAMLError:
        return DEFAULT_MANDATORY_FIELDS


def check_compliance(
    invoice_data: dict[str, Any],
    rules_path: str | None = None,
    strict_mode: bool = False,
) -> dict[str, Any]:
    """
    Validate invoice against §14 UStG requirements.

    Returns dict with: is_compliant, missing_fields, errors, warnings, summary.
    """
    mandatory_fields = load_rules(rules_path)
    data = normalize_invoice_data(invoice_data)

    missing_fields = []
    warnings = []
    errors = []

    # Kleinbetragsrechnung check
    gross_amount = float(data.get("gross_amount", 0) or 0)
    is_small_invoice = 0 < gross_amount <= SMALL_INVOICE_THRESHOLD

    if is_small_invoice:
        required_fields = SMALL_INVOICE_REQUIRED
        legal_basis = "§33 UStDV (Kleinbetragsrechnung)"
    else:
        required_fields = set(mandatory_fields.keys())
        legal_basis = "§14 Abs. 4 UStG"

    # Check each required field
    for field in required_fields:
        field_config = mandatory_fields.get(field, {})
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
                "severity": severity,
            }
            if severity == "warning" and not strict_mode:
                warnings.append(issue)
            else:
                errors.append(issue)

    # VAT consistency check
    if not is_small_invoice:
        net = float(data.get("net_amount", 0) or 0)
        vat = float(data.get("vat_amount", 0) or 0)
        vb = data.get("vat_breakdown") or []

        if isinstance(vb, list) and len(vb) > 0:
            expected_vat = sum(
                float(item.get("net_amount", 0) or 0) * float(item.get("rate", 0) or 0)
                for item in vb
            )
            if abs(expected_vat - vat) > 0.05:
                warnings.append({
                    "field": "vat_calculation",
                    "message": f"MwSt-Abweichung (multi-rate): {vat:.2f} vs {expected_vat:.2f}",
                    "legal_reference": "§14 Abs. 4 Nr. 8 UStG",
                    "severity": "warning",
                })
        else:
            rate_str = str(data.get("vat_rate", "") or "")
            rate = 0.0
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
                    warnings.append({
                        "field": "vat_calculation",
                        "message": f"MwSt-Abweichung: {vat:.2f} vs {expected_vat:.2f}",
                        "legal_reference": "§14 Abs. 4 Nr. 8 UStG",
                        "severity": "warning",
                    })

    # Reverse charge detection
    reverse_charge_indicators = [
        "steuerschuldnerschaft des leistungsempfängers",
        "reverse charge",
        "§13b ustg",
        "vat due by recipient",
    ]
    all_text = json.dumps(data, ensure_ascii=False).lower()
    is_reverse_charge = any(ind in all_text for ind in reverse_charge_indicators)

    is_compliant = len(errors) == 0

    # Summary
    if is_compliant and not warnings:
        summary = "Rechnung erfuellt alle Pflichtangaben gemaess §14 UStG."
    elif is_compliant:
        summary = f"Rechnung grundsaetzlich konform. {len(warnings)} Hinweis(e)."
    else:
        summary = f"Rechnung nicht konform: {len(errors)} fehlende Pflichtangabe(n)."

    return {
        "is_compliant": is_compliant,
        "is_small_invoice": is_small_invoice,
        "is_reverse_charge": is_reverse_charge,
        "legal_basis": legal_basis,
        "missing_fields": missing_fields,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
        "fields_checked": len(required_fields),
    }


def main():
    parser = argparse.ArgumentParser(description="§14 UStG Compliance Check")
    parser.add_argument("--input", "-i", help="Path to invoice JSON file (or use stdin)")
    parser.add_argument("--rules", "-r", help="Path to compliance_rules.yaml")
    parser.add_argument("--strict", action="store_true", help="Strict mode (warnings become errors)")
    args = parser.parse_args()

    # Read input
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            invoice_data = json.load(f)
    else:
        invoice_data = json.load(sys.stdin)

    result = check_compliance(invoice_data, args.rules, args.strict)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
