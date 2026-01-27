"""
Unit Tests for Semantic Rule Engine

Tests the rule matching logic including vendor-only and vendor+item rules.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from accounting_agent.tools.semantic_rule_engine_tool import SemanticRuleEngineTool
from accounting_agent.domain.models import (
    AccountingRule,
    RuleType,
    RuleSource,
    MatchType,
)


class TestSemanticRuleEngine:
    """Tests for SemanticRuleEngineTool."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = MagicMock()
        service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        service.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
        service.cosine_similarity = MagicMock(return_value=0.85)
        return service

    def test_tool_properties(self):
        """Tool should have correct properties."""
        tool = SemanticRuleEngineTool()

        assert tool.name == "semantic_rule_engine"
        assert "semantic" in tool.description.lower()
        assert tool.requires_approval is False

    def test_validate_params_missing_invoice_data(self):
        """Should fail validation without invoice_data."""
        tool = SemanticRuleEngineTool()

        valid, error = tool.validate_params(chart_of_accounts="SKR03")

        assert valid is False
        assert "invoice_data" in error

    def test_validate_params_invalid_chart(self):
        """Should fail validation with invalid chart."""
        tool = SemanticRuleEngineTool()

        valid, error = tool.validate_params(
            invoice_data={"supplier_name": "Test"},
            chart_of_accounts="SKR99"
        )

        assert valid is False
        assert "SKR99" in error

    def test_validate_params_success(self):
        """Should pass validation with correct params."""
        tool = SemanticRuleEngineTool()

        valid, error = tool.validate_params(
            invoice_data={"supplier_name": "Test"},
            chart_of_accounts="SKR03"
        )

        assert valid is True
        assert error is None

    def test_matches_vendor_pattern_exact(self):
        """Should match exact vendor names."""
        tool = SemanticRuleEngineTool()

        assert tool._matches_vendor_pattern("Amazon Web Services", "Amazon Web Services")
        assert tool._matches_vendor_pattern("AMAZON WEB SERVICES", "Amazon Web Services")
        assert not tool._matches_vendor_pattern("Microsoft", "Amazon Web Services")

    def test_matches_vendor_pattern_regex(self):
        """Should match regex vendor patterns."""
        tool = SemanticRuleEngineTool()

        assert tool._matches_vendor_pattern("Microsoft Germany GmbH", "Microsoft.*")
        assert tool._matches_vendor_pattern("Microsoft Azure", "Microsoft.*")
        assert not tool._matches_vendor_pattern("Google Cloud", "Microsoft.*")

    def test_matches_vendor_pattern_any(self):
        """Wildcard pattern should match any vendor."""
        tool = SemanticRuleEngineTool()

        assert tool._matches_vendor_pattern("Any Vendor", ".*")
        assert tool._matches_vendor_pattern("Another Company", ".*")

    def test_parse_rule_source_valid(self):
        """Should parse valid rule source strings."""
        tool = SemanticRuleEngineTool()

        assert tool._parse_rule_source("manual") == RuleSource.MANUAL
        assert tool._parse_rule_source("auto_high_confidence") == RuleSource.AUTO_HIGH_CONFIDENCE
        assert tool._parse_rule_source("hitl_correction") == RuleSource.HITL_CORRECTION

    def test_parse_rule_source_invalid(self):
        """Should fallback to MANUAL for invalid source."""
        tool = SemanticRuleEngineTool()

        assert tool._parse_rule_source("invalid_source") == RuleSource.MANUAL

    def test_get_skr04_account_mapping(self):
        """Should convert SKR03 to SKR04 accounts."""
        tool = SemanticRuleEngineTool()
        tool._raw_rules = {
            "kontierung_rules": {
                "skr04_mapping": {
                    "4930": "6815",
                    "1576": "1406",
                }
            }
        }

        assert tool._get_skr04_account("4930") == "6815"
        assert tool._get_skr04_account("1576") == "1406"
        # Unknown account should return itself
        assert tool._get_skr04_account("9999") == "9999"


class TestSemanticRuleEngineAsync:
    """Async tests for SemanticRuleEngineTool."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = MagicMock()
        service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        service.embed_batch = AsyncMock(return_value=[[0.1] * 1536])
        service.cosine_similarity = MagicMock(return_value=0.85)
        return service

    @pytest.mark.asyncio
    async def test_execute_no_rules(self):
        """Should return empty results when no rules loaded."""
        tool = SemanticRuleEngineTool(rules_path="/nonexistent/path")

        result = await tool.execute(
            invoice_data={
                "supplier_name": "Test Vendor",
                "line_items": [
                    {"description": "Test Item", "net_amount": 100, "vat_rate": 0.19}
                ]
            }
        )

        assert result["success"] is True
        assert result["rules_applied"] == 0
        assert len(result["unmatched_items"]) == 1

    @pytest.mark.asyncio
    async def test_execute_creates_line_item_from_totals(self):
        """Should create line item from invoice totals if none provided."""
        tool = SemanticRuleEngineTool(rules_path="/nonexistent/path")

        result = await tool.execute(
            invoice_data={
                "supplier_name": "Test Vendor",
                "total_net": 100,
                "total_vat": 19,
                "vat_rate": 0.19,
                "description": "Service Invoice"
            }
        )

        assert result["success"] is True
        # Should have created one line item
        assert len(result["unmatched_items"]) == 1


class TestRuleMatching:
    """Tests for rule matching algorithm."""

    def test_accounting_rule_creation(self):
        """Should create AccountingRule with correct defaults."""
        rule = AccountingRule(
            rule_id="TEST-001",
            rule_type=RuleType.VENDOR_ONLY,
            vendor_pattern="Test Vendor",
            target_account="4930",
        )

        assert rule.rule_id == "TEST-001"
        assert rule.rule_type == RuleType.VENDOR_ONLY
        assert rule.priority == 100
        assert rule.similarity_threshold == 0.8
        assert rule.source == RuleSource.MANUAL
        assert rule.is_active is True

    def test_vendor_item_rule_with_patterns(self):
        """Should create vendor+item rule with patterns."""
        rule = AccountingRule(
            rule_id="TEST-002",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern=".*",
            item_patterns=["Bürobedarf", "Papier", "Toner"],
            target_account="4930",
            similarity_threshold=0.8,
        )

        assert rule.rule_type == RuleType.VENDOR_ITEM
        assert len(rule.item_patterns) == 3
        assert "Bürobedarf" in rule.item_patterns
