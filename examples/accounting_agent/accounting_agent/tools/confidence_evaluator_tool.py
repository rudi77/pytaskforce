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
                        "Booking proposal to evaluate. "
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
            },
            "required": ["booking_proposal", "invoice_data"],
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
        if "booking_proposal" not in kwargs:
            return False, "Missing required parameter: booking_proposal"
        if "invoice_data" not in kwargs:
            return False, "Missing required parameter: invoice_data"
        return True, None

    async def execute(
        self,
        booking_proposal: dict[str, Any],
        invoice_data: dict[str, Any],
        rule_match: Optional[dict[str, Any]] = None,
        extraction_score: float = 1.0,
        is_new_vendor: Optional[bool] = None,
        is_rag_suggestion: bool = False,
        rag_confidence: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Evaluate confidence for a booking proposal.

        Args:
            booking_proposal: Proposed booking with debit_account, amount
            invoice_data: Invoice context with supplier_name, total_gross
            rule_match: Rule match result (if rule-based)
            extraction_score: OCR quality score
            is_new_vendor: True for first-time vendors (auto-detected if None)
            is_rag_suggestion: True for RAG fallback suggestions
            rag_confidence: RAG confidence score

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
            # Extract relevant values
            invoice_amount = invoice_data.get("total_gross")
            if invoice_amount is not None:
                invoice_amount = Decimal(str(invoice_amount))

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

            # Get historical hit rate (placeholder - could be from repository)
            historical_hit_rate = 0.8  # Default assumption

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

            logger.info(
                "confidence_evaluator.evaluated",
                confidence=result.overall_confidence,
                recommendation=result.recommendation.value,
                hard_gates_triggered=len([g for g in result.hard_gates_triggered if g.triggered]),
            )

            return {
                "success": True,
                "overall_confidence": result.overall_confidence,
                "recommendation": result.recommendation.value,
                "requires_hitl": result.recommendation == ConfidenceRecommendation.HITL_REVIEW,
                "signals": signals_output,
                "hard_gates": hard_gates_output,
                "auto_book_threshold": result.auto_book_threshold,
                "explanation": result.explanation,
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
                "new_vendor": True,
                "high_amount_threshold": Decimal(str(high_amount_threshold or 5000.0)),
                "critical_accounts": critical_accounts or ["1800", "2100"],
            }
            self._calculator.set_hard_gate_config(current_config)

    def set_booking_history(self, booking_history: Any) -> None:
        """Set or update the booking history for vendor lookups."""
        self._booking_history = booking_history
