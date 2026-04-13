"""Tool to resolve the fiscal period for a given date."""

from __future__ import annotations

from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class PeriodResolveTool:
    """Find or create the fiscal period for a date."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_period_resolve"

    @property
    def description(self) -> str:
        return (
            "Find or automatically create the fiscal period (month) for a date. "
            "Returns the period ID, label, and open/closed status."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
            },
            "required": ["date"],
        }

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> str:
        return "low"

    @property
    def supports_parallelism(self) -> bool:
        return True

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        date = kwargs.get("date", "")
        if not date or len(date) < 10:
            return False, "date is required (YYYY-MM-DD)"
        try:
            int(date[:4])
            int(date[5:7])
        except (ValueError, IndexError):
            return False, f"Invalid date format: '{date}'. Expected YYYY-MM-DD"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()
        try:
            period = store.resolve_period(kwargs["date"])
            return {
                "success": True,
                "period": {
                    "id": period.id,
                    "year": period.year,
                    "month": period.month,
                    "label": period.label,
                    "start_date": period.start_date,
                    "end_date": period.end_date,
                    "is_closed": period.is_closed,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Period lookup for {kwargs.get('date', '?')}"
