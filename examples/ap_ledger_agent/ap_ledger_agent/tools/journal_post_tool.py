"""Tool to finalize (post) a journal entry."""

from __future__ import annotations

from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class JournalPostTool:
    """Post a journal entry: transition draft -> posted."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_journal_post"

    @property
    def description(self) -> str:
        return (
            "Finalize a journal entry by changing its status from 'draft' to 'posted'. "
            "Also updates the associated invoice status. "
            "Validates Soll=Haben before posting."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "journal_id": {
                    "type": "integer",
                    "description": "ID of the journal entry to post",
                },
            },
            "required": ["journal_id"],
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
        if not kwargs.get("journal_id"):
            return False, "journal_id is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()
        try:
            result = store.post_journal(kwargs["journal_id"])
            return {
                "success": True,
                "journal_id": kwargs["journal_id"],
                "status": "posted",
                "posted_at": result.get("posted_at"),
                "vendor": result.get("vendor_name_raw"),
                "total_gross": result.get("total_gross"),
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Post journal entry #{kwargs.get('journal_id', '?')}"
