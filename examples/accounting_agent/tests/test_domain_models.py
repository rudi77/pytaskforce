"""
Unit Tests for Domain Models

Tests the dataclasses and enums in the domain layer.
"""

import pytest
from decimal import Decimal
from datetime import date

from accounting_agent.domain.models import (
    # Core models
    Invoice,
    LineItem,
    BookingProposal,
    ComplianceFields,
    # Semantic rules models
    AccountingRule,
    RuleType,
    RuleSource,
    RuleMatch,
    MatchType,
    # Confidence models
    ConfidenceSignals,
    ConfidenceResult,
    ConfidenceRecommendation,
    HardGate,
    # Workflow models
    WorkflowState,
    WorkflowStateType,
)


class TestEnums:
    """Tests for enum types."""

    def test_rule_type_values(self):
        """RuleType should have correct values."""
        assert RuleType.VENDOR_ONLY.value == "vendor_only"
        assert RuleType.VENDOR_ITEM.value == "vendor_item"

    def test_rule_source_values(self):
        """RuleSource should have correct values."""
        assert RuleSource.MANUAL.value == "manual"
        assert RuleSource.AUTO_HIGH_CONFIDENCE.value == "auto_high_confidence"
        assert RuleSource.HITL_CORRECTION.value == "hitl_correction"

    def test_match_type_values(self):
        """MatchType should have correct values."""
        assert MatchType.EXACT.value == "exact"
        assert MatchType.SEMANTIC.value == "semantic"

    def test_confidence_recommendation_values(self):
        """ConfidenceRecommendation should have correct values."""
        assert ConfidenceRecommendation.AUTO_BOOK.value == "auto_book"
        assert ConfidenceRecommendation.HITL_REVIEW.value == "hitl_review"

    def test_workflow_state_type_values(self):
        """WorkflowStateType should have all expected states."""
        states = [e.value for e in WorkflowStateType]
        assert "ingestion" in states
        assert "rule_matching" in states
        assert "rag_fallback" in states
        assert "confidence_check" in states
        assert "review_pending" in states
        assert "finalization" in states
        assert "completed" in states
        assert "error" in states


class TestAccountingRule:
    """Tests for AccountingRule dataclass."""

    def test_vendor_only_rule(self):
        """Should create vendor-only rule correctly."""
        rule = AccountingRule(
            rule_id="VR-001",
            rule_type=RuleType.VENDOR_ONLY,
            vendor_pattern="Amazon Web Services",
            target_account="6805",
        )

        assert rule.rule_id == "VR-001"
        assert rule.rule_type == RuleType.VENDOR_ONLY
        assert rule.vendor_pattern == "Amazon Web Services"
        assert rule.target_account == "6805"
        assert rule.item_patterns == []
        assert rule.priority == 100
        assert rule.is_active is True

    def test_vendor_item_rule(self):
        """Should create vendor+item rule correctly."""
        rule = AccountingRule(
            rule_id="SR-001",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern=".*",
            item_patterns=["Bürobedarf", "Papier"],
            target_account="4930",
            similarity_threshold=0.85,
        )

        assert rule.rule_type == RuleType.VENDOR_ITEM
        assert len(rule.item_patterns) == 2
        assert rule.similarity_threshold == 0.85

    def test_rule_with_metadata(self):
        """Should handle rule metadata correctly."""
        rule = AccountingRule(
            rule_id="TEST-001",
            rule_type=RuleType.VENDOR_ONLY,
            vendor_pattern="Test",
            target_account="4930",
            source=RuleSource.HITL_CORRECTION,
            version=2,
            legal_basis="§4 Abs. 4 EStG",
            created_at="2024-01-01T00:00:00Z",
        )

        assert rule.source == RuleSource.HITL_CORRECTION
        assert rule.version == 2
        assert rule.legal_basis == "§4 Abs. 4 EStG"
        assert rule.created_at == "2024-01-01T00:00:00Z"


class TestRuleMatch:
    """Tests for RuleMatch dataclass."""

    def test_exact_match(self):
        """Should create exact match result."""
        rule = AccountingRule(
            rule_id="VR-001",
            rule_type=RuleType.VENDOR_ONLY,
            vendor_pattern="Test",
            target_account="4930",
        )
        match = RuleMatch(
            rule=rule,
            match_type=MatchType.EXACT,
            similarity_score=1.0,
        )

        assert match.match_type == MatchType.EXACT
        assert match.similarity_score == 1.0
        assert match.is_ambiguous is False

    def test_semantic_match(self):
        """Should create semantic match result."""
        rule = AccountingRule(
            rule_id="SR-001",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern=".*",
            target_account="4930",
            item_patterns=["Bürobedarf"],
        )
        match = RuleMatch(
            rule=rule,
            match_type=MatchType.SEMANTIC,
            similarity_score=0.87,
            matched_item_pattern="Bürobedarf",
        )

        assert match.match_type == MatchType.SEMANTIC
        assert match.similarity_score == 0.87
        assert match.matched_item_pattern == "Bürobedarf"

    def test_ambiguous_match(self):
        """Should handle ambiguous matches."""
        rule1 = AccountingRule(
            rule_id="SR-001",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern=".*",
            target_account="4930",
        )
        rule2 = AccountingRule(
            rule_id="SR-002",
            rule_type=RuleType.VENDOR_ITEM,
            vendor_pattern=".*",
            target_account="4940",
        )

        match1 = RuleMatch(
            rule=rule1,
            match_type=MatchType.SEMANTIC,
            similarity_score=0.85,
        )
        match2 = RuleMatch(
            rule=rule2,
            match_type=MatchType.SEMANTIC,
            similarity_score=0.83,
        )

        match1.is_ambiguous = True
        match1.alternative_matches = [match2]

        assert match1.is_ambiguous is True
        assert len(match1.alternative_matches) == 1


class TestConfidenceModels:
    """Tests for confidence-related models."""

    def test_confidence_signals(self):
        """Should create confidence signals."""
        signals = ConfidenceSignals(
            rule_type_score=1.0,
            similarity_score=0.9,
            uniqueness_score=1.0,
            historical_score=0.8,
            extraction_score=0.95,
        )

        assert signals.rule_type_score == 1.0
        assert signals.similarity_score == 0.9

    def test_hard_gate(self):
        """Should create hard gate."""
        gate = HardGate(
            gate_type="new_vendor",
            triggered=True,
            reason="Erster Beleg von diesem Lieferanten",
        )

        assert gate.gate_type == "new_vendor"
        assert gate.triggered is True

    def test_confidence_result(self):
        """Should create confidence result."""
        signals = ConfidenceSignals()
        result = ConfidenceResult(
            overall_confidence=0.85,
            signals=signals,
            recommendation=ConfidenceRecommendation.HITL_REVIEW,
            explanation="Confidence below threshold",
        )

        assert result.overall_confidence == 0.85
        assert result.recommendation == ConfidenceRecommendation.HITL_REVIEW
        assert result.auto_book_threshold == 0.95


class TestWorkflowState:
    """Tests for WorkflowState dataclass."""

    def test_initial_state(self):
        """Should create initial workflow state."""
        state = WorkflowState(
            state=WorkflowStateType.INGESTION,
            invoice_id="INV-001",
            session_id="SESSION-001",
        )

        assert state.state == WorkflowStateType.INGESTION
        assert state.invoice_id == "INV-001"
        assert state.hitl_required is False

    def test_hitl_required_state(self):
        """Should handle HITL required state."""
        state = WorkflowState(
            state=WorkflowStateType.REVIEW_PENDING,
            invoice_id="INV-001",
            session_id="SESSION-001",
            confidence=0.85,
            hitl_required=True,
            hitl_reason="Confidence below threshold",
        )

        assert state.state == WorkflowStateType.REVIEW_PENDING
        assert state.hitl_required is True
        assert state.hitl_reason is not None


class TestCoreModels:
    """Tests for core invoice models (existing)."""

    def test_line_item(self):
        """Should create line item."""
        item = LineItem(
            description="Kopierpapier A4",
            quantity=Decimal("10"),
            unit_price=Decimal("5.00"),
            net_amount=Decimal("50.00"),
            vat_rate=Decimal("0.19"),
            vat_amount=Decimal("9.50"),
        )

        assert item.description == "Kopierpapier A4"
        assert item.net_amount == Decimal("50.00")

    def test_invoice(self):
        """Should create invoice."""
        invoice = Invoice(
            invoice_id="INV-001",
            supplier_name="Bürobedarf GmbH",
            invoice_number="2024-001",
            invoice_date=date(2024, 1, 15),
            total_gross=Decimal("119.00"),
            total_net=Decimal("100.00"),
            total_vat=Decimal("19.00"),
        )

        assert invoice.invoice_id == "INV-001"
        assert invoice.supplier_name == "Bürobedarf GmbH"
        assert invoice.currency == "EUR"
