"""
Unit Tests for Confidence Calculator

Tests the weighted confidence evaluation and hard gate logic.
"""

import pytest
from decimal import Decimal

from accounting_agent.domain.confidence import ConfidenceCalculator
from accounting_agent.domain.models import (
    ConfidenceRecommendation,
)


class TestConfidenceCalculator:
    """Tests for ConfidenceCalculator."""

    def test_default_weights_sum_to_one(self):
        """Default weights should sum to 1.0."""
        calc = ConfidenceCalculator()
        weight_sum = sum(calc._weights.values())
        assert abs(weight_sum - 1.0) < 0.001

    def test_auto_book_on_high_confidence(self):
        """High confidence should result in AUTO_BOOK recommendation."""
        calc = ConfidenceCalculator(auto_book_threshold=0.95)

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_only",
                "similarity_score": 1.0,
            },
            extraction_score=1.0,
            historical_hit_rate=1.0,
            is_new_vendor=False,
            invoice_amount=Decimal("100.00"),
            target_account="4930",
        )

        assert result.recommendation == ConfidenceRecommendation.AUTO_BOOK
        assert result.overall_confidence >= 0.95

    def test_hitl_review_on_low_confidence(self):
        """Low confidence should result in HITL_REVIEW recommendation."""
        calc = ConfidenceCalculator(auto_book_threshold=0.95)

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_item",
                "similarity_score": 0.5,
            },
            extraction_score=0.7,
            historical_hit_rate=0.5,
            is_new_vendor=False,
            invoice_amount=Decimal("100.00"),
            target_account="4930",
        )

        assert result.recommendation == ConfidenceRecommendation.HITL_REVIEW
        assert result.overall_confidence < 0.95

    def test_new_vendor_triggers_hitl(self):
        """New vendor hard gate should always trigger HITL."""
        calc = ConfidenceCalculator()

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_only",
                "similarity_score": 1.0,
            },
            extraction_score=1.0,
            historical_hit_rate=1.0,
            is_new_vendor=True,
            invoice_amount=Decimal("100.00"),
            target_account="4930",
        )

        assert result.recommendation == ConfidenceRecommendation.HITL_REVIEW
        assert any(g.gate_type == "new_vendor" and g.triggered for g in result.hard_gates_triggered)

    def test_high_amount_triggers_hitl(self):
        """High amount hard gate should trigger HITL."""
        calc = ConfidenceCalculator(
            hard_gate_config={
                "new_vendor": True,
                "high_amount_threshold": Decimal("5000.00"),
                "critical_accounts": [],
            }
        )

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_only",
                "similarity_score": 1.0,
            },
            extraction_score=1.0,
            historical_hit_rate=1.0,
            is_new_vendor=False,
            invoice_amount=Decimal("6000.00"),
            target_account="4930",
        )

        assert result.recommendation == ConfidenceRecommendation.HITL_REVIEW
        assert any(g.gate_type == "high_amount" and g.triggered for g in result.hard_gates_triggered)

    def test_critical_account_triggers_hitl(self):
        """Critical account hard gate should trigger HITL."""
        calc = ConfidenceCalculator(
            hard_gate_config={
                "new_vendor": False,
                "high_amount_threshold": Decimal("10000.00"),
                "critical_accounts": ["1800", "2100"],
            }
        )

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_only",
                "similarity_score": 1.0,
            },
            extraction_score=1.0,
            historical_hit_rate=1.0,
            is_new_vendor=False,
            invoice_amount=Decimal("100.00"),
            target_account="1800",
        )

        assert result.recommendation == ConfidenceRecommendation.HITL_REVIEW
        assert any(g.gate_type == "critical_account" and g.triggered for g in result.hard_gates_triggered)

    def test_rag_suggestion_lower_confidence(self):
        """RAG suggestions should have lower rule_type score."""
        calc = ConfidenceCalculator()

        result = calc.calculate(
            is_rag_suggestion=True,
            rag_confidence=0.8,
            extraction_score=1.0,
            historical_hit_rate=0.8,
            is_new_vendor=False,
            invoice_amount=Decimal("100.00"),
            target_account="4930",
        )

        assert result.signals.rule_type_score == 0.5
        assert result.signals.similarity_score == 0.8

    def test_weight_normalization(self):
        """Non-normalized weights should be automatically normalized."""
        calc = ConfidenceCalculator(
            weights={
                "rule_type": 0.5,
                "similarity": 0.5,
                "uniqueness": 0.5,
                "historical": 0.5,
                "extraction": 0.5,
            }
        )

        weight_sum = sum(calc._weights.values())
        assert abs(weight_sum - 1.0) < 0.001


class TestConfidenceSignals:
    """Tests for confidence signal calculation."""

    def test_vendor_only_rule_type_score(self):
        """Vendor-only rules should have highest rule_type score."""
        calc = ConfidenceCalculator()

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_only",
                "similarity_score": 1.0,
            },
            is_new_vendor=False,
        )

        assert result.signals.rule_type_score == 1.0

    def test_vendor_item_rule_type_score(self):
        """Vendor+item rules should have medium rule_type score."""
        calc = ConfidenceCalculator()

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_item",
                "similarity_score": 0.9,
            },
            is_new_vendor=False,
        )

        assert result.signals.rule_type_score == 0.8

    def test_ambiguous_match_reduces_uniqueness(self):
        """Ambiguous matches should reduce uniqueness score."""
        calc = ConfidenceCalculator()

        result = calc.calculate(
            rule_match={
                "rule_type": "vendor_item",
                "similarity_score": 0.9,
                "is_ambiguous": True,
            },
            is_new_vendor=False,
        )

        assert result.signals.uniqueness_score == 0.5
