"""
Unit Tests for Vendor-Level Generalization

Tests the vendor account profile building and generalization matching logic
that allows the SemanticRuleEngineTool to infer accounts for unseen items
from vendors with a dominant booking pattern.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from accounting_agent.tools.semantic_rule_engine_tool import SemanticRuleEngineTool
from accounting_agent.domain.models import (
    AccountingRule,
    RuleType,
    RuleSource,
    RuleMatch,
    MatchType,
    VendorAccountProfile,
)


class TestBuildVendorAccountProfiles:
    """Tests for _build_vendor_account_profiles()."""

    def _make_tool_with_rules(self, rules: list[AccountingRule]) -> SemanticRuleEngineTool:
        """Create a tool with pre-loaded rules (bypass YAML loading)."""
        tool = SemanticRuleEngineTool(rules_path="/nonexistent")
        tool._rules = rules
        return tool

    def test_single_dominant_account(self):
        """5 rules all pointing to 4900 should create a profile."""
        rules = [
            AccountingRule(
                rule_id=f"HITL-{i}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern="Musterbetrieb",
                item_patterns=[item],
                target_account="4900",
                target_account_name="Sonstige betriebliche Aufwendungen",
                source=RuleSource.HITL_CORRECTION,
            )
            for i, item in enumerate([
                "Bitburger Pils",
                "Warsteiner Premium",
                "Coca Cola 0,5l",
                "Fanta Orange",
                "Mineralwasser",
            ])
        ]

        tool = self._make_tool_with_rules(rules)
        tool._build_vendor_account_profiles()

        assert len(tool._vendor_profiles) == 1
        profile = tool._vendor_profiles["musterbetrieb"]
        assert profile.dominant_account == "4900"
        assert profile.total_rules == 5
        assert profile.rules_for_dominant == 5
        assert profile.dominance_ratio == 1.0
        assert len(profile.all_item_patterns) == 5
        assert profile.dominant_account_name == "Sonstige betriebliche Aufwendungen"

    def test_below_min_rules(self):
        """2 rules should NOT create a profile (minimum is 3)."""
        rules = [
            AccountingRule(
                rule_id=f"HITL-{i}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern="SmallVendor",
                item_patterns=[f"Item {i}"],
                target_account="4900",
                source=RuleSource.HITL_CORRECTION,
            )
            for i in range(2)
        ]

        tool = self._make_tool_with_rules(rules)
        tool._build_vendor_account_profiles()

        assert len(tool._vendor_profiles) == 0

    def test_no_dominance(self):
        """Rules distributed across many accounts should NOT create a profile."""
        rules = [
            AccountingRule(
                rule_id=f"AUTO-{i}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern="DiverseVendor",
                item_patterns=[f"Item {i}"],
                target_account=f"{4900 + i}",
                source=RuleSource.AUTO_HIGH_CONFIDENCE,
            )
            for i in range(5)  # 5 rules, each different account → 20% each < 60%
        ]

        tool = self._make_tool_with_rules(rules)
        tool._build_vendor_account_profiles()

        assert len(tool._vendor_profiles) == 0

    def test_mixed_accounts_with_dominance(self):
        """4/5 rules to same account (80%) should create a profile."""
        rules = [
            AccountingRule(
                rule_id=f"HITL-{i}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern="MixedVendor",
                item_patterns=[f"Item {i}"],
                target_account="4900" if i < 4 else "4930",
                source=RuleSource.HITL_CORRECTION,
            )
            for i in range(5)
        ]

        tool = self._make_tool_with_rules(rules)
        tool._build_vendor_account_profiles()

        assert len(tool._vendor_profiles) == 1
        profile = tool._vendor_profiles["mixedvendor"]
        assert profile.dominant_account == "4900"
        assert profile.dominance_ratio == 0.8

    def test_ignores_manual_rules(self):
        """Only auto_high_confidence and hitl_correction rules are used."""
        rules = [
            AccountingRule(
                rule_id=f"MANUAL-{i}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern="ManualVendor",
                item_patterns=[f"Item {i}"],
                target_account="4900",
                source=RuleSource.MANUAL,
            )
            for i in range(5)
        ]

        tool = self._make_tool_with_rules(rules)
        tool._build_vendor_account_profiles()

        assert len(tool._vendor_profiles) == 0

    def test_ignores_vendor_only_rules(self):
        """Only VENDOR_ITEM rules are used for profiles."""
        rules = [
            AccountingRule(
                rule_id=f"HITL-{i}",
                rule_type=RuleType.VENDOR_ONLY,
                vendor_pattern="VendorOnlyVendor",
                target_account="4900",
                source=RuleSource.HITL_CORRECTION,
            )
            for i in range(5)
        ]

        tool = self._make_tool_with_rules(rules)
        tool._build_vendor_account_profiles()

        assert len(tool._vendor_profiles) == 0


class TestTryVendorGeneralization:
    """Tests for _try_vendor_generalization()."""

    def _make_tool_with_profile(
        self, vendor: str, account: str, ratio: float = 1.0
    ) -> SemanticRuleEngineTool:
        """Create a tool with a pre-built vendor profile."""
        tool = SemanticRuleEngineTool(rules_path="/nonexistent")
        tool._vendor_profiles[vendor.lower()] = VendorAccountProfile(
            vendor_pattern=vendor,
            dominant_account=account,
            dominant_account_name="Sonstige betriebliche Aufwendungen",
            total_rules=5,
            rules_for_dominant=int(5 * ratio),
            dominance_ratio=ratio,
            all_item_patterns=["Bitburger Pils", "Warsteiner", "Coca Cola"],
        )
        return tool

    def test_returns_vendor_generalized_match(self):
        """Should return VENDOR_GENERALIZED match for known vendor."""
        tool = self._make_tool_with_profile("Musterbetrieb", "4900")

        result = tool._try_vendor_generalization("Musterbetrieb GmbH", "Stiegl Goldbräu")

        assert result is not None
        assert result.match_type == MatchType.VENDOR_GENERALIZED
        assert result.rule.target_account == "4900"
        assert "VENDOR-GEN" in result.rule.rule_id

    def test_similarity_calculation(self):
        """Similarity should be base_score * dominance_ratio."""
        tool = self._make_tool_with_profile("TestVendor", "4900", ratio=0.8)

        result = tool._try_vendor_generalization("TestVendor", "New Item")

        assert result is not None
        expected = SemanticRuleEngineTool.VENDOR_GENERALIZATION_BASE_SCORE * 0.8
        assert abs(result.similarity_score - expected) < 0.001

    def test_returns_none_for_unknown_vendor(self):
        """Should return None for vendor without profile."""
        tool = self._make_tool_with_profile("Musterbetrieb", "4900")

        result = tool._try_vendor_generalization("Unknown Vendor", "Some item")

        assert result is None

    def test_returns_none_when_no_profiles(self):
        """Should return None when no vendor profiles exist."""
        tool = SemanticRuleEngineTool(rules_path="/nonexistent")

        result = tool._try_vendor_generalization("Any Vendor", "Any item")

        assert result is None


class TestVendorGeneralizationDoesNotOverrideExact:
    """Test that exact matches take priority over vendor generalization."""

    @pytest.mark.asyncio
    async def test_exact_match_wins_over_generalization(self):
        """Exact item match should be returned, not vendor generalization."""
        tool = SemanticRuleEngineTool(rules_path="/nonexistent")

        # Create a rule that exactly matches "Bitburger Pils"
        exact_rule = AccountingRule(
            rule_id="HITL-exact",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern="Musterbetrieb",
            item_patterns=["Bitburger Pils"],
            target_account="4900",
            target_account_name="Sonstige betriebliche Aufwendungen",
            priority=75,
            source=RuleSource.HITL_CORRECTION,
        )
        tool._rules = [exact_rule]
        tool._rules_loaded = True
        tool._learned_rules_mtime = float("inf")  # Prevent reload

        # Also add a vendor profile
        tool._vendor_profiles["musterbetrieb"] = VendorAccountProfile(
            vendor_pattern="Musterbetrieb",
            dominant_account="4900",
            dominant_account_name="Sonstige betriebliche Aufwendungen",
            total_rules=5,
            rules_for_dominant=5,
            dominance_ratio=1.0,
            all_item_patterns=["Bitburger Pils", "Warsteiner"],
        )

        result = await tool._match_item(
            supplier_name="Musterbetrieb GmbH",
            line_item={"description": "Bitburger Pils 0,5l"},
            chart="SKR03",
        )

        assert result is not None
        assert result.match_type == MatchType.EXACT
        assert result.rule.rule_id == "HITL-exact"


class TestMusterbetriebStieglScenario:
    """End-to-end test for the specific Stiegl Goldbräu scenario."""

    @pytest.mark.asyncio
    async def test_stiegl_goldbraeu_via_vendor_generalization(self):
        """Stiegl Goldbräu should be assigned to 4900 via vendor generalization.

        Given: Musterbetrieb has 5 learned rules, all pointing to 4900
        When: A new item "Stiegl Goldbräu" is processed
        Then: It should be matched via vendor generalization to 4900
        """
        tool = SemanticRuleEngineTool(rules_path="/nonexistent")

        # Simulate learned rules for Musterbetrieb
        items = ["Bitburger Pils", "Warsteiner Premium", "Coca Cola 0,5l",
                 "Fanta Orange", "Mineralwasser still"]
        rules = [
            AccountingRule(
                rule_id=f"HITL-{i}",
                rule_type=RuleType.VENDOR_ITEM,
                vendor_pattern="Musterbetrieb",
                item_patterns=[item],
                target_account="4900",
                target_account_name="Sonstige betriebliche Aufwendungen",
                priority=75,
                source=RuleSource.HITL_CORRECTION,
            )
            for i, item in enumerate(items)
        ]
        tool._rules = rules

        # Build profiles (normally called in _load_rules)
        tool._build_vendor_account_profiles()
        tool._rules_loaded = True
        tool._learned_rules_mtime = float("inf")  # Prevent reload

        # Now process "Stiegl Goldbräu" - not in any learned rule
        result = await tool.execute(
            invoice_data={
                "supplier_name": "Musterbetrieb GmbH & Co. KG",
                "line_items": [
                    {
                        "description": "Stiegl Goldbräu 0,5l",
                        "net_amount": 2.50,
                        "vat_rate": 0.19,
                        "vat_amount": 0.48,
                    }
                ],
            }
        )

        assert result["success"] is True
        assert result["rules_applied"] == 1
        assert len(result["unmatched_items"]) == 0

        # Verify the booking proposal
        debit_proposals = [p for p in result["booking_proposals"] if p.get("type") == "debit"]
        assert len(debit_proposals) == 1
        assert debit_proposals[0]["debit_account"] == "4900"
        assert debit_proposals[0]["match_type"] == "vendor_generalized"

        # Verify generalization info is present
        assert "generalization_info" in debit_proposals[0]
        gen_info = debit_proposals[0]["generalization_info"]
        assert gen_info["dominance_ratio"] == 1.0
        assert gen_info["total_rules"] == 5

        # Verify rule match details
        assert len(result["rule_matches"]) == 1
        assert result["rule_matches"][0]["match_type"] == "vendor_generalized"
