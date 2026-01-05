"""
Tests for TaxCalculatorTool.

Tests VAT and depreciation calculations.
"""

import pytest

from taskforce.infrastructure.tools.native.accounting.tax_calculator_tool import (
    TaxCalculatorTool,
)


@pytest.fixture
def tax_tool() -> TaxCalculatorTool:
    """Create TaxCalculatorTool instance."""
    return TaxCalculatorTool()


class TestTaxCalculatorTool:
    """Test suite for TaxCalculatorTool."""

    def test_tool_metadata(self, tax_tool: TaxCalculatorTool):
        """Test tool metadata properties."""
        assert tax_tool.name == "calculate_tax"
        assert "VAT" in tax_tool.description or "Umsatzsteuer" in tax_tool.description
        assert tax_tool.requires_approval is False

    def test_parameters_schema(self, tax_tool: TaxCalculatorTool):
        """Test parameter schema structure."""
        schema = tax_tool.parameters_schema
        assert schema["type"] == "object"
        assert "calculation_type" in schema["properties"]
        assert "amount" in schema["properties"]
        assert "calculation_type" in schema["required"]
        assert "amount" in schema["required"]

    def test_validate_params_missing_calculation_type(self, tax_tool: TaxCalculatorTool):
        """Test validation fails without calculation_type."""
        valid, error = tax_tool.validate_params(amount=100)
        assert valid is False
        assert "calculation_type" in error

    def test_validate_params_missing_amount(self, tax_tool: TaxCalculatorTool):
        """Test validation fails without amount."""
        valid, error = tax_tool.validate_params(calculation_type="vat")
        assert valid is False
        assert "amount" in error

    def test_validate_params_invalid_calculation_type(self, tax_tool: TaxCalculatorTool):
        """Test validation fails with invalid calculation_type."""
        valid, error = tax_tool.validate_params(
            calculation_type="invalid", amount=100
        )
        assert valid is False
        assert "Invalid calculation_type" in error

    def test_validate_params_negative_amount(self, tax_tool: TaxCalculatorTool):
        """Test validation fails with negative amount."""
        valid, error = tax_tool.validate_params(
            calculation_type="vat", amount=-100
        )
        assert valid is False
        assert "negative" in error

    @pytest.mark.asyncio
    async def test_vat_calculation_standard_rate(self, tax_tool: TaxCalculatorTool):
        """Test VAT calculation with standard 19% rate."""
        result = await tax_tool.execute(
            calculation_type="vat",
            amount=100.00,
            vat_rate=0.19
        )

        assert result["success"] is True
        assert result["calculation_type"] == "vat"
        assert result["net_amount"] == 100.00
        assert result["vat_rate"] == 0.19
        assert result["vat_amount"] == 19.00
        assert result["gross_amount"] == 119.00
        assert result["legal_basis"] == "§12 UStG"

    @pytest.mark.asyncio
    async def test_vat_calculation_reduced_rate(self, tax_tool: TaxCalculatorTool):
        """Test VAT calculation with reduced 7% rate."""
        result = await tax_tool.execute(
            calculation_type="vat",
            amount=100.00,
            vat_rate=0.07
        )

        assert result["success"] is True
        assert result["vat_rate"] == 0.07
        assert result["vat_amount"] == 7.00
        assert result["gross_amount"] == 107.00

    @pytest.mark.asyncio
    async def test_vat_calculation_default_rate(self, tax_tool: TaxCalculatorTool):
        """Test VAT calculation defaults to 19%."""
        result = await tax_tool.execute(
            calculation_type="vat",
            amount=100.00
        )

        assert result["success"] is True
        assert result["vat_rate"] == 0.19
        assert result["vat_amount"] == 19.00

    @pytest.mark.asyncio
    async def test_input_tax_calculation(self, tax_tool: TaxCalculatorTool):
        """Test input tax (Vorsteuer) calculation from gross amount."""
        result = await tax_tool.execute(
            calculation_type="input_tax",
            amount=119.00,
            vat_rate=0.19
        )

        assert result["success"] is True
        assert result["calculation_type"] == "input_tax"
        assert result["gross_amount"] == 119.00
        assert result["input_tax"] == 19.00
        assert result["net_amount"] == 100.00
        assert result["legal_basis"] == "§15 Abs. 1 UStG"

    @pytest.mark.asyncio
    async def test_input_tax_reduced_rate(self, tax_tool: TaxCalculatorTool):
        """Test input tax calculation with 7% rate."""
        result = await tax_tool.execute(
            calculation_type="input_tax",
            amount=107.00,
            vat_rate=0.07
        )

        assert result["success"] is True
        assert result["input_tax"] == 7.00
        assert result["net_amount"] == 100.00

    @pytest.mark.asyncio
    async def test_reverse_charge_calculation(self, tax_tool: TaxCalculatorTool):
        """Test reverse charge calculation (§13b UStG)."""
        result = await tax_tool.execute(
            calculation_type="reverse_charge",
            amount=1000.00,
            vat_rate=0.19
        )

        assert result["success"] is True
        assert result["calculation_type"] == "reverse_charge"
        assert result["net_amount"] == 1000.00
        assert result["reverse_charge_vat"] == 190.00
        assert result["input_tax_deductible"] == 190.00
        assert result["net_effect"] == 0.0  # VAT charged and deducted
        assert result["legal_basis"] == "§13b UStG"

    @pytest.mark.asyncio
    async def test_afa_calculation_computer(self, tax_tool: TaxCalculatorTool):
        """Test AfA calculation for computer (3 years)."""
        result = await tax_tool.execute(
            calculation_type="afa",
            amount=1500.00,
            asset_type="computer"
        )

        assert result["success"] is True
        assert result["calculation_type"] == "afa"
        assert result["acquisition_cost"] == 1500.00
        assert result["afa_years"] == 3
        assert result["annual_afa"] == 500.00
        assert "depreciation_schedule" in result
        assert len(result["depreciation_schedule"]) == 3

    @pytest.mark.asyncio
    async def test_afa_calculation_vehicle(self, tax_tool: TaxCalculatorTool):
        """Test AfA calculation for vehicle (6 years)."""
        result = await tax_tool.execute(
            calculation_type="afa",
            amount=30000.00,
            asset_type="vehicle"
        )

        assert result["success"] is True
        assert result["afa_years"] == 6
        assert result["annual_afa"] == 5000.00

    @pytest.mark.asyncio
    async def test_afa_calculation_default(self, tax_tool: TaxCalculatorTool):
        """Test AfA calculation with default asset type (5 years)."""
        result = await tax_tool.execute(
            calculation_type="afa",
            amount=1000.00
        )

        assert result["success"] is True
        assert result["afa_years"] == 5
        assert result["asset_type"] == "default"

    @pytest.mark.asyncio
    async def test_afa_depreciation_schedule(self, tax_tool: TaxCalculatorTool):
        """Test depreciation schedule generation."""
        result = await tax_tool.execute(
            calculation_type="afa",
            amount=900.00,
            asset_type="computer"
        )

        schedule = result["depreciation_schedule"]
        assert len(schedule) == 3

        # Check first year
        assert schedule[0]["year"] == 1
        assert schedule[0]["depreciation"] == 300.00
        assert schedule[0]["remaining_value"] == 600.00

        # Check last year
        assert schedule[2]["year"] == 3
        assert schedule[2]["remaining_value"] == 0.0

    @pytest.mark.asyncio
    async def test_gwg_check_under_250(self, tax_tool: TaxCalculatorTool):
        """Test GWG check for amount under 250 EUR."""
        result = await tax_tool.execute(
            calculation_type="gwg_check",
            amount=200.00
        )

        assert result["success"] is True
        assert result["treatment"] == "sofort_abzugsfaehig"
        assert "§6 Abs. 2 EStG" in result["legal_basis"]

    @pytest.mark.asyncio
    async def test_gwg_check_250_to_800(self, tax_tool: TaxCalculatorTool):
        """Test GWG check for amount between 250-800 EUR."""
        result = await tax_tool.execute(
            calculation_type="gwg_check",
            amount=500.00
        )

        assert result["success"] is True
        assert result["is_gwg"] is True
        assert result["is_pool_eligible"] is True
        assert result["treatment"] == "gwg_oder_pool"

    @pytest.mark.asyncio
    async def test_gwg_check_over_800(self, tax_tool: TaxCalculatorTool):
        """Test GWG check for amount over 800 EUR."""
        result = await tax_tool.execute(
            calculation_type="gwg_check",
            amount=1000.00
        )

        assert result["success"] is True
        assert result["is_gwg"] is False
        assert result["treatment"] == "normale_afa"
        assert "§7 Abs. 1 EStG" in result["legal_basis"]

    @pytest.mark.asyncio
    async def test_rounding(self, tax_tool: TaxCalculatorTool):
        """Test proper rounding of calculated amounts."""
        result = await tax_tool.execute(
            calculation_type="vat",
            amount=33.33,
            vat_rate=0.19
        )

        assert result["success"] is True
        # Check proper rounding to 2 decimal places
        assert result["vat_amount"] == 6.33  # 33.33 * 0.19 = 6.3327 -> 6.33
        assert result["gross_amount"] == 39.66

    @pytest.mark.asyncio
    async def test_monthly_afa(self, tax_tool: TaxCalculatorTool):
        """Test monthly AfA calculation."""
        result = await tax_tool.execute(
            calculation_type="afa",
            amount=1200.00,
            asset_type="computer"
        )

        assert result["success"] is True
        assert result["annual_afa"] == 400.00
        assert result["monthly_afa"] == 33.33  # 400 / 12

    @pytest.mark.asyncio
    async def test_explanation_included(self, tax_tool: TaxCalculatorTool):
        """Test that results include explanations."""
        result = await tax_tool.execute(
            calculation_type="vat",
            amount=100.00
        )

        assert "explanation" in result
        assert len(result["explanation"]) > 0
