"""Domain models for the Accounts Payable PoC plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CompanyProfile:
    """Configuration for the company running the PoC."""

    name: str
    country: str
    vat_id: str


@dataclass(frozen=True)
class CostCenter:
    """Cost center metadata."""

    code: str
    name: str


@dataclass(frozen=True)
class AccountDefinition:
    """Definition for a chart of accounts entry."""

    code: str
    name: str
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VendorDefinition:
    """Vendor master data entry."""

    vendor_id: str
    name: str
    vat_id: str
    country: str
    default_account: str | None = None
    default_cost_center: str | None = None


@dataclass(frozen=True)
class SystemConfig:
    """Validated system configuration for the PoC."""

    chart_of_accounts: str
    tax_rates: list[float]
    company: CompanyProfile
    cost_centers: list[CostCenter]
    accounts: list[AccountDefinition]
    vendors: list[VendorDefinition]
    payment_terms_days: int
    default_currency: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a dictionary."""
        return {
            "chart_of_accounts": self.chart_of_accounts,
            "tax_rates": self.tax_rates,
            "company": {
                "name": self.company.name,
                "country": self.company.country,
                "vat_id": self.company.vat_id,
            },
            "cost_centers": [
                {"code": center.code, "name": center.name}
                for center in self.cost_centers
            ],
            "accounts": [
                {
                    "code": account.code,
                    "name": account.name,
                    "keywords": account.keywords,
                }
                for account in self.accounts
            ],
            "vendors": [
                {
                    "vendor_id": vendor.vendor_id,
                    "name": vendor.name,
                    "vat_id": vendor.vat_id,
                    "country": vendor.country,
                    "default_account": vendor.default_account,
                    "default_cost_center": vendor.default_cost_center,
                }
                for vendor in self.vendors
            ],
            "payment_terms_days": self.payment_terms_days,
            "default_currency": self.default_currency,
        }
