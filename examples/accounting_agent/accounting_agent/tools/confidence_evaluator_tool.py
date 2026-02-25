"""
Confidence Evaluator Tool

Wraps the ConfidenceCalculator for tool-based access.
Evaluates booking proposals and determines whether auto-booking
is allowed or HITL review is required.
"""

from decimal import Decimal
from typing import Any, Optional

import structlog

from accounting_agent.domain.confidence import ConfidenceCalculator
from accounting_agent.domain.models import (
    ConfidenceRecommendation,
)
from accounting_agent.domain.invoice_utils import extract_supplier_name
from accounting_agent.tools.tool_base import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class ConfidenceEvaluatorTool:
    """
    Evaluate confidence for booking proposals.

    Uses weighted signals and hard gates to determine whether
    a booking can be auto-processed or requires HITL review.

    Signals evaluated:
    - Rule type (Vendor-Only > Vendor+Item > RAG)
    - Similarity score from matching
    - Match uniqueness (not ambiguous)
    - Historical hit rate
    - Extraction/OCR quality

    Hard Gates (always trigger HITL):
    - New vendor (first invoice)
    - High amount (> threshold)
    - Critical account
    """

    def __init__(
        self,
        auto_book_threshold: float = 0.95,
        high_amount_threshold: float = 5000.0,
        critical_accounts: Optional[list[str]] = None,
        booking_history: Optional[Any] = None,
    ):
        """
        Initialize confidence evaluator.

        Args:
            auto_book_threshold: Threshold for auto-booking (default 0.95)
            high_amount_threshold: Amount threshold for HITL (default 5000 EUR)
            critical_accounts: List of accounts that always require HITL
            booking_history: BookingHistoryProtocol for vendor lookup
        """
        hard_gate_config = {
            "no_rule_match": True,
            "new_vendor": True,
            "high_amount_threshold": Decimal(str(high_amount_threshold)),
            "critical_accounts": critical_accounts or ["1800", "2100"],
        }

        self._calculator = ConfidenceCalculator(
            auto_book_threshold=auto_book_threshold,
            hard_gate_config=hard_gate_config,
        )
        self._booking_history = booking_history

    @property
    def name(self) -> str:
        """Return tool name."""
        return "confidence_evaluator"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Evaluate confidence for a booking proposal. "
            "Returns confidence score, recommendation (auto_book or hitl_review), "
            "and any triggered hard gates. Use after semantic_rule_engine or rag_fallback "
            "to determine if the booking can be auto-processed."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "rule_match": {
                    "type": "object",
                    "description": (
                        "Rule match result from semantic_rule_engine. "
                        "Contains: rule_id, rule_type, match_type, similarity_score"
                    ),
                },
                "booking_proposal": {
                    "type": "object",
                    "description": (
                        "Booking proposal to evaluate (OPTIONAL). "
                        "If missing or empty, no_rule_match hard gate triggers HITL. "
                        "Should include: debit_account, amount"
                    ),
                },
                "invoice_data": {
                    "type": "object",
                    "description": (
                        "Invoice data for context. "
                        "Should include: supplier_name, total_gross"
                    ),
                },
                "extraction_score": {
                    "type": "number",
                    "description": "OCR/extraction quality score (0.0-1.0, default 1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "is_new_vendor": {
                    "type": "boolean",
                    "description": "True if this is the first invoice from this vendor",
                },
                "is_rag_suggestion": {
                    "type": "boolean",
                    "description": "True if this is a RAG fallback suggestion (not rule-based)",
                },
                "rag_confidence": {
                    "type": "number",
                    "description": "RAG suggestion confidence (0.0-1.0, if is_rag_suggestion)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "memory_confirmed": {
                    "type": "boolean",
                    "description": (
                        "True if a user-defined memory rule confirms this booking "
                        "(e.g. 'Getränke immer auf 4900'). Forces auto-book when set."
                    ),
                },
            },
            "required": ["invoice_data"],
        }

    @property
    def requires_approval(self) -> bool:
        """Read-only evaluation."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - only evaluates, doesn't book."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        invoice_data = kwargs.get("invoice_data", {})
        supplier = invoice_data.get("supplier_name", "Unknown")
        amount = invoice_data.get("total_gross", 0)
        return (
            f"Tool: {self.name}\n"
            f"Operation: Evaluate booking confidence\n"
            f"Supplier: {supplier}\n"
            f"Amount: {amount} EUR"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        # Note: booking_proposal is now OPTIONAL - when missing/empty, the
        # no_rule_match hard gate will trigger HITL automatically
        if "invoice_data" not in kwargs:
            return False, "Missing required parameter: invoice_data"
        return True, None

    async def execute(
        self,
        invoice_data: dict[str, Any],
        booking_proposal: Optional[dict[str, Any]] = None,
        rule_match: Optional[dict[str, Any]] = None,
        extraction_score: float = 1.0,
        is_new_vendor: Optional[bool] = None,
        is_rag_suggestion: bool = False,
        rag_confidence: float = 0.0,
        memory_confirmed: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Evaluate confidence for a booking proposal.

        Args:
            invoice_data: Invoice context with supplier_name, total_gross
            booking_proposal: Proposed booking with debit_account, amount (optional - if missing, no_rule_match gate triggers)
            rule_match: Rule match result (if rule-based)
            extraction_score: OCR quality score
            is_new_vendor: True for first-time vendors (auto-detected if None)
            is_rag_suggestion: True for RAG fallback suggestions
            rag_confidence: RAG confidence score
            memory_confirmed: True if a user-defined memory rule confirms this booking

        Returns:
            Dictionary with:
            - success: bool
            - overall_confidence: float (0.0-1.0)
            - recommendation: "auto_book" or "hitl_review"
            - signals: Individual signal scores
            - hard_gates: List of hard gate results
            - explanation: Human-readable explanation
        """
        try:
            # Log input parameters
            logger.debug(
                "confidence_evaluator.execute_start",
                has_rule_match=rule_match is not None,
                rule_id=rule_match.get("rule_id") if rule_match else None,
                has_booking_proposal=booking_proposal is not None,
            )
            # Extract relevant values
            invoice_amount = invoice_data.get("total_gross")
            if invoice_amount is not None:
                invoice_amount = Decimal(str(invoice_amount))

            # Handle missing booking_proposal (no rule match case)
            target_account = None
            if booking_proposal:
                target_account = booking_proposal.get("debit_account")

            # Auto-detect new vendor if not provided
            vendor_is_new = is_new_vendor
            if vendor_is_new is None and self._booking_history:
                supplier_name = invoice_data.get("supplier_name", "")
                if supplier_name:
                    vendor_is_new = await self._booking_history.is_new_vendor(supplier_name)
                else:
                    vendor_is_new = False
            elif vendor_is_new is None:
                vendor_is_new = False

            # Get historical hit rate based on rule source
            # Confirmed learned rules (from HITL or high-confidence auto) have higher hit rate
            force_auto_book = False
            if rule_match:
                rule_source = rule_match.get("rule_source", "")
                match_type = rule_match.get("match_type", "")
                similarity = rule_match.get("similarity_score", 0.0)
                rule_id = rule_match.get("rule_id", "")

                is_confirmed_rule = rule_source in ("auto_high_confidence", "hitl_correction")
                is_exact_match = match_type == "exact" and similarity >= 0.95

                logger.info(
                    "confidence_evaluator.rule_analysis",
                    rule_id=rule_id,
                    rule_source=rule_source,
                    match_type=match_type,
                    similarity=similarity,
                    is_confirmed=is_confirmed_rule,
                    is_exact=is_exact_match,
                )

                if match_type == "vendor_generalized":
                    # Vendor generalization: reasonable confidence, but not auto-book
                    historical_hit_rate = 0.85
                    # Do NOT force_auto_book - this is an inference, needs HITL review
                    logger.debug(
                        "confidence_evaluator.vendor_generalized",
                        rule_id=rule_id,
                        similarity=similarity,
                    )
                elif is_confirmed_rule and is_exact_match:
                    # Confirmed rules with exact match - TRUST THEM!
                    # These were previously approved by the user
                    historical_hit_rate = 0.99
                    force_auto_book = True  # Skip other confidence checks
                    logger.debug(
                        "confidence_evaluator.force_auto_book",
                        rule_id=rule_id,
                        reason="confirmed_exact_match",
                    )
                elif is_confirmed_rule and similarity >= 0.8:
                    # Confirmed rules with good semantic match
                    historical_hit_rate = 0.95
                    # Also force auto-book for confirmed rules with good semantic match
                    force_auto_book = True
                    logger.debug(
                        "confidence_evaluator.force_auto_book",
                        rule_id=rule_id,
                        reason="confirmed_semantic_match",
                        similarity=similarity,
                    )
                elif is_confirmed_rule:
                    # Confirmed rules with lower match
                    historical_hit_rate = 0.90
                else:
                    historical_hit_rate = 0.8  # Default for manual rules
            else:
                historical_hit_rate = 0.8  # Default assumption
                logger.debug("confidence_evaluator.no_rule_match_provided")

            # Memory-confirmed bookings: user explicitly stored this rule
            if memory_confirmed and not force_auto_book:
                force_auto_book = True
                historical_hit_rate = 1.0
                logger.info(
                    "confidence_evaluator.memory_confirmed_auto_book",
                    reason="user_memory_rule_matches_booking",
                )

            # Calculate confidence
            result = self._calculator.calculate(
                rule_match=rule_match,
                extraction_score=extraction_score,
                historical_hit_rate=historical_hit_rate,
                is_new_vendor=vendor_is_new,
                invoice_amount=invoice_amount,
                target_account=target_account,
                is_rag_suggestion=is_rag_suggestion,
                rag_confidence=rag_confidence,
            )

            # Format hard gates for output
            hard_gates_output = []
            for gate in result.hard_gates_triggered:
                hard_gates_output.append({
                    "gate_type": gate.gate_type,
                    "triggered": gate.triggered,
                    "reason": gate.reason,
                    "threshold": gate.threshold_value,
                    "actual": gate.actual_value,
                })

            # Format signals for output
            signals_output = {
                "rule_type": result.signals.rule_type_score,
                "similarity": result.signals.similarity_score,
                "uniqueness": result.signals.uniqueness_score,
                "historical": result.signals.historical_score,
                "extraction": result.signals.extraction_score,
            }

            # Check if no_rule_match hard gate was triggered
            no_rule_match_triggered = any(
                g.gate_type == "no_rule_match" and g.triggered
                for g in result.hard_gates_triggered
            )

            # Override recommendation for confirmed learned rules
            # But still respect critical hard gates (high_amount, critical_account)
            final_recommendation = result.recommendation
            critical_gates_triggered = any(
                g.gate_type in ("high_amount", "critical_account") and g.triggered
                for g in result.hard_gates_triggered
            )

            if force_auto_book and not critical_gates_triggered and not no_rule_match_triggered:
                # Confirmed rule with exact match - auto book!
                final_recommendation = ConfidenceRecommendation.AUTO_BOOK
                logger.info(
                    "confidence_evaluator.override_to_auto_book",
                    reason="confirmed_learned_rule",
                    original_recommendation=result.recommendation.value,
                )

            logger.debug(
                "confidence_evaluator.recommendation_logic",
                force_auto_book=force_auto_book,
                critical_gates_triggered=critical_gates_triggered,
                no_rule_match_triggered=no_rule_match_triggered,
                final_recommendation=final_recommendation.value,
            )

            logger.info(
                "confidence_evaluator.evaluated",
                confidence=result.overall_confidence,
                recommendation=final_recommendation.value,
                force_auto_book=force_auto_book,
                hard_gates_triggered=len([g for g in result.hard_gates_triggered if g.triggered]),
                no_rule_match=no_rule_match_triggered,
                has_booking_proposal=booking_proposal is not None and bool(booking_proposal),
            )

            if no_rule_match_triggered:
                supplier_name = extract_supplier_name(invoice_data)
                logger.warning(
                    "confidence_evaluator.no_rule_match_hitl_required",
                    supplier=supplier_name or "unknown",
                    message="Keine passende Buchungsregel gefunden - HITL erforderlich",
                )

            return {
                "success": True,
                "overall_confidence": result.overall_confidence,
                "recommendation": final_recommendation.value,
                "requires_hitl": final_recommendation == ConfidenceRecommendation.HITL_REVIEW,
                "signals": signals_output,
                "hard_gates": hard_gates_output,
                "auto_book_threshold": result.auto_book_threshold,
                "explanation": result.explanation,
                "force_auto_book": force_auto_book,
            }

        except Exception as e:
            logger.error(
                "confidence_evaluator.error",
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def update_config(
        self,
        auto_book_threshold: Optional[float] = None,
        high_amount_threshold: Optional[float] = None,
        critical_accounts: Optional[list[str]] = None,
    ) -> None:
        """
        Update evaluator configuration.

        Args:
            auto_book_threshold: New auto-booking threshold
            high_amount_threshold: New high amount threshold
            critical_accounts: New list of critical accounts
        """
        if auto_book_threshold is not None:
            self._calculator.set_auto_book_threshold(auto_book_threshold)

        if high_amount_threshold is not None or critical_accounts is not None:
            current_config = {
                "no_rule_match": True,
                "new_vendor": True,
                "high_amount_threshold": Decimal(str(high_amount_threshold or 5000.0)),
                "critical_accounts": critical_accounts or ["1800", "2100"],
            }
            self._calculator.set_hard_gate_config(current_config)

    def set_booking_history(self, booking_history: Any) -> None:
        """Set or update the booking history for vendor lookups."""
        self._booking_history = booking_history
