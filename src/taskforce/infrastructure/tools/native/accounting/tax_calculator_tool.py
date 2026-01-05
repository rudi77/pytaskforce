"""
Tax calculation tool for VAT and depreciation.

This tool performs deterministic tax calculations for:
- VAT (Umsatzsteuer) - standard and reduced rates
- Input tax (Vorsteuer)
- Reverse charge
- Depreciation (AfA)
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from taskforce.core.interfaces.tools import ApprovalRiskLevel


class TaxCalculatorTool:
    """
    Calculate VAT (Umsatzsteuer) and depreciation (AfA) amounts.

    Rule-based calculations - no LLM involved. Supports German tax rates
    and AfA tables for common asset types.
    """

    # German VAT rates
    VAT_RATES = {
        "standard": Decimal("0.19"),
        "reduced": Decimal("0.07"),
        "zero": Decimal("0.00")
    }

    # AfA-Tabellen für häufige Anlagegüter (vereinfacht)
    AFA_TABLES = {
        "computer": {"years": 3, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 6.14.3.2"},
        "software": {"years": 3, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 6.14.3.1"},
        "laptop": {"years": 3, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 6.14.3.2"},
        "monitor": {"years": 3, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 6.14.3.2"},
        "server": {"years": 3, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 6.14.3.2"},
        "office_furniture": {"years": 13, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 6.4"},
        "vehicle": {"years": 6, "legal_basis": "§7 Abs. 1 EStG, AfA-Tabelle 7.6"},
        "building": {"years": 33, "legal_basis": "§7 Abs. 4 EStG"},
        "machine": {"years": 10, "legal_basis": "§7 Abs. 1 EStG"},
        "default": {"years": 5, "legal_basis": "§7 Abs. 1 EStG"}
    }

    # GWG threshold (since 2018)
    GWG_THRESHOLD = Decimal("800.00")
    GWG_POOL_MIN = Decimal("250.00")

    @property
    def name(self) -> str:
        """Return tool name."""
        return "calculate_tax"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Calculate VAT amounts and depreciation schedules. "
            "Supports German VAT rates (7%, 19%), reverse charge, "
            "input tax (Vorsteuer), and AfA tables. "
            "Returns calculation with legal basis. Rule-based, no LLM."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "calculation_type": {
                    "type": "string",
                    "description": "Type of calculation to perform",
                    "enum": ["vat", "input_tax", "reverse_charge", "afa", "gwg_check"]
                },
                "amount": {
                    "type": "number",
                    "description": "Base amount for calculation (net for VAT, gross for input_tax)"
                },
                "vat_rate": {
                    "type": "number",
                    "description": "VAT rate as decimal (0.19 for 19%, 0.07 for 7%)"
                },
                "asset_type": {
                    "type": "string",
                    "description": "Asset type for AfA calculation (computer, software, vehicle, etc.)"
                }
            },
            "required": ["calculation_type", "amount"]
        }

    @property
    def requires_approval(self) -> bool:
        """Read-only calculation, no approval required."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - pure calculation."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        calc_type = kwargs.get("calculation_type", "vat")
        amount = kwargs.get("amount", 0)
        return (
            f"Tool: {self.name}\n"
            f"Operation: {calc_type} calculation\n"
            f"Amount: {amount}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "calculation_type" not in kwargs:
            return False, "Missing required parameter: calculation_type"
        if "amount" not in kwargs:
            return False, "Missing required parameter: amount"

        calc_type = kwargs["calculation_type"]
        valid_types = ["vat", "input_tax", "reverse_charge", "afa", "gwg_check"]
        if calc_type not in valid_types:
            return False, f"Invalid calculation_type: {calc_type}. Valid: {valid_types}"

        amount = kwargs["amount"]
        if not isinstance(amount, (int, float, Decimal)):
            return False, "amount must be a number"
        if amount < 0:
            return False, "amount cannot be negative"

        return True, None

    async def execute(
        self,
        calculation_type: str,
        amount: float,
        vat_rate: float | None = None,
        asset_type: str | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Perform tax calculation.

        Args:
            calculation_type: Type of calculation (vat, input_tax, reverse_charge, afa, gwg_check)
            amount: Base amount
            vat_rate: VAT rate (optional, defaults to 19%)
            asset_type: Asset type for AfA (optional)

        Returns:
            Dictionary with calculation results and legal basis
        """
        try:
            amount_decimal = Decimal(str(amount)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            if calculation_type == "vat":
                return self._calculate_vat(amount_decimal, vat_rate)

            elif calculation_type == "input_tax":
                return self._calculate_input_tax(amount_decimal, vat_rate)

            elif calculation_type == "reverse_charge":
                return self._calculate_reverse_charge(amount_decimal, vat_rate)

            elif calculation_type == "afa":
                return self._calculate_afa(amount_decimal, asset_type)

            elif calculation_type == "gwg_check":
                return self._check_gwg(amount_decimal)

            else:
                return {
                    "success": False,
                    "error": f"Unknown calculation_type: {calculation_type}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }

    def _calculate_vat(
        self,
        net_amount: Decimal,
        vat_rate: float | None
    ) -> dict[str, Any]:
        """Calculate VAT from net amount."""
        rate = Decimal(str(vat_rate)) if vat_rate else self.VAT_RATES["standard"]
        vat_amount = (net_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gross_amount = net_amount + vat_amount

        return {
            "success": True,
            "calculation_type": "vat",
            "net_amount": float(net_amount),
            "vat_rate": float(rate),
            "vat_rate_percent": float(rate * 100),
            "vat_amount": float(vat_amount),
            "gross_amount": float(gross_amount),
            "legal_basis": "§12 UStG",
            "explanation": f"Umsatzsteuer {float(rate*100):.0f}% auf Nettobetrag {net_amount} EUR"
        }

    def _calculate_input_tax(
        self,
        gross_amount: Decimal,
        vat_rate: float | None
    ) -> dict[str, Any]:
        """Calculate input tax (Vorsteuer) from gross amount."""
        rate = Decimal(str(vat_rate)) if vat_rate else self.VAT_RATES["standard"]

        # Formula: Vorsteuer = Brutto * (MwSt-Satz / (1 + MwSt-Satz))
        input_tax = (gross_amount * rate / (1 + rate)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net_amount = gross_amount - input_tax

        return {
            "success": True,
            "calculation_type": "input_tax",
            "gross_amount": float(gross_amount),
            "vat_rate": float(rate),
            "vat_rate_percent": float(rate * 100),
            "input_tax": float(input_tax),
            "net_amount": float(net_amount),
            "legal_basis": "§15 Abs. 1 UStG",
            "explanation": f"Vorsteuerabzug {float(rate*100):.0f}% aus Bruttobetrag {gross_amount} EUR"
        }

    def _calculate_reverse_charge(
        self,
        net_amount: Decimal,
        vat_rate: float | None
    ) -> dict[str, Any]:
        """Calculate reverse charge VAT."""
        rate = Decimal(str(vat_rate)) if vat_rate else self.VAT_RATES["standard"]
        vat_amount = (net_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "success": True,
            "calculation_type": "reverse_charge",
            "net_amount": float(net_amount),
            "vat_rate": float(rate),
            "vat_rate_percent": float(rate * 100),
            "reverse_charge_vat": float(vat_amount),
            "input_tax_deductible": float(vat_amount),
            "net_effect": 0.0,
            "legal_basis": "§13b UStG",
            "explanation": (
                f"Reverse-Charge-Verfahren: Steuerschuldnerschaft des Leistungsempfängers. "
                f"MwSt {vat_amount} EUR wird geschuldet und als Vorsteuer abgezogen."
            ),
            "booking_hint": "Buchung: USt (Konto 1787) und Vorsteuer (Konto 1577) in gleicher Höhe"
        }

    def _calculate_afa(
        self,
        acquisition_cost: Decimal,
        asset_type: str | None
    ) -> dict[str, Any]:
        """Calculate depreciation (AfA) schedule."""
        asset_key = (asset_type or "default").lower().replace(" ", "_")
        afa_config = self.AFA_TABLES.get(asset_key, self.AFA_TABLES["default"])

        years = afa_config["years"]
        legal_basis = afa_config["legal_basis"]

        annual_afa = (acquisition_cost / years).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        monthly_afa = (annual_afa / 12).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Generate depreciation schedule
        schedule = []
        remaining = acquisition_cost
        for year in range(1, years + 1):
            depreciation = min(annual_afa, remaining)
            remaining -= depreciation
            schedule.append({
                "year": year,
                "depreciation": float(depreciation),
                "remaining_value": float(max(remaining, Decimal("0")))
            })

        return {
            "success": True,
            "calculation_type": "afa",
            "acquisition_cost": float(acquisition_cost),
            "asset_type": asset_type or "default",
            "afa_years": years,
            "annual_afa": float(annual_afa),
            "monthly_afa": float(monthly_afa),
            "depreciation_schedule": schedule,
            "legal_basis": legal_basis,
            "explanation": f"Lineare AfA über {years} Jahre für {asset_type or 'Wirtschaftsgut'}"
        }

    def _check_gwg(self, net_amount: Decimal) -> dict[str, Any]:
        """Check GWG (geringwertiges Wirtschaftsgut) treatment."""
        is_gwg = net_amount <= self.GWG_THRESHOLD
        is_pool = self.GWG_POOL_MIN <= net_amount <= self.GWG_THRESHOLD

        if net_amount <= self.GWG_POOL_MIN:
            treatment = "sofort_abzugsfaehig"
            explanation = f"Wirtschaftsgut unter {self.GWG_POOL_MIN} EUR: Sofortabzug als Betriebsausgabe möglich"
            legal_basis = "§6 Abs. 2 EStG"
        elif is_gwg:
            treatment = "gwg_oder_pool"
            explanation = (
                f"Wirtschaftsgut zwischen {self.GWG_POOL_MIN} EUR und {self.GWG_THRESHOLD} EUR: "
                "Wahlrecht zwischen GWG-Sofortabschreibung oder Poolabschreibung (5 Jahre)"
            )
            legal_basis = "§6 Abs. 2 / Abs. 2a EStG"
        else:
            treatment = "normale_afa"
            explanation = (
                f"Wirtschaftsgut über {self.GWG_THRESHOLD} EUR: "
                "Reguläre Abschreibung nach AfA-Tabelle erforderlich"
            )
            legal_basis = "§7 Abs. 1 EStG"

        return {
            "success": True,
            "calculation_type": "gwg_check",
            "net_amount": float(net_amount),
            "is_gwg": is_gwg,
            "is_pool_eligible": is_pool,
            "treatment": treatment,
            "gwg_threshold": float(self.GWG_THRESHOLD),
            "pool_minimum": float(self.GWG_POOL_MIN),
            "legal_basis": legal_basis,
            "explanation": explanation
        }
