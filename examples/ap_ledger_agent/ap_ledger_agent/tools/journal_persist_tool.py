"""Tool to persist a journal entry (Buchungssatz) to the database."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ap_ledger_agent.domain.models import JournalEntry, JournalLine, JournalStatus
from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class JournalPersistTool:
    """Create a journal entry with debit/credit lines.

    Validates that sum(debit) == sum(credit) before saving.
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_journal_persist"

    @property
    def description(self) -> str:
        return (
            "Create a journal entry (Buchungssatz) with debit/credit lines. "
            "Validates Soll=Haben before saving. Returns the journal_id. "
            "Use ap_journal_post to finalize the booking."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "integer", "description": "Related invoice ID"},
                "entry_date": {"type": "string", "description": "Booking date (YYYY-MM-DD)"},
                "description": {"type": "string", "description": "Booking description"},
                "fiscal_period_id": {"type": "integer", "description": "Fiscal period ID"},
                "lines": {
                    "type": "array",
                    "description": "Journal lines (Soll/Haben). Each line has either debit_amount OR credit_amount.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "line_number": {"type": "integer"},
                            "account_code": {"type": "string", "description": "Account number (e.g. 5100, 2500)"},
                            "account_name": {"type": "string", "description": "Account name"},
                            "debit_amount": {"type": "number", "description": "Soll-Betrag (0 if credit line)"},
                            "credit_amount": {"type": "number", "description": "Haben-Betrag (0 if debit line)"},
                            "tax_code": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["account_code", "account_name"],
                    },
                },
            },
            "required": ["entry_date", "description", "lines"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> str:
        return "medium"

    @property
    def supports_parallelism(self) -> bool:
        return False

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if not kwargs.get("entry_date"):
            return False, "entry_date is required"
        if not kwargs.get("description"):
            return False, "description is required"
        if not kwargs.get("lines"):
            return False, "lines are required (at least one debit and one credit)"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()

        try:
            lines = []
            for i, line_data in enumerate(kwargs["lines"], start=1):
                lines.append(
                    JournalLine(
                        line_number=line_data.get("line_number", i),
                        account_code=line_data["account_code"],
                        account_name=line_data["account_name"],
                        debit_amount=Decimal(str(line_data.get("debit_amount", 0))),
                        credit_amount=Decimal(str(line_data.get("credit_amount", 0))),
                        tax_code=line_data.get("tax_code"),
                        description=line_data.get("description"),
                    )
                )

            entry = JournalEntry(
                invoice_id=kwargs.get("invoice_id"),
                entry_date=kwargs["entry_date"],
                description=kwargs["description"],
                status=JournalStatus.DRAFT,
                fiscal_period_id=kwargs.get("fiscal_period_id"),
                lines=lines,
            )

            # Balance check
            if not entry.is_balanced():
                total_debit = sum(l.debit_amount for l in lines)
                total_credit = sum(l.credit_amount for l in lines)
                return {
                    "success": False,
                    "error": "journal_not_balanced",
                    "message": f"Soll ({total_debit}) != Haben ({total_credit}). "
                    "Buchungssatz muss ausgeglichen sein.",
                    "total_debit": float(total_debit),
                    "total_credit": float(total_credit),
                }

            journal_id = store.persist_journal(entry)
            return {
                "success": True,
                "journal_id": journal_id,
                "status": "draft",
                "description": kwargs["description"],
                "line_count": len(lines),
                "message": "Journal-Eintrag erstellt. Verwende ap_journal_post zum Buchen.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Create journal entry: {kwargs.get('description', '?')}"
