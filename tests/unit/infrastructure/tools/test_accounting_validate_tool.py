"""Tests for AccountingValidateTool."""

import pytest

from taskforce.infrastructure.tools.native.accounting_validate_tool import (
    AccountingValidateTool,
    _map_invoice_fields,
    _normalize_vat_id,
)


@pytest.fixture
def tool() -> AccountingValidateTool:
    return AccountingValidateTool()


# -- VAT ID normalization --


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("DE123456789", "DE123456789"),
        ("USt-IDNr. DE 123456789", "DE123456789"),
        ("UID ATU12345678", "ATU12345678"),
        ("12/345/67890", "12/345/67890"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_vat_id(raw: str | None, expected: str | None) -> None:
    assert _normalize_vat_id(raw) == expected


# -- Field mapping --


def test_map_invoice_fields_alternative_names() -> None:
    data = _map_invoice_fields({
        "total_net": 100.0,
        "total_gross": 119.0,
        "total_vat": 19.0,
        "sender_name": "Test GmbH",
        "supplier_vat_id": "DE123456789",
    })
    assert data["net_amount"] == 100.0
    assert data["gross_amount"] == 119.0
    assert data["vat_amount"] == 19.0
    assert data["supplier_name"] == "Test GmbH"
    assert data["vat_id"] == "DE123456789"


def test_map_invoice_fields_line_items_to_quantity() -> None:
    data = _map_invoice_fields({
        "line_items": [
            {"description": "Widget A"},
            {"description": "Widget B"},
        ],
    })
    assert "quantity_description" in data
    assert "Widget A" in data["quantity_description"]


def test_map_invoice_fields_vat_breakdown_to_rate() -> None:
    data = _map_invoice_fields({
        "vat_breakdown": [
            {"rate": 0.19, "net_amount": 100},
            {"rate": 0.07, "net_amount": 50},
        ],
    })
    assert data["vat_rate"] == "0.07,0.19"


# -- Full invoice validation --


@pytest.mark.asyncio
async def test_compliant_invoice(tool: AccountingValidateTool) -> None:
    result = await tool.execute(
        invoice_data={
            "supplier_name": "Muster GmbH",
            "supplier_address": "Musterstr. 1, 12345 Berlin",
            "recipient_name": "Kunde AG",
            "vat_id": "DE123456789",
            "invoice_date": "2025-03-21",
            "invoice_number": "RE-2025-001",
            "quantity_description": "Beratungsleistung Maerz 2025",
            "delivery_date": "2025-03-15",
            "net_amount": 1000.00,
            "vat_rate": 0.19,
            "vat_amount": 190.00,
            "gross_amount": 1190.00,
        }
    )
    assert result["success"] is True
    assert result["is_compliant"] is True
    assert result["missing_fields"] == []
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_missing_mandatory_fields(tool: AccountingValidateTool) -> None:
    result = await tool.execute(
        invoice_data={
            "supplier_name": "Muster GmbH",
            "invoice_date": "2025-03-21",
            # Missing most mandatory fields
        }
    )
    assert result["success"] is True
    assert result["is_compliant"] is False
    assert len(result["errors"]) > 0
    assert len(result["missing_fields"]) > 0


@pytest.mark.asyncio
async def test_small_invoice_reduced_requirements(
    tool: AccountingValidateTool,
) -> None:
    """Kleinbetragsrechnung (< 250 EUR) needs fewer fields."""
    result = await tool.execute(
        invoice_data={
            "supplier_name": "Kiosk",
            "invoice_date": "2025-03-21",
            "quantity_description": "Bueromaterial",
            "gross_amount": 49.90,
            "vat_rate": 0.19,
        }
    )
    assert result["success"] is True
    assert result["is_compliant"] is True
    assert result["is_small_invoice"] is True
    assert result["legal_basis"] == "§33 UStDV (Kleinbetragsrechnung)"


@pytest.mark.asyncio
async def test_strict_mode_promotes_warnings(
    tool: AccountingValidateTool,
) -> None:
    """In strict mode, delivery_date (normally a warning) becomes an error."""
    result = await tool.execute(
        invoice_data={
            "supplier_name": "Muster GmbH",
            "supplier_address": "Musterstr. 1",
            "recipient_name": "Kunde AG",
            "vat_id": "DE123456789",
            "invoice_date": "2025-03-21",
            "invoice_number": "RE-2025-001",
            "quantity_description": "Beratung",
            "net_amount": 1000.00,
            "vat_rate": 0.19,
            "vat_amount": 190.00,
            "gross_amount": 1190.00,
            # delivery_date intentionally missing
        },
        strict_mode=True,
    )
    assert result["success"] is True
    assert result["is_compliant"] is False
    assert "delivery_date" in result["missing_fields"]


@pytest.mark.asyncio
async def test_vat_consistency_warning(tool: AccountingValidateTool) -> None:
    """VAT amount inconsistency should produce a warning."""
    result = await tool.execute(
        invoice_data={
            "supplier_name": "Muster GmbH",
            "supplier_address": "Musterstr. 1",
            "recipient_name": "Kunde AG",
            "vat_id": "DE123456789",
            "invoice_date": "2025-03-21",
            "invoice_number": "RE-2025-001",
            "quantity_description": "Beratung",
            "delivery_date": "2025-03-15",
            "net_amount": 1000.00,
            "vat_rate": 0.19,
            "vat_amount": 250.00,  # Wrong! Should be 190
            "gross_amount": 1250.00,
        }
    )
    assert result["success"] is True
    vat_warnings = [w for w in result["warnings"] if w["field"] == "vat_calculation"]
    assert len(vat_warnings) == 1


@pytest.mark.asyncio
async def test_tool_protocol_properties(tool: AccountingValidateTool) -> None:
    assert tool.name == "accounting_validate"
    assert "§14 UStG" in tool.description
    assert tool.requires_approval is False
    assert tool.supports_parallelism is True
