"""
Compliance validation tool for German invoice requirements.

This tool validates invoices against §14 UStG (Umsatzsteuergesetz)
requirements for mandatory fields (Pflichtangaben).

Rules can be loaded from YAML configuration files for flexibility.
"""

import re
from pathlib import Path
from typing import Any

import yaml

from accounting_agent.tools.tool_base import ApprovalRiskLevel


class ComplianceCheckerTool:
    """
    Validate invoice compliance with §14 UStG requirements.

    Checks for all mandatory fields (Pflichtangaben) required by German
    tax law. Returns detailed compliance report with legal references.

    Also checks for Kleinbetragsrechnung (§33 UStDV) reduced requirements
    for invoices under 250 EUR.

    Rules can be loaded from a YAML file via the rules_path parameter,
    or use built-in defaults if no path is provided.
    """

    # Default §14 Abs. 4 UStG mandatory fields (used if no YAML provided)
    DEFAULT_MANDATORY_FIELDS = {
        "supplier_name": {
            "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
            "description": "Name und Anschrift des leistenden Unternehmers",
            "severity": "error"
        },
        "supplier_address": {
            "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
            "description": "Anschrift des leistenden Unternehmers",
            "severity": "error"
        },
        "recipient_name": {
            "legal_ref": "§14 Abs. 4 Nr. 1 UStG",
            "description": "Name und Anschrift des Leistungsempfängers",
            "severity": "error"
        },
        "vat_id": {
            "legal_ref": "§14 Abs. 4 Nr. 2 UStG",
            "description": "Steuernummer oder USt-IdNr. des Lieferanten",
            "severity": "error",
            "validation": {"pattern_vat_id": r"^DE[0-9]{9}$"}
        },
        "invoice_date": {
            "legal_ref": "§14 Abs. 4 Nr. 3 UStG",
            "description": "Ausstellungsdatum der Rechnung",
            "severity": "error"
        },
        "invoice_number": {
            "legal_ref": "§14 Abs. 4 Nr. 4 UStG",
            "description": "Fortlaufende Rechnungsnummer",
            "severity": "error"
        },
        "quantity_description": {
            "legal_ref": "§14 Abs. 4 Nr. 5 UStG",
            "description": "Menge und Art der Lieferung/Leistung",
            "severity": "error"
        },
        "delivery_date": {
            "legal_ref": "§14 Abs. 4 Nr. 6 UStG",
            "description": "Zeitpunkt der Lieferung/Leistung",
            "severity": "warning"
        },
        "net_amount": {
            "legal_ref": "§14 Abs. 4 Nr. 7 UStG",
            "description": "Entgelt (Nettobetrag)",
            "severity": "error"
        },
        "vat_rate": {
            "legal_ref": "§14 Abs. 4 Nr. 8 UStG",
            "description": "Anzuwendender Steuersatz",
            "severity": "error"
        },
        "vat_amount": {
            "legal_ref": "§14 Abs. 4 Nr. 8 UStG",
            "description": "Auf das Entgelt entfallender Steuerbetrag",
            "severity": "error"
        }
    }

    # Reduced requirements for Kleinbetragsrechnung (§33 UStDV)
    SMALL_INVOICE_THRESHOLD = 250.0
    SMALL_INVOICE_REQUIRED = {
        "supplier_name",
        "invoice_date",
        "quantity_description",
        "gross_amount",
        "vat_rate"
    }

    def __init__(self, rules_path: str | None = None):
        """
        Initialize ComplianceCheckerTool.

        Args:
            rules_path: Optional path to compliance_rules.yaml file.
                If provided, rules are loaded from the YAML file.
                If None, built-in default rules are used.
        """
        self._rules_path = rules_path
        self._rules: dict[str, Any] = {}
        self._mandatory_fields: dict[str, Any] = {}

        if rules_path:
            self._load_rules()
        else:
            # Use default rules
            self._mandatory_fields = self.DEFAULT_MANDATORY_FIELDS.copy()

    def _load_rules(self) -> None:
        """Load compliance rules from YAML file."""
        rules_file = Path(self._rules_path)
        if not rules_file.exists():
            # Fall back to defaults if file not found
            self._mandatory_fields = self.DEFAULT_MANDATORY_FIELDS.copy()
            return

        try:
            with open(rules_file, encoding="utf-8") as f:
                self._rules = yaml.safe_load(f) or {}

            # Extract mandatory fields from loaded rules
            loaded_fields = self._rules.get("mandatory_fields", {})
            if loaded_fields:
                self._mandatory_fields = loaded_fields
            else:
                self._mandatory_fields = self.DEFAULT_MANDATORY_FIELDS.copy()

        except yaml.YAMLError:
            # Fall back to defaults on parse error
            self._mandatory_fields = self.DEFAULT_MANDATORY_FIELDS.copy()

    @property
    def MANDATORY_FIELDS(self) -> dict[str, Any]:
        """Return the active mandatory fields (from YAML or defaults)."""
        return self._mandatory_fields

    @property
    def name(self) -> str:
        """Return tool name."""
        return "check_compliance"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Validate invoice against §14 UStG Pflichtangaben requirements. "
            "Returns compliance status, missing fields, warnings, and "
            "specific legal references for each issue found. "
            "Also checks for Kleinbetragsrechnung (§33 UStDV) requirements."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "invoice_data": {
                    "type": "object",
                    "description": (
                        "Structured invoice data to validate. Should include fields like: "
                        "supplier_name, supplier_address, vat_id, invoice_number, "
                        "invoice_date, net_amount, vat_rate, vat_amount, gross_amount"
                    )
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "Enable strict validation (all warnings become errors)",
                    "default": False
                }
            },
            "required": ["invoice_data"]
        }

    @property
    def requires_approval(self) -> bool:
        """Read-only validation, no approval required."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - read-only validation."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        strict = kwargs.get("strict_mode", False)
        return (
            f"Tool: {self.name}\n"
            f"Operation: Validate invoice compliance (§14 UStG)\n"
            f"Strict Mode: {strict}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "invoice_data" not in kwargs:
            return False, "Missing required parameter: invoice_data"
        if not isinstance(kwargs["invoice_data"], dict):
            return False, "invoice_data must be a dictionary"
        return True, None

    async def execute(
        self,
        invoice_data: dict[str, Any],
        strict_mode: bool = False,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Validate invoice and return compliance result.

        Args:
            invoice_data: Invoice data to validate
            strict_mode: If True, warnings become errors

        Returns:
            Dictionary with:
            - success: bool (tool execution success)
            - is_compliant: bool (invoice compliance status)
            - missing_fields: List of missing mandatory fields
            - warnings: List of non-critical issues
            - errors: List of critical compliance errors
            - legal_basis: Primary legal reference
            - is_small_invoice: Whether Kleinbetragsrechnung rules apply
        """
        try:
            missing_fields = []
            warnings = []
            errors = []

            # Determine if this is a Kleinbetragsrechnung
            gross_amount = float(invoice_data.get("gross_amount", 0) or
                                invoice_data.get("total_gross", 0) or 0)
            is_small_invoice = gross_amount <= self.SMALL_INVOICE_THRESHOLD and gross_amount > 0

            # Select applicable required fields
            if is_small_invoice:
                required_fields = self.SMALL_INVOICE_REQUIRED
                legal_basis = "§33 UStDV (Kleinbetragsrechnung)"
            else:
                required_fields = set(self.MANDATORY_FIELDS.keys())
                legal_basis = "§14 Abs. 4 UStG"

            # Check each required field
            for field in required_fields:
                field_config = self.MANDATORY_FIELDS.get(field, {})
                legal_ref = field_config.get("legal_ref", "")
                description = field_config.get("description", field)
                severity = field_config.get("severity", "error")

                value = invoice_data.get(field)

                # Check if field is present and non-empty
                if not value or (isinstance(value, str) and not value.strip()):
                    missing_fields.append(field)

                    issue = {
                        "field": field,
                        "message": f"Pflichtangabe fehlt: {description}",
                        "legal_reference": legal_ref
                    }

                    if severity == "warning" and not strict_mode:
                        warnings.append(issue)
                    else:
                        errors.append(issue)

                # Additional validation for specific fields
                elif field == "vat_id" and value:
                    # Get validation patterns (support both old and new YAML formats)
                    validation = field_config.get("validation", {})
                    vat_pattern = (
                        validation.get("pattern_vat_id")
                        or field_config.get("validation_pattern")  # Legacy format
                    )
                    tax_pattern = (
                        validation.get("pattern_tax_number")
                        or r"^\d{2,3}/\d{3}/\d{5}$"  # Default fallback
                    )

                    if vat_pattern:
                        vat_match = re.match(vat_pattern, str(value))
                        tax_match = re.match(tax_pattern, str(value))

                        if not vat_match and not tax_match:
                            warnings.append({
                                "field": field,
                                "message": f"USt-IdNr. Format ungültig: {value}",
                                "legal_reference": legal_ref,
                                "hint": "Erwartet: EU USt-IdNr. oder Steuernummer"
                            })

            # Check for VAT consistency
            if not is_small_invoice:
                net = float(invoice_data.get("net_amount", 0) or
                           invoice_data.get("total_net", 0) or 0)
                vat = float(invoice_data.get("vat_amount", 0) or
                           invoice_data.get("total_vat", 0) or 0)
                rate = float(invoice_data.get("vat_rate", 0) or 0)

                if net > 0 and rate > 0:
                    expected_vat = net * rate
                    if abs(expected_vat - vat) > 0.01:  # Allow 1 cent tolerance
                        warnings.append({
                            "field": "vat_calculation",
                            "message": (
                                f"MwSt-Berechnung inkonsistent: "
                                f"Erwartet {expected_vat:.2f}, gefunden {vat:.2f}"
                            ),
                            "legal_reference": "§14 Abs. 4 Nr. 8 UStG"
                        })

            is_compliant = len(errors) == 0

            return {
                "success": True,
                "is_compliant": is_compliant,
                "missing_fields": missing_fields,
                "warnings": warnings,
                "errors": errors,
                "legal_basis": legal_basis,
                "is_small_invoice": is_small_invoice,
                "small_invoice_threshold": self.SMALL_INVOICE_THRESHOLD,
                "fields_checked": len(required_fields),
                "summary": self._generate_summary(is_compliant, errors, warnings)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }

    def _generate_summary(
        self,
        is_compliant: bool,
        errors: list[dict],
        warnings: list[dict]
    ) -> str:
        """Generate human-readable compliance summary."""
        if is_compliant and not warnings:
            return "Rechnung erfüllt alle Pflichtangaben gemäß §14 UStG."

        parts = []
        if not is_compliant:
            parts.append(f"Rechnung nicht konform: {len(errors)} fehlende Pflichtangabe(n).")
        elif warnings:
            parts.append("Rechnung grundsätzlich konform.")

        if warnings:
            parts.append(f"{len(warnings)} Hinweis(e) zur Prüfung.")

        return " ".join(parts)
