"""Tool to generate EÜR reports, monthly summaries, and CSV exports."""

from __future__ import annotations

from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class EuerReportTool:
    """Generate EÜR reports, monthly summaries, and CSV exports for the Steuerberater."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_euer_report"

    @property
    def description(self) -> str:
        return (
            "Generate financial reports from the AP Ledger. "
            "Actions: 'monthly' for monthly totals (revenue, expenses, profit, tax), "
            "'euer' for full EÜR category breakdown, "
            "'csv' for CSV export (for the Steuerberater), "
            "'open' for open/draft invoices, "
            "'categories' for available expense/revenue categories."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["monthly", "euer", "csv", "open", "categories"],
                    "description": "Type of report to generate",
                },
                "year": {
                    "type": "integer",
                    "description": "Year to report on (for monthly, euer, csv)",
                },
            },
            "required": ["action"],
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
        action = kwargs.get("action")
        if not action:
            return False, "action is required"
        if action in ("euer", "csv") and not kwargs.get("year"):
            return False, f"year is required for action '{action}'"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()
        action = kwargs["action"]

        try:
            if action == "monthly":
                totals = store.monthly_totals(kwargs.get("year"))
                return {"success": True, "monthly_totals": totals}

            if action == "euer":
                summary = store.euer_summary(kwargs["year"])
                return {"success": True, "year": kwargs["year"], "euer_summary": summary}

            if action == "csv":
                csv_content = store.export_csv(kwargs["year"])
                if not csv_content:
                    return {
                        "success": True,
                        "csv": "",
                        "message": f"Keine gebuchten Belege für {kwargs['year']}.",
                    }
                return {
                    "success": True,
                    "csv": csv_content,
                    "message": f"CSV-Export für {kwargs['year']} erstellt.",
                }

            if action == "open":
                invoices = store.open_invoices()
                return {"success": True, "open_invoices": invoices}

            if action == "categories":
                categories = store.list_categories()
                return {
                    "success": True,
                    "categories": [
                        {
                            "code": c.code,
                            "name": c.name,
                            "type": c.type.value,
                            "default_tax_code": c.default_tax_code,
                        }
                        for c in categories
                    ],
                }

            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"EÜR report: {kwargs.get('action', '?')}"
