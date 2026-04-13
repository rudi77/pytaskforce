"""Tool to resolve or create a vendor in the AP Ledger database."""

from __future__ import annotations

from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class VendorResolveTool:
    """Resolve a vendor by name or create a new one."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    # -- ToolProtocol properties ------------------------------------------

    @property
    def name(self) -> str:
        return "ap_vendor_resolve"

    @property
    def description(self) -> str:
        return (
            "Search for a vendor/supplier in the AP Ledger database by name. "
            "Returns matching vendors with their default category and tax code. "
            "Can also create a new vendor if action='create'."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "vendor_name": {
                    "type": "string",
                    "description": "Name of the vendor to search for",
                },
                "action": {
                    "type": "string",
                    "enum": ["search", "create"],
                    "description": "search = find existing, create = add new vendor",
                    "default": "search",
                },
                "category_code": {
                    "type": "string",
                    "description": "Default expense category code (for create)",
                },
                "tax_code": {
                    "type": "string",
                    "description": "Default tax code (for create, default: AT_20)",
                },
                "keywords": {
                    "type": "string",
                    "description": "Comma-separated search keywords (for create)",
                },
            },
            "required": ["vendor_name"],
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

    # -- ToolProtocol methods ---------------------------------------------

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        if not kwargs.get("vendor_name"):
            return False, "vendor_name is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()
        action = kwargs.get("action", "search")
        vendor_name = kwargs["vendor_name"]

        try:
            if action == "create":
                vendor = store.create_vendor(
                    name=vendor_name,
                    category_code=kwargs.get("category_code"),
                    tax_code=kwargs.get("tax_code", "AT_20"),
                    keywords=kwargs.get("keywords"),
                )
                return {
                    "success": True,
                    "action": "created",
                    "vendor": {
                        "id": vendor.id,
                        "name": vendor.name,
                        "default_category_code": vendor.default_category_code,
                        "default_tax_code": vendor.default_tax_code,
                    },
                }

            vendors = store.resolve_vendor(vendor_name)
            if not vendors:
                return {
                    "success": True,
                    "found": False,
                    "vendors": [],
                    "message": f"Kein Vendor gefunden für '{vendor_name}'. "
                    "Verwende action='create' um einen neuen anzulegen.",
                }

            return {
                "success": True,
                "found": True,
                "vendors": [
                    {
                        "id": v.id,
                        "name": v.name,
                        "default_category_code": v.default_category_code,
                        "default_tax_code": v.default_tax_code,
                        "match_keywords": v.match_keywords,
                    }
                    for v in vendors
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Vendor lookup: {kwargs.get('vendor_name', '?')}"
