"""
Tests for RuleEngineTool.

Tests YAML-based Kontierung rule matching.
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from taskforce.infrastructure.tools.native.accounting.rule_engine_tool import (
    RuleEngineTool,
)


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    """Create temporary rules directory with test rules."""
    rules_path = tmp_path / "rules"
    rules_path.mkdir()

    # Create test kontierung_rules.yaml
    kontierung_rules = {
        "version": "1.0",
        "chart_of_accounts": "SKR03",
        "expense_categories": {
            "office_supplies": {
                "keywords": ["Bürobedarf", "Papier"],
                "debit_account": "4930",
                "debit_name": "Bürobedarf",
            },
            "it_equipment": {
                "keywords": ["Computer", "Laptop"],
                "conditions": [
                    {
                        "if_amount_below": 800,
                        "debit_account": "4985",
                        "debit_name": "GWG",
                    },
                    {
                        "if_amount_above": 800,
                        "debit_account": "0420",
                        "debit_name": "EDV-Anlagen",
                        "afa_years": 3,
                    },
                ],
            },
        },
        "vat_rules": {
            "standard_rate": {
                "rate": 0.19,
                "input_tax_account": "1576",
            },
        },
    }

    with open(rules_path / "kontierung_rules.yaml", "w", encoding="utf-8") as f:
        yaml.dump(kontierung_rules, f, allow_unicode=True)

    return rules_path


@pytest.fixture
def rule_tool(rules_dir: Path) -> RuleEngineTool:
    """Create RuleEngineTool with test rules."""
    return RuleEngineTool(rules_path=str(rules_dir))


@pytest.fixture
def rule_tool_no_rules(tmp_path: Path) -> RuleEngineTool:
    """Create RuleEngineTool with empty rules directory."""
    empty_dir = tmp_path / "empty_rules"
    empty_dir.mkdir()
    return RuleEngineTool(rules_path=str(empty_dir))


class TestRuleEngineTool:
    """Test suite for RuleEngineTool."""

    def test_tool_metadata(self, rule_tool: RuleEngineTool):
        """Test tool metadata properties."""
        assert rule_tool.name == "apply_kontierung_rules"
        assert "Kontierung" in rule_tool.description
        assert rule_tool.requires_approval is False

    def test_parameters_schema(self, rule_tool: RuleEngineTool):
        """Test parameter schema structure."""
        schema = rule_tool.parameters_schema
        assert schema["type"] == "object"
        assert "invoice_data" in schema["properties"]
        assert "chart_of_accounts" in schema["properties"]
        assert "invoice_data" in schema["required"]

    def test_validate_params_missing_invoice_data(self, rule_tool: RuleEngineTool):
        """Test validation fails without invoice_data."""
        valid, error = rule_tool.validate_params()
        assert valid is False
        assert "invoice_data" in error

    def test_validate_params_invalid_chart(self, rule_tool: RuleEngineTool):
        """Test validation fails with invalid chart."""
        valid, error = rule_tool.validate_params(
            invoice_data={},
            chart_of_accounts="INVALID"
        )
        assert valid is False
        assert "SKR03" in error or "SKR04" in error

    def test_validate_params_valid(self, rule_tool: RuleEngineTool):
        """Test validation passes with valid data."""
        valid, error = rule_tool.validate_params(
            invoice_data={"line_items": []},
            chart_of_accounts="SKR03"
        )
        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_office_supplies_kontierung(self, rule_tool: RuleEngineTool):
        """Test Kontierung for office supplies."""
        invoice = {
            "line_items": [
                {"description": "Bürobedarf für Büro", "net_amount": 50.00, "vat_rate": 0.19}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        assert result["rules_applied"] == 1
        assert len(result["booking_proposals"]) > 0

        # Find debit proposal
        debit_proposal = next(
            (p for p in result["booking_proposals"] if p.get("type") == "debit"), None
        )
        assert debit_proposal is not None
        assert debit_proposal["debit_account"] == "4930"

    @pytest.mark.asyncio
    async def test_gwg_under_threshold(self, rule_tool: RuleEngineTool):
        """Test GWG Kontierung for IT equipment under 800 EUR."""
        invoice = {
            "line_items": [
                {"description": "Laptop", "net_amount": 500.00, "vat_rate": 0.19}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        debit_proposal = next(
            (p for p in result["booking_proposals"] if p.get("type") == "debit"), None
        )
        assert debit_proposal is not None
        assert debit_proposal["debit_account"] == "4985"  # GWG account

    @pytest.mark.asyncio
    async def test_anlage_over_threshold(self, rule_tool: RuleEngineTool):
        """Test Anlage Kontierung for IT equipment over 800 EUR."""
        invoice = {
            "line_items": [
                {"description": "Computer Workstation", "net_amount": 1500.00, "vat_rate": 0.19}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        debit_proposal = next(
            (p for p in result["booking_proposals"] if p.get("type") == "debit"), None
        )
        assert debit_proposal is not None
        assert debit_proposal["debit_account"] == "0420"  # EDV-Anlagen
        assert debit_proposal.get("afa_years") == 3

    @pytest.mark.asyncio
    async def test_credit_account_generated(self, rule_tool: RuleEngineTool):
        """Test that credit account (Verbindlichkeiten) is generated."""
        invoice = {
            "line_items": [
                {"description": "Bürobedarf", "net_amount": 100.00, "vat_rate": 0.19}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        credit_proposal = next(
            (p for p in result["booking_proposals"] if p.get("type") == "credit"), None
        )
        assert credit_proposal is not None
        assert credit_proposal["credit_account"] == "1600"

    @pytest.mark.asyncio
    async def test_vat_account_included(self, rule_tool: RuleEngineTool):
        """Test that VAT account is included in proposals."""
        invoice = {
            "line_items": [
                {"description": "Bürobedarf", "net_amount": 100.00, "vat_rate": 0.19}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        debit_proposal = next(
            (p for p in result["booking_proposals"] if p.get("type") == "debit"), None
        )
        assert debit_proposal is not None
        assert debit_proposal.get("vat_account") == "1576"

    @pytest.mark.asyncio
    async def test_unmatched_items(self, rule_tool: RuleEngineTool):
        """Test handling of line items without matching rules."""
        invoice = {
            "line_items": [
                {"description": "Unbekannte Dienstleistung", "net_amount": 500.00}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        assert len(result["unmatched_items"]) > 0
        assert result["unmatched_items"][0]["reason"] == "No matching rule found"

    @pytest.mark.asyncio
    async def test_multiple_line_items(self, rule_tool: RuleEngineTool):
        """Test processing of multiple line items."""
        invoice = {
            "line_items": [
                {"description": "Bürobedarf", "net_amount": 50.00, "vat_rate": 0.19},
                {"description": "Computer", "net_amount": 600.00, "vat_rate": 0.19},
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        assert result["rules_applied"] == 2

    @pytest.mark.asyncio
    async def test_empty_line_items(self, rule_tool: RuleEngineTool):
        """Test handling of empty line items list."""
        invoice = {"line_items": []}

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        assert result["rules_applied"] == 0

    @pytest.mark.asyncio
    async def test_fallback_to_totals(self, rule_tool: RuleEngineTool):
        """Test fallback to invoice totals when no line items."""
        invoice = {
            "total_net": 100.00,
            "total_vat": 19.00,
            "vat_rate": 0.19,
            "description": "Bürobedarf",
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        # Should create proposal from totals

    @pytest.mark.asyncio
    async def test_rules_loaded_info(self, rule_tool: RuleEngineTool):
        """Test that loaded rules info is returned."""
        invoice = {"line_items": []}

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        assert "rules_loaded" in result
        assert "kontierung_rules" in result["rules_loaded"]

    @pytest.mark.asyncio
    async def test_no_rules_loaded(self, rule_tool_no_rules: RuleEngineTool):
        """Test behavior when no rules are loaded."""
        invoice = {
            "line_items": [
                {"description": "Bürobedarf", "net_amount": 50.00}
            ]
        }

        result = await rule_tool_no_rules.execute(invoice_data=invoice)

        assert result["success"] is True
        assert len(result["unmatched_items"]) > 0

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, rule_tool: RuleEngineTool):
        """Test that keyword matching is case insensitive."""
        invoice = {
            "line_items": [
                {"description": "BÜROBEDARF", "net_amount": 50.00, "vat_rate": 0.19}
            ]
        }

        result = await rule_tool.execute(invoice_data=invoice)

        assert result["success"] is True
        assert result["rules_applied"] == 1

    @pytest.mark.asyncio
    async def test_chart_of_accounts_skr04(self, rule_tool: RuleEngineTool):
        """Test SKR04 chart of accounts selection."""
        invoice = {
            "line_items": [
                {"description": "Bürobedarf", "net_amount": 50.00}
            ]
        }

        result = await rule_tool.execute(
            invoice_data=invoice,
            chart_of_accounts="SKR04"
        )

        assert result["success"] is True
        assert result["chart_of_accounts"] == "SKR04"
