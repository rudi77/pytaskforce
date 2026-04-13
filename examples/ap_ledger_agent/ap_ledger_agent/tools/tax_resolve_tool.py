"""Tool to resolve an Austrian tax code."""

from __future__ import annotations

from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class TaxResolveTool:
    """Look up an Austrian tax code (USt-Satz)."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_tax_resolve"

    @property
    def description(self) -> str:
        return (
            "Resolve an Austrian tax code to its rate and description. "
            "Valid codes: AT_20 (20%), AT_10 (10%), AT_13 (13%), AT_0 (0%), EU_RC (Reverse Charge). "
            "Can also list all available tax codes with action='list'."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tax_code": {
                    "type": "string",
                    "description": "Tax code to resolve (e.g. AT_20)",
                },
                "action": {
                    "type": "string",
                    "enum": ["resolve", "list"],
                    "description": "resolve = look up one code, list = show all codes",
                    "default": "resolve",
                },
            },
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
        action = kwargs.get("action", "resolve")
        if action == "resolve" and not kwargs.get("tax_code"):
            return False, "tax_code is required for resolve action"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()
        action = kwargs.get("action", "resolve")

        try:
            if action == "list":
                tax_codes = store.list_tax_codes()
                return {
                    "success": True,
                    "tax_codes": tax_codes,
                }

            tc = store.resolve_tax(kwargs["tax_code"])
            if not tc:
                return {
                    "success": False,
                    "error": f"Steuercode '{kwargs['tax_code']}' nicht gefunden. "
                    "Gültige Codes: AT_20, AT_10, AT_13, AT_0, EU_RC",
                }
            return {
                "success": True,
                "tax_code": {
                    "code": tc.code,
                    "rate": float(tc.rate),
                    "label": tc.label,
                    "description": tc.description,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Tax code lookup: {kwargs.get('tax_code', 'list all')}"
