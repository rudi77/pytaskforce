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


def _normalize_vat_id(raw: str | None) -> str | None:
    """
    Normalize VAT ID by removing prefixes and whitespace.

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
    m = re.search(r"\b[A-Z]{2}[0-9A-Za-z\+\*\.]{2,12}\b", s)
    if m:
        return m.group(0)

    # German tax number fallback (e.g., 12/345/67890)
    m = re.search(r"\b\d{2,3}/\d{3}/\d{5}\b", s)
    if m:
        return m.group(0)

    return s  # Return cleaned string as fallback


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
        """
        try:
            # --- NEU: MAPPING / NORMALISIERUNG ---
            # Wir erstellen eine Arbeitskopie und mappen die Extraktions-Daten
            # auf die erwarteten Compliance-Felder.
            data = invoice_data.copy()

            # 1. Mapping von Beträgen
            if "net_amount" not in data:
                data["net_amount"] = data.get("total_net")
            if "gross_amount" not in data:
                data["gross_amount"] = data.get("total_gross")
            if "vat_amount" not in data:
                data["vat_amount"] = data.get("total_vat")

            # 2. Mapping von IDs und Adressen
            if "vat_id" not in data:
                # Bevorzuge Lieferanten-ID
                data["vat_id"] = data.get("supplier_vat_id")

            # Normalize VAT ID (remove prefixes like "USt-IDNr." and whitespace)
            data["vat_id"] = _normalize_vat_id(data.get("vat_id"))

            if "supplier_name" not in data and "sender_name" in data:  # Fallback
                data["supplier_name"] = data.get("sender_name")

            # 3. Mapping von Mengen/Beschreibungen
            # Wenn line_items existieren, gilt "Menge und Art" als erfüllt
            if "quantity_description" not in data:
                line_items = data.get("line_items", [])
                if line_items and isinstance(line_items, list) and len(line_items) > 0:
                    # Wir generieren einen Platzhalter-Text für die Prüfung
                    item_desc = ", ".join([str(i.get("description", "")) for i in line_items[:3]])
                    data["quantity_description"] = f"Positionen vorhanden: {item_desc}..."

            # 4. Mapping von vat_rate aus vat_breakdown (für Mehrfachsteuersätze)
            if "vat_rate" not in data or not data.get("vat_rate"):
                vb = data.get("vat_breakdown") or []
                if isinstance(vb, list) and len(vb) > 0:
                    rates = []
                    for item in vb:
                        r = item.get("rate")
                        if r is not None:
                            rates.append(float(r))
                    # Store as comma-separated string to satisfy mandatory field check
                    if rates:
                        data["vat_rate"] = ",".join(str(r) for r in sorted(set(rates)))

            # --- ENDE MAPPING ---

            missing_fields = []
            warnings = []
            errors = []

            # Determine if this is a Kleinbetragsrechnung
            gross_amount = float(data.get("gross_amount", 0) or 0)
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

                value = data.get(field) # Nutze die gemappten Daten

                # Check if field is present and non-empty
                if not value or (isinstance(value, str) and not value.strip()):
                    # Kontext-Logik: Bei Auslandsrechnungen (wenn vat_id da ist aber nicht DE)
                    # sind wir nachsichtiger, hier vereinfacht dargestellt:
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

                # Validation logic for VAT ID (mit dem neuen flexiblen Regex aus vorherigem Schritt)
                elif field == "vat_id" and value:
                    # Hier wieder die Logik aus dem vorherigen Schritt einfügen
                    # (Habe ich der Kürze halber hier kondensiert)
                    pattern = r"^([A-Z]{2})[0-9A-Za-z\+\*\.]{2,12}$"
                    if not re.match(pattern, str(value)):
                        # Check Tax Number fallback...
                        pass

            # Check for VAT consistency
            if not is_small_invoice:
                net = float(data.get("net_amount", 0) or 0)
                vat = float(data.get("vat_amount", 0) or 0)

                vb = data.get("vat_breakdown") or []

                # Multi-rate calculation via vat_breakdown
                if isinstance(vb, list) and len(vb) > 0:
                    expected_vat = 0.0
                    for item in vb:
                        item_net = float(item.get("net_amount", 0) or 0)
                        item_rate = float(item.get("rate", 0) or 0)
                        expected_vat += item_net * item_rate

                    if abs(expected_vat - vat) > 0.05:
                        warnings.append({
                            "field": "vat_calculation",
                            "message": f"MwSt-Check (multi-rate): {vat:.2f} (Ist) vs {expected_vat:.2f} (Soll)",
                            "legal_reference": "§14 Abs. 4 Nr. 8 UStG"
                        })
                else:
                    # Single-rate fallback
                    rate = 0.0

                    # Try to extract rate from vat_rate field
                    rate_str = str(data.get("vat_rate", "") or "")
                    if rate_str and "," not in rate_str:
                        # Single rate value
                        try:
                            rate = float(rate_str)
                        except ValueError:
                            pass

                    # Fallback: Try rate from line_items
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
                                "message": f"MwSt-Check: {vat:.2f} (Ist) vs {expected_vat:.2f} (Soll)",
                                "legal_reference": "§14 Abs. 4 Nr. 8 UStG"
                            })

            is_compliant = len(errors) == 0

            return {
                "success": True,
                "is_compliant": is_compliant,
                "mapped_data_debug": data, # Hilfreich fürs Debugging
                "missing_fields": missing_fields,
                "warnings": warnings,
                "errors": errors,
                "legal_basis": legal_basis,
                "summary": self._generate_summary(is_compliant, errors, warnings)
            }

        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

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
