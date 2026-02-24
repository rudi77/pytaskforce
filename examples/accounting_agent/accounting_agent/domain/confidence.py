"""
Confidence Calculator for Booking Proposals

Implements deterministic confidence evaluation based on weighted signals
and hard gates. Used to decide between auto-booking and HITL review.

PRD Reference:
- > 95%: Automatic booking + rule learning
- <= 95%: HITL review required
- Hard gates: Always trigger HITL regardless of confidence
"""

from decimal import Decimal
from typing import Any, Optional

import structlog

from accounting_agent.domain.models import (
    ConfidenceResult,
    ConfidenceSignals,
    ConfidenceRecommendation,
    HardGate,
)

logger = structlog.get_logger(__name__)


class ConfidenceCalculator:
    """
    Calculate booking confidence from weighted signals and hard gates.

    Signal Weights (PRD):
    - rule_type: 0.25 (Vendor-Only > Vendor+Item > RAG)
    - similarity: 0.25 (Embedding similarity score)
    - uniqueness: 0.20 (Unambiguous match = higher)
    - historical: 0.15 (Historical hit rate for this rule)
    - extraction: 0.15 (OCR/extraction quality)

    Hard Gates (always trigger HITL):
    - no_rule_match: No matching rule found (ALWAYS triggers HITL)
    - new_vendor: First invoice from this vendor
    - high_amount: Amount > threshold (default 5000 EUR)
    - critical_account: Account in critical list
    """

    # Signal weights from PRD
    DEFAULT_WEIGHTS = {
        "rule_type": 0.25,
        "similarity": 0.25,
        "uniqueness": 0.20,
        "historical": 0.15,
        "extraction": 0.15,
    }

    # Threshold for automatic booking
    DEFAULT_AUTO_BOOK_THRESHOLD = 0.95

    # Default hard gate configuration
    DEFAULT_HARD_GATES = {
        "no_rule_match": True,  # CRITICAL: Always require HITL when no rule found
        "new_vendor": True,
        "high_amount_threshold": Decimal("5000.00"),
        "critical_accounts": ["1800", "2100"],  # Example critical accounts
    }

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        auto_book_threshold: float = DEFAULT_AUTO_BOOK_THRESHOLD,
        hard_gate_config: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize confidence calculator.

        Args:
            weights: Custom signal weights (must sum to 1.0)
            auto_book_threshold: Threshold for auto-booking (default 0.95)
            hard_gate_config: Configuration for hard gates
        """
        self._weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._auto_book_threshold = auto_book_threshold
        self._hard_gate_config = hard_gate_config or self.DEFAULT_HARD_GATES.copy()

        # Validate weights sum to 1.0
        weight_sum = sum(self._weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            logger.warning(
                "confidence.weights_not_normalized",
                sum=weight_sum,
            )
            # Normalize
            for key in self._weights:
                self._weights[key] /= weight_sum

    def calculate(
        self,
        rule_match: Optional[dict[str, Any]] = None,
        extraction_score: float = 1.0,
        historical_hit_rate: float = 0.8,
        is_new_vendor: bool = False,
        invoice_amount: Optional[Decimal] = None,
        target_account: Optional[str] = None,
        is_rag_suggestion: bool = False,
        rag_confidence: float = 0.0,
    ) -> ConfidenceResult:
        """
        Calculate overall confidence for a booking proposal.

        Args:
            rule_match: Rule match data from SemanticRuleEngineTool
            extraction_score: OCR/extraction quality score (0.0-1.0)
            historical_hit_rate: Historical hit rate for matched rule (0.0-1.0)
            is_new_vendor: True if this is first invoice from vendor
            invoice_amount: Invoice gross amount for high_amount gate
            target_account: Target account for critical_account gate
            is_rag_suggestion: True if this is a RAG fallback suggestion
            rag_confidence: RAG suggestion confidence (if applicable)

        Returns:
            ConfidenceResult with overall score and recommendation
        """
        # Calculate individual signal scores
        signals = self._calculate_signals(
            rule_match=rule_match,
            extraction_score=extraction_score,
            historical_hit_rate=historical_hit_rate,
            is_rag_suggestion=is_rag_suggestion,
            rag_confidence=rag_confidence,
        )

        # Calculate weighted overall confidence
        overall_confidence = (
            self._weights["rule_type"] * signals.rule_type_score
            + self._weights["similarity"] * signals.similarity_score
            + self._weights["uniqueness"] * signals.uniqueness_score
            + self._weights["historical"] * signals.historical_score
            + self._weights["extraction"] * signals.extraction_score
        )

        # Determine if we have a valid rule match
        has_rule_match = rule_match is not None and bool(rule_match)

        # Check hard gates
        hard_gates = self._check_hard_gates(
            has_rule_match=has_rule_match,
            is_new_vendor=is_new_vendor,
            invoice_amount=invoice_amount,
            target_account=target_account,
        )

        # Determine recommendation
        triggered_gates = [g for g in hard_gates if g.triggered]
        if triggered_gates:
            recommendation = ConfidenceRecommendation.HITL_REVIEW
            explanation = self._format_hard_gate_explanation(triggered_gates)
        elif overall_confidence >= self._auto_book_threshold:
            recommendation = ConfidenceRecommendation.AUTO_BOOK
            explanation = f"Confidence {overall_confidence:.1%} >= threshold {self._auto_book_threshold:.1%}"
        else:
            recommendation = ConfidenceRecommendation.HITL_REVIEW
            explanation = f"Confidence {overall_confidence:.1%} < threshold {self._auto_book_threshold:.1%}"

        logger.info(
            "confidence.calculated",
            overall=overall_confidence,
            recommendation=recommendation.value,
            hard_gates_triggered=len(triggered_gates),
        )

        return ConfidenceResult(
            overall_confidence=overall_confidence,
            signals=signals,
            recommendation=recommendation,
            hard_gates_triggered=hard_gates,
            explanation=explanation,
            auto_book_threshold=self._auto_book_threshold,
        )

    def _calculate_signals(
        self,
        rule_match: Optional[dict[str, Any]],
        extraction_score: float,
        historical_hit_rate: float,
        is_rag_suggestion: bool,
        rag_confidence: float,
    ) -> ConfidenceSignals:
        """Calculate individual confidence signals."""
        # Rule type score: Vendor-Only (1.0) > Vendor+Item (0.8) > RAG (0.5)
        # Boost for confirmed learned rules with exact match
        if is_rag_suggestion:
            rule_type_score = 0.5
        elif rule_match:
            rule_type = rule_match.get("rule_type", "")
            rule_source = rule_match.get("rule_source", "")
            match_type = rule_match.get("match_type", "")
            similarity = rule_match.get("similarity_score", 0.0)

            # Check if this is a confirmed learned rule with exact match
            # Use 0.95 threshold (consistent with confidence_evaluator_tool)
            is_confirmed_rule = rule_source in ("auto_high_confidence", "hitl_correction")
            is_exact_match = match_type == "exact" and similarity >= 0.95

            if rule_type == "vendor_only":
                rule_type_score = 1.0
            elif rule_type == "vendor_item":
                if match_type == "vendor_generalized":
                    # Vendor generalization: between vendor_item (0.8) and RAG (0.5)
                    rule_type_score = 0.70
                elif is_confirmed_rule and is_exact_match:
                    # Boost confirmed learned rules with exact match to near vendor_only level
                    rule_type_score = 0.98  # Almost as trusted as vendor_only
                else:
                    rule_type_score = 0.8
            else:
                rule_type_score = 0.6
        else:
            rule_type_score = 0.0

        # Similarity score: From rule match or RAG
        if is_rag_suggestion:
            similarity_score = rag_confidence
        elif rule_match:
            similarity_score = float(rule_match.get("similarity_score", 0.0))
        else:
            similarity_score = 0.0

        # Uniqueness score: Based on whether match is ambiguous
        if rule_match:
            # If match data includes is_ambiguous, use it
            is_ambiguous = rule_match.get("is_ambiguous", False)
            uniqueness_score = 0.5 if is_ambiguous else 1.0
        elif is_rag_suggestion:
            # RAG suggestions are inherently less unique
            uniqueness_score = 0.7
        else:
            uniqueness_score = 0.0

        # Historical score: Rule hit rate
        historical_score = historical_hit_rate

        # Extraction score: OCR quality
        extraction_score_final = extraction_score

        return ConfidenceSignals(
            rule_type_score=rule_type_score,
            similarity_score=similarity_score,
            uniqueness_score=uniqueness_score,
            historical_score=historical_score,
            extraction_score=extraction_score_final,
        )

    def _check_hard_gates(
        self,
        has_rule_match: bool,
        is_new_vendor: bool,
        invoice_amount: Optional[Decimal],
        target_account: Optional[str],
    ) -> list[HardGate]:
        """Check all hard gates and return results."""
        gates = []

        # No rule match gate (CRITICAL - always check first)
        if self._hard_gate_config.get("no_rule_match", True):
            no_match = not has_rule_match
            gates.append(
                HardGate(
                    gate_type="no_rule_match",
                    triggered=no_match,
                    reason="Keine passende Buchungsregel gefunden - User muss Konto angeben" if no_match else "",
                )
            )

        # New vendor gate
        if self._hard_gate_config.get("new_vendor", True):
            gates.append(
                HardGate(
                    gate_type="new_vendor",
                    triggered=is_new_vendor,
                    reason="Erster Beleg von diesem Lieferanten" if is_new_vendor else "",
                )
            )

        # High amount gate
        threshold = self._hard_gate_config.get(
            "high_amount_threshold", Decimal("5000.00")
        )
        if invoice_amount is not None:
            amount_decimal = (
                invoice_amount
                if isinstance(invoice_amount, Decimal)
                else Decimal(str(invoice_amount))
            )
            is_high = amount_decimal > threshold
            gates.append(
                HardGate(
                    gate_type="high_amount",
                    triggered=is_high,
                    reason=f"Betrag {amount_decimal} EUR > {threshold} EUR" if is_high else "",
                    threshold_value=str(threshold),
                    actual_value=str(amount_decimal),
                )
            )

        # Critical account gate
        critical_accounts = self._hard_gate_config.get("critical_accounts", [])
        if target_account and critical_accounts:
            is_critical = target_account in critical_accounts
            gates.append(
                HardGate(
                    gate_type="critical_account",
                    triggered=is_critical,
                    reason=f"Kritisches Konto: {target_account}" if is_critical else "",
                    actual_value=target_account,
                )
            )

        return gates

    def _format_hard_gate_explanation(self, triggered_gates: list[HardGate]) -> str:
        """Format explanation for triggered hard gates."""
        reasons = [g.reason for g in triggered_gates if g.reason]
        if not reasons:
            return "Hard gate triggered"
        return "HITL erforderlich: " + "; ".join(reasons)

    def set_weights(self, weights: dict[str, float]) -> None:
        """
        Update signal weights.

        Args:
            weights: New weights (will be normalized to sum to 1.0)
        """
        self._weights = weights.copy()
        weight_sum = sum(self._weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            for key in self._weights:
                self._weights[key] /= weight_sum

    def set_auto_book_threshold(self, threshold: float) -> None:
        """
        Update auto-booking threshold.

        Args:
            threshold: New threshold (0.0-1.0)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        self._auto_book_threshold = threshold

    def set_hard_gate_config(self, config: dict[str, Any]) -> None:
        """
        Update hard gate configuration.

        Args:
            config: New configuration dict
        """
        self._hard_gate_config = config.copy()
