"""Validation helpers for Accounts Payable PoC configuration."""

from __future__ import annotations

from typing import Any

from ap_poc_agent.domain.models import (
    AccountDefinition,
    CompanyProfile,
    CostCenter,
    SystemConfig,
    VendorDefinition,
)


class ConfigValidationError(ValueError):
    """Raised when system configuration is invalid."""


def parse_system_config(payload: dict[str, Any]) -> SystemConfig:
    """Parse and validate the system configuration payload.

    Args:
        payload: Raw configuration dictionary.

    Returns:
        Parsed SystemConfig instance.

    Raises:
        ConfigValidationError: If validation fails.
    """
    errors = _collect_validation_errors(payload)
    if errors:
        error_message = "Configuration validation failed: " + "; ".join(errors)
        raise ConfigValidationError(error_message)

    company = CompanyProfile(**payload["company"])
    cost_centers = [CostCenter(**center) for center in payload.get("cost_centers", [])]
    accounts = [AccountDefinition(**account) for account in payload.get("accounts", [])]
    vendors = [VendorDefinition(**vendor) for vendor in payload.get("vendors", [])]

    return SystemConfig(
        chart_of_accounts=payload["chart_of_accounts"],
        tax_rates=[float(rate) for rate in payload["tax_rates"]],
        company=company,
        cost_centers=cost_centers,
        accounts=accounts,
        vendors=vendors,
        payment_terms_days=int(payload.get("payment_terms_days", 30)),
        default_currency=payload.get("default_currency", "EUR"),
    )


def _collect_validation_errors(payload: dict[str, Any]) -> list[str]:
    """Collect validation errors for the system configuration."""
    errors: list[str] = []
    required_keys = ["chart_of_accounts", "tax_rates", "company"]
    for key in required_keys:
        if key not in payload:
            errors.append(f"Missing required key: {key}")

    company = payload.get("company")
    if not isinstance(company, dict):
        errors.append("company must be an object")
    else:
        for field in ["name", "country", "vat_id"]:
            if not company.get(field):
                errors.append(f"company.{field} is required")

    chart = payload.get("chart_of_accounts")
    if chart and chart not in {"SKR03", "SKR04"}:
        errors.append("chart_of_accounts must be SKR03 or SKR04")

    tax_rates = payload.get("tax_rates", [])
    if not isinstance(tax_rates, list) or not tax_rates:
        errors.append("tax_rates must be a non-empty list")

    return errors
