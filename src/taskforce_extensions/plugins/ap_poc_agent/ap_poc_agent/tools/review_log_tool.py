"""Review log tool for human approval mock."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class ReviewLogTool:
    """Generate a review log table for manual approval."""

    @property
    def name(self) -> str:
        """Return tool name."""
        return "review_log_generate"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Generates a human review table for booking proposals including "
            "suggested payment date and approval question."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "booking_proposal": {
                    "type": "object",
                    "description": "Booking proposal from Tax Wizard",
                },
                "payment_terms_days": {
                    "type": "integer",
                    "description": "Payment terms in days",
                    "default": 30,
                },
            },
            "required": ["booking_proposal"],
        }

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "booking_proposal" not in kwargs:
            return False, "booking_proposal is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Generate review log entry."""
        try:
            proposal = _ensure_dict(kwargs.get("booking_proposal"))
            terms = int(kwargs.get("payment_terms_days", 30))
        except (TypeError, ValueError) as error:
            return _error_result(error)

        payment_date = _calculate_payment_date(terms)
        entry = _build_entry(proposal, payment_date)

        return {
            "success": True,
            "review_entry": entry,
            "approval_prompt": (
                "Ich würde Rechnung {invoice_id} auf Konto {account} buchen und "
                "am {payment_date} zur Zahlung anweisen. Bestätigen?"
            ).format(
                invoice_id=proposal.get("invoice_id"),
                account=proposal.get("debit_account"),
                payment_date=payment_date,
            ),
        }


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Ensure a value is a dictionary."""
    if not isinstance(value, dict):
        raise ValueError("booking_proposal must be an object")
    return value


def _calculate_payment_date(terms: int) -> str:
    """Calculate payment date from today and terms."""
    target_date = date.today() + timedelta(days=terms)
    return target_date.isoformat()


def _build_entry(proposal: dict[str, Any], payment_date: str) -> dict[str, Any]:
    """Build review entry for manual approval."""
    return {
        "invoice_id": proposal.get("invoice_id"),
        "vendor": proposal.get("vendor"),
        "debit_account": proposal.get("debit_account"),
        "credit_account": proposal.get("credit_account"),
        "total_amount": proposal.get("total_amount"),
        "currency": proposal.get("currency"),
        "payment_date": payment_date,
    }


def _error_result(error: Exception) -> dict[str, Any]:
    """Format an error result."""
    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
    }
