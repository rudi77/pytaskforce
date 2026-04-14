"""Tool to correct an existing invoice in the AP Ledger database."""

from __future__ import annotations

from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class InvoiceCorrectTool:
    """Correct amounts or lines on an existing invoice.

    For non-posted invoices: updates directly.
    For posted invoices: reverses old journals and sets invoice back to
    'validated' so a new correct journal can be created.
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_invoice_correct"

    @property
    def description(self) -> str:
        return (
            "Correct an existing invoice's amounts or line items. "
            "Provide the invoice_id and the corrected values. "
            "For posted invoices, the old journals are reversed and the "
            "invoice is set back to 'validated' — you must then create a "
            "new journal (ap_journal_persist) and post it (ap_journal_post) "
            "with the corrected amounts. "
            "Use ap_euer_report with action='open_invoices' or action='monthly' "
            "to find the invoice_id."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "integer",
                    "description": "ID of the invoice to correct",
                },
                "total_gross": {
                    "type": "number",
                    "description": "Corrected total gross amount",
                },
                "total_net": {
                    "type": "number",
                    "description": "Corrected total net amount",
                },
                "total_tax": {
                    "type": "number",
                    "description": "Corrected total tax amount",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the correction",
                },
                "lines": {
                    "type": "array",
                    "description": "Corrected line items (replaces all existing lines)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "position": {"type": "integer"},
                            "description": {"type": "string"},
                            "quantity": {"type": "number", "default": 1},
                            "unit_price": {"type": "number"},
                            "net_amount": {"type": "number"},
                            "tax_code": {"type": "string"},
                            "tax_amount": {"type": "number"},
                            "gross_amount": {"type": "number"},
                            "category_code": {"type": "string"},
                        },
                        "required": ["description", "gross_amount"],
                    },
                },
            },
            "required": ["invoice_id"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> str:
        return "high"

    @property
    def supports_parallelism(self) -> bool:
        return False

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if not kwargs.get("invoice_id"):
            return False, "invoice_id is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()

        try:
            invoice_id = kwargs["invoice_id"]

            # Verify invoice exists
            invoice = store.get_invoice(invoice_id)
            if not invoice:
                return {
                    "success": False,
                    "error": f"Invoice {invoice_id} not found",
                }

            result = store.correct_invoice(
                invoice_id=invoice_id,
                total_gross=kwargs.get("total_gross"),
                total_net=kwargs.get("total_net"),
                total_tax=kwargs.get("total_tax"),
                lines=kwargs.get("lines"),
                reason=kwargs.get("reason", ""),
            )

            return {"success": True, **result}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return (
            f"Correct invoice #{kwargs.get('invoice_id', '?')}: "
            f"new gross={kwargs.get('total_gross', 'unchanged')}"
        )
