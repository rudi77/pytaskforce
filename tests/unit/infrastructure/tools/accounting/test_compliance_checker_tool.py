"""
Tests for ComplianceCheckerTool.

Tests validation of invoices against §14 UStG requirements.
"""

import pytest

from taskforce.infrastructure.tools.native.accounting.compliance_checker_tool import (
    ComplianceCheckerTool,
)


@pytest.fixture
def compliance_tool() -> ComplianceCheckerTool:
    """Create ComplianceCheckerTool instance."""
    return ComplianceCheckerTool()


@pytest.fixture
def valid_invoice_data() -> dict:
    """Create valid invoice data with all mandatory fields."""
    return {
        "supplier_name": "Test GmbH",
        "supplier_address": "Teststraße 1, 12345 Berlin",
        "recipient_name": "Kunde AG",
        "recipient_address": "Kundenweg 5, 54321 München",
        "vat_id": "DE123456789",
        "invoice_number": "RE-2024-001",
        "invoice_date": "2024-01-15",
        "quantity_description": "Beratungsleistung Januar 2024",
        "delivery_date": "2024-01-31",
        "net_amount": 1000.00,
        "vat_rate": 0.19,
        "vat_amount": 190.00,
        "gross_amount": 1190.00,
    }


@pytest.fixture
def small_invoice_data() -> dict:
    """Create valid small invoice data (Kleinbetragsrechnung)."""
    return {
        "supplier_name": "Kleiner Laden",
        "invoice_date": "2024-01-15",
        "quantity_description": "Bürobedarf",
        "gross_amount": 50.00,
        "vat_rate": 0.19,
    }


class TestComplianceCheckerTool:
    """Test suite for ComplianceCheckerTool."""

    def test_tool_metadata(self, compliance_tool: ComplianceCheckerTool):
        """Test tool metadata properties."""
        assert compliance_tool.name == "check_compliance"
        assert "§14 UStG" in compliance_tool.description
        assert compliance_tool.requires_approval is False

    def test_parameters_schema(self, compliance_tool: ComplianceCheckerTool):
        """Test parameter schema structure."""
        schema = compliance_tool.parameters_schema
        assert schema["type"] == "object"
        assert "invoice_data" in schema["properties"]
        assert "strict_mode" in schema["properties"]
        assert "invoice_data" in schema["required"]

    def test_validate_params_missing_invoice_data(
        self, compliance_tool: ComplianceCheckerTool
    ):
        """Test validation fails without invoice_data."""
        valid, error = compliance_tool.validate_params()
        assert valid is False
        assert "invoice_data" in error

    def test_validate_params_invalid_type(
        self, compliance_tool: ComplianceCheckerTool
    ):
        """Test validation fails with non-dict invoice_data."""
        valid, error = compliance_tool.validate_params(invoice_data="not a dict")
        assert valid is False
        assert "dictionary" in error

    def test_validate_params_valid(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test validation passes with valid data."""
        valid, error = compliance_tool.validate_params(invoice_data=valid_invoice_data)
        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_compliant_invoice(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test validation of compliant invoice."""
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert result["success"] is True
        assert result["is_compliant"] is True
        assert len(result["errors"]) == 0
        assert result["legal_basis"] == "§14 Abs. 4 UStG"

    @pytest.mark.asyncio
    async def test_missing_supplier_name(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test validation detects missing supplier name."""
        del valid_invoice_data["supplier_name"]
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert result["success"] is True
        assert result["is_compliant"] is False
        assert "supplier_name" in result["missing_fields"]
        assert any(e["field"] == "supplier_name" for e in result["errors"])

    @pytest.mark.asyncio
    async def test_missing_vat_id(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test validation detects missing VAT ID."""
        del valid_invoice_data["vat_id"]
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert result["success"] is True
        assert result["is_compliant"] is False
        assert "vat_id" in result["missing_fields"]

    @pytest.mark.asyncio
    async def test_invalid_vat_id_format(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test validation warns on invalid VAT ID format."""
        valid_invoice_data["vat_id"] = "INVALID123"
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert result["success"] is True
        # Should produce warning but not error
        assert any(w.get("field") == "vat_id" for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_valid_tax_number(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test validation accepts valid German tax number format."""
        valid_invoice_data["vat_id"] = "12/345/67890"
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert result["success"] is True
        # Tax number format should be accepted

    @pytest.mark.asyncio
    async def test_small_invoice_detection(
        self, compliance_tool: ComplianceCheckerTool, small_invoice_data: dict
    ):
        """Test detection of Kleinbetragsrechnung."""
        result = await compliance_tool.execute(invoice_data=small_invoice_data)

        assert result["success"] is True
        assert result["is_small_invoice"] is True
        assert result["legal_basis"] == "§33 UStDV (Kleinbetragsrechnung)"
        # Small invoices have reduced requirements
        assert result["is_compliant"] is True

    @pytest.mark.asyncio
    async def test_small_invoice_threshold(
        self, compliance_tool: ComplianceCheckerTool, small_invoice_data: dict
    ):
        """Test small invoice threshold detection."""
        # Just under threshold
        small_invoice_data["gross_amount"] = 250.00
        result = await compliance_tool.execute(invoice_data=small_invoice_data)
        assert result["is_small_invoice"] is True

        # Over threshold
        small_invoice_data["gross_amount"] = 250.01
        result = await compliance_tool.execute(invoice_data=small_invoice_data)
        assert result["is_small_invoice"] is False

    @pytest.mark.asyncio
    async def test_vat_calculation_check(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test VAT calculation consistency check."""
        # Create inconsistent VAT
        valid_invoice_data["vat_amount"] = 200.00  # Should be 190.00
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert result["success"] is True
        # Should produce warning about VAT inconsistency
        assert any("vat_calculation" in str(w) for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_strict_mode(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test strict mode converts warnings to errors."""
        del valid_invoice_data["delivery_date"]

        # Without strict mode - should be warning
        result_normal = await compliance_tool.execute(
            invoice_data=valid_invoice_data, strict_mode=False
        )

        # With strict mode - should be error
        result_strict = await compliance_tool.execute(
            invoice_data=valid_invoice_data, strict_mode=True
        )

        # In normal mode, missing delivery_date is a warning
        # In strict mode, it becomes an error
        assert result_strict["is_compliant"] is False

    @pytest.mark.asyncio
    async def test_summary_generation(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test summary generation for compliant invoice."""
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert "summary" in result
        assert "§14 UStG" in result["summary"]

    @pytest.mark.asyncio
    async def test_legal_references_in_errors(
        self, compliance_tool: ComplianceCheckerTool, valid_invoice_data: dict
    ):
        """Test that errors include legal references."""
        del valid_invoice_data["invoice_number"]
        result = await compliance_tool.execute(invoice_data=valid_invoice_data)

        assert len(result["errors"]) > 0
        error = next(e for e in result["errors"] if e["field"] == "invoice_number")
        assert "§14 Abs. 4 Nr. 4 UStG" in error["legal_reference"]
