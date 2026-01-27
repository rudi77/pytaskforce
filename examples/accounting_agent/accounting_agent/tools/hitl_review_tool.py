"""
HITL Review Tool

Handles Human-in-the-Loop review workflow for booking proposals
that don't meet confidence thresholds or trigger hard gates.

Triggers:
- Confidence <= 95%
- New vendor (Hard Gate)
- High amount > 5000 EUR (Hard Gate)
- Critical accounts (Hard Gate)

The tool creates structured review requests and processes corrections.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

import structlog

from accounting_agent.domain.models import (
    ConfidenceRecommendation,
)
from accounting_agent.tools.tool_base import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class HITLReviewTool:
    """
    Human-in-the-Loop review workflow handler.

    Creates review requests when automatic booking isn't possible
    and processes user corrections.

    Review Request Structure:
    - review_id: Unique identifier
    - invoice_data: Original invoice
    - booking_proposal: Proposed booking
    - confidence_result: Confidence evaluation
    - review_reason: Why HITL is needed
    - options: Suggested actions (confirm, correct, reject)
    """

    def __init__(self, rule_learning_tool: Optional[Any] = None):
        """
        Initialize HITL review tool.

        Args:
            rule_learning_tool: RuleLearningTool for creating rules from corrections
        """
        self._rule_learning_tool = rule_learning_tool
        self._pending_reviews: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        """Return tool name."""
        return "hitl_review"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Create or process a Human-in-the-Loop review request. "
            "Use when confidence_evaluator returns requires_hitl=true. "
            "Can create a review request (action='create') or process a response (action='process'). "
            "Optionally creates new rules from confirmed corrections."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": ["create", "process"],
                },
                "invoice_data": {
                    "type": "object",
                    "description": "Invoice data (for create action)",
                },
                "booking_proposal": {
                    "type": "object",
                    "description": "Proposed booking (for create action)",
                },
                "confidence_result": {
                    "type": "object",
                    "description": "Confidence evaluation result (for create action)",
                },
                "review_id": {
                    "type": "string",
                    "description": "Review ID (for process action)",
                },
                "user_decision": {
                    "type": "string",
                    "description": "User decision (for process action)",
                    "enum": ["confirm", "correct", "reject"],
                },
                "correction": {
                    "type": "object",
                    "description": "User correction data (if user_decision='correct')",
                },
                "create_rule": {
                    "type": "boolean",
                    "description": "Whether to create a rule from this decision",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        """This tool interacts with users."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Medium risk - creates review requests."""
        return ApprovalRiskLevel.MEDIUM

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        action = kwargs.get("action", "unknown")
        if action == "create":
            invoice_data = kwargs.get("invoice_data", {})
            supplier = invoice_data.get("supplier_name", "Unknown")
            return (
                f"Tool: {self.name}\n"
                f"Operation: Create HITL review request\n"
                f"Supplier: {supplier}"
            )
        else:
            review_id = kwargs.get("review_id", "unknown")
            decision = kwargs.get("user_decision", "unknown")
            return (
                f"Tool: {self.name}\n"
                f"Operation: Process HITL response\n"
                f"Review ID: {review_id}\n"
                f"Decision: {decision}"
            )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        action = kwargs.get("action")
        if action not in ["create", "process"]:
            return False, "action must be 'create' or 'process'"

        if action == "create":
            if "invoice_data" not in kwargs:
                return False, "Missing invoice_data for create action"
            if "booking_proposal" not in kwargs:
                return False, "Missing booking_proposal for create action"

        if action == "process":
            if "review_id" not in kwargs:
                return False, "Missing review_id for process action"
            if "user_decision" not in kwargs:
                return False, "Missing user_decision for process action"
            if kwargs["user_decision"] not in ["confirm", "correct", "reject"]:
                return False, "user_decision must be 'confirm', 'correct', or 'reject'"

        return True, None

    async def execute(
        self,
        action: str,
        invoice_data: Optional[dict[str, Any]] = None,
        booking_proposal: Optional[dict[str, Any]] = None,
        confidence_result: Optional[dict[str, Any]] = None,
        review_id: Optional[str] = None,
        user_decision: Optional[str] = None,
        correction: Optional[dict[str, Any]] = None,
        create_rule: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Create or process a HITL review.

        Args:
            action: 'create' or 'process'
            invoice_data: Invoice data (create)
            booking_proposal: Proposed booking (create)
            confidence_result: Confidence evaluation (create)
            review_id: Review ID (process)
            user_decision: User decision (process)
            correction: Correction data (process, if correcting)
            create_rule: Whether to create rule from decision

        Returns:
            Dictionary with review request or processing result
        """
        try:
            if action == "create":
                return await self._create_review(
                    invoice_data=invoice_data or {},
                    booking_proposal=booking_proposal or {},
                    confidence_result=confidence_result or {},
                )
            else:
                return await self._process_review(
                    review_id=review_id or "",
                    user_decision=user_decision or "",
                    correction=correction,
                    create_rule=create_rule,
                )

        except Exception as e:
            logger.error(
                "hitl_review.error",
                action=action,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def _create_review(
        self,
        invoice_data: dict[str, Any],
        booking_proposal: dict[str, Any],
        confidence_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new HITL review request."""
        review_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        # Determine review reason
        review_reasons = []
        if confidence_result.get("overall_confidence", 0) < confidence_result.get(
            "auto_book_threshold", 0.95
        ):
            conf = confidence_result.get("overall_confidence", 0)
            threshold = confidence_result.get("auto_book_threshold", 0.95)
            review_reasons.append(
                f"Konfidenz ({conf:.1%}) unter Schwellenwert ({threshold:.1%})"
            )

        for gate in confidence_result.get("hard_gates", []):
            if gate.get("triggered"):
                review_reasons.append(gate.get("reason", "Hard Gate ausgelöst"))

        # Build review request
        review_request = {
            "review_id": review_id,
            "timestamp": timestamp,
            "status": "pending",
            "invoice_data": invoice_data,
            "booking_proposal": booking_proposal,
            "confidence_result": confidence_result,
            "review_reasons": review_reasons,
        }

        # Store for later processing
        self._pending_reviews[review_id] = review_request

        # Format for user display
        supplier = invoice_data.get("supplier_name", "Unbekannt")
        amount = invoice_data.get("total_gross", 0)
        proposed_account = booking_proposal.get("debit_account", "?")
        proposed_name = booking_proposal.get("debit_account_name", "")
        confidence = confidence_result.get("overall_confidence", 0)

        user_prompt = f"""
## Buchungsvorschlag zur Prüfung

**Review-ID:** {review_id}

### Rechnungsdaten
- **Lieferant:** {supplier}
- **Bruttobetrag:** {amount} EUR
- **Positionen:** {len(invoice_data.get('line_items', []))}

### Vorgeschlagene Buchung
- **Konto:** {proposed_account} ({proposed_name})
- **Konfidenz:** {confidence:.1%}

### Prüfungsgrund
{chr(10).join('- ' + r for r in review_reasons)}

### Optionen
1. **Bestätigen** - Vorschlag übernehmen
2. **Korrigieren** - Anderes Konto angeben
3. **Ablehnen** - Buchung nicht durchführen

Bitte wählen Sie eine Option und geben Sie ggf. das korrekte Konto an.
"""

        logger.info(
            "hitl_review.created",
            review_id=review_id,
            supplier=supplier,
            confidence=confidence,
            reasons=len(review_reasons),
        )

        return {
            "success": True,
            "review_id": review_id,
            "status": "pending",
            "user_prompt": user_prompt,
            "review_reasons": review_reasons,
            "requires_user_input": True,
        }

    async def _process_review(
        self,
        review_id: str,
        user_decision: str,
        correction: Optional[dict[str, Any]],
        create_rule: bool,
    ) -> dict[str, Any]:
        """Process a HITL review response."""
        # Get pending review
        review = self._pending_reviews.get(review_id)
        if not review:
            return {
                "success": False,
                "error": f"Review {review_id} not found",
                "error_type": "ReviewNotFound",
            }

        timestamp = datetime.now(timezone.utc).isoformat()

        # Update review status
        review["status"] = "processed"
        review["processed_at"] = timestamp
        review["user_decision"] = user_decision
        review["correction"] = correction

        result = {
            "success": True,
            "review_id": review_id,
            "user_decision": user_decision,
            "processed_at": timestamp,
        }

        if user_decision == "confirm":
            # Use original proposal
            result["final_booking"] = review["booking_proposal"]
            result["is_hitl_correction"] = False

            logger.info(
                "hitl_review.confirmed",
                review_id=review_id,
            )

        elif user_decision == "correct":
            if not correction:
                return {
                    "success": False,
                    "error": "Correction data required for 'correct' decision",
                    "error_type": "MissingCorrection",
                }

            # Apply correction to booking
            final_booking = review["booking_proposal"].copy()
            final_booking.update(correction)
            result["final_booking"] = final_booking
            result["is_hitl_correction"] = True

            logger.info(
                "hitl_review.corrected",
                review_id=review_id,
                new_account=correction.get("debit_account"),
            )

            # Optionally create rule from correction
            if create_rule and self._rule_learning_tool:
                try:
                    rule_result = await self._rule_learning_tool.execute(
                        action="create_from_hitl",
                        invoice_data=review["invoice_data"],
                        correction=correction,
                    )
                    result["rule_created"] = rule_result.get("success", False)
                    result["rule_id"] = rule_result.get("rule_id")
                except Exception as e:
                    logger.warning(
                        "hitl_review.rule_creation_failed",
                        error=str(e),
                    )
                    result["rule_created"] = False

        elif user_decision == "reject":
            result["final_booking"] = None
            result["rejected"] = True

            logger.info(
                "hitl_review.rejected",
                review_id=review_id,
            )

        # Remove from pending
        del self._pending_reviews[review_id]

        return result

    def get_pending_reviews(self) -> list[dict[str, Any]]:
        """Get all pending reviews."""
        return list(self._pending_reviews.values())

    def get_review(self, review_id: str) -> Optional[dict[str, Any]]:
        """Get a specific review by ID."""
        return self._pending_reviews.get(review_id)

    def set_rule_learning_tool(self, rule_learning_tool: Any) -> None:
        """Set the rule learning tool for creating rules from corrections."""
        self._rule_learning_tool = rule_learning_tool
