"""Tax Wizard tool for account assignment and VAT logic."""

from __future__ import annotations

from typing import Any

from ap_poc_agent.domain import ConfigValidationError, parse_system_config
from ap_poc_agent.tools.data_loader import load_json_file


class TaxWizardTool:
    """Match vendors, assign accounts, and apply VAT logic."""

    @property
    def name(self) -> str:
        """Return tool name."""
        return "tax_wizard_assign_accounts"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Matches invoice supplier against vendor master data and assigns "
            "accounts plus VAT handling (domestic vs reverse charge)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "invoice_data": {
                    "type": "object",
                    "description": "Invoice data from Gatekeeper",
                },
                "system_config": {
                    "type": "object",
                    "description": "System config from Architect",
                },
                "erp_db_path": {
                    "type": "string",
                    "description": "Optional path to ERP mock data JSON",
                },
            },
            "required": ["invoice_data", "system_config"],
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "invoice_data" not in kwargs:
            return False, "invoice_data is required"
        if "system_config" not in kwargs:
            return False, "system_config is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Assign accounts and tax logic based on config and vendor data."""
        try:
            invoice = _ensure_dict(kwargs.get("invoice_data"))
            config = parse_system_config(_ensure_dict(kwargs.get("system_config")))
        except (ConfigValidationError, ValueError) as error:
            return _error_result(error)

        erp_data = _load_erp_data(kwargs.get("erp_db_path"))
        vendor_match = _match_vendor(invoice, config, erp_data)
        account_match = _match_account(invoice, config, vendor_match)
        vat_logic = _determine_vat_logic(invoice, config)
        booking = _build_booking(invoice, config, account_match, vendor_match, vat_logic)

        return {
            "success": True,
            "vendor_match": vendor_match,
            "account_assignment": account_match,
            "vat_logic": vat_logic,
            "booking_proposal": booking,
        }


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Ensure a value is a dictionary."""
    if not isinstance(value, dict):
        raise ValueError("Expected an object payload")
    return value


def _load_erp_data(erp_path: str | None) -> dict[str, Any]:
    """Load ERP mock data if provided."""
    if not erp_path:
        return {}
    return load_json_file(erp_path)


def _normalize(value: str | None) -> str:
    """Normalize string for comparison."""
    return (value or "").strip().lower()


def _match_vendor(
    invoice: dict[str, Any],
    config: Any,
    erp_data: dict[str, Any],
) -> dict[str, Any]:
    """Match vendor by VAT ID or name."""
    supplier_vat = _normalize(invoice.get("supplier_vat_id"))
    supplier_name = _normalize(invoice.get("supplier_name"))

    vendors = _vendors_from_config(config) + _vendors_from_erp(erp_data)
    for vendor in vendors:
        if supplier_vat and _normalize(vendor.get("vat_id")) == supplier_vat:
            return _vendor_result(vendor, "vat_id")
        if supplier_name and _normalize(vendor.get("name")) == supplier_name:
            return _vendor_result(vendor, "name")
    return {"matched": False, "reason": "Vendor not found"}


def _vendors_from_config(config: Any) -> list[dict[str, Any]]:
    """Extract vendor records from validated config."""
    return [
        {
            "vendor_id": vendor.vendor_id,
            "name": vendor.name,
            "vat_id": vendor.vat_id,
            "country": vendor.country,
            "default_account": vendor.default_account,
            "default_cost_center": vendor.default_cost_center,
        }
        for vendor in config.vendors
    ]


def _vendors_from_erp(erp_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract vendor records from ERP mock data."""
    vendor_entries = erp_data.get("vendors", [])
    return [vendor for vendor in vendor_entries if "name" in vendor]


def _vendor_result(vendor: dict[str, Any], matched_by: str) -> dict[str, Any]:
    """Create vendor match result."""
    return {
        "matched": True,
        "matched_by": matched_by,
        "vendor_id": vendor.get("vendor_id"),
        "name": vendor.get("name"),
        "vat_id": vendor.get("vat_id"),
        "country": vendor.get("country"),
        "default_account": vendor.get("default_account"),
        "default_cost_center": vendor.get("default_cost_center"),
    }


def _match_account(
    invoice: dict[str, Any],
    config: Any,
    vendor_match: dict[str, Any],
) -> dict[str, Any]:
    """Assign account based on vendor defaults or keyword matching."""
    if vendor_match.get("default_account"):
        return {
            "matched": True,
            "account": vendor_match["default_account"],
            "reason": "Vendor default account",
        }

    description = _normalize(invoice.get("description"))
    for account in config.accounts:
        for keyword in account.keywords:
            if keyword.lower() in description:
                return {
                    "matched": True,
                    "account": account.code,
                    "account_name": account.name,
                    "reason": f"Keyword match: {keyword}",
                }

    return {
        "matched": False,
        "reason": "No account match",
    }


def _determine_vat_logic(
    invoice: dict[str, Any],
    config: Any,
) -> dict[str, Any]:
    """Determine VAT treatment (domestic vs reverse charge)."""
    supplier_country = invoice.get("supplier_country")
    domestic = supplier_country == config.company.country
    vat_rate = float(invoice.get("tax_rate") or 0.0)

    return {
        "domestic": domestic,
        "reverse_charge": not domestic,
        "vat_rate": vat_rate,
        "vat_rate_valid": vat_rate in config.tax_rates,
    }


def _build_booking(
    invoice: dict[str, Any],
    config: Any,
    account_match: dict[str, Any],
    vendor_match: dict[str, Any],
    vat_logic: dict[str, Any],
) -> dict[str, Any]:
    """Build a booking proposal based on matches."""
    debit_account = account_match.get("account", "4920")
    credit_account = "1600" if config.chart_of_accounts == "SKR03" else "3300"

    return {
        "invoice_id": invoice.get("invoice_id"),
        "vendor": vendor_match.get("name"),
        "debit_account": debit_account,
        "credit_account": credit_account,
        "net_amount": invoice.get("net_amount"),
        "tax_amount": invoice.get("tax_amount"),
        "total_amount": invoice.get("total_amount"),
        "currency": invoice.get("currency"),
        "vat_logic": vat_logic,
    }


def _error_result(error: Exception) -> dict[str, Any]:
    """Format an error result."""
    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
    }
