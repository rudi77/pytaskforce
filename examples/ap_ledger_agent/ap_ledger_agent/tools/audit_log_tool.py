"""Tool to write immutable audit log entries."""

from __future__ import annotations

import json
from typing import Any

from ap_ledger_agent.infrastructure.sqlite_store import SQLiteStore


class AuditLogTool:
    """Write an immutable entry to the audit log."""

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "ap_audit_log"

    @property
    def description(self) -> str:
        return (
            "Write an immutable audit log entry for compliance. "
            "Event types: invoice_created, invoice_validated, invoice_posted, "
            "invoice_rejected, journal_created, journal_posted, journal_reversed, "
            "vendor_created, user_confirmed, user_corrected, error_occurred."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "Type of audit event",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Entity type (invoice, journal_entry, vendor)",
                },
                "entity_id": {
                    "type": "integer",
                    "description": "ID of the related entity",
                },
                "actor": {
                    "type": "string",
                    "description": "Who performed the action (agent, user, system)",
                    "default": "agent",
                },
                "details": {
                    "type": "object",
                    "description": "Additional details as JSON object",
                },
            },
            "required": ["event_type", "entity_type", "entity_id"],
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
        if not kwargs.get("event_type"):
            return False, "event_type is required"
        if not kwargs.get("entity_type"):
            return False, "entity_type is required"
        if kwargs.get("entity_id") is None:
            return False, "entity_id is required"
        return True, None

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        store = SQLiteStore(self._db_path)
        store.ensure_initialized()
        try:
            details = kwargs.get("details", {})
            if isinstance(details, dict):
                details = json.dumps(details, ensure_ascii=False)

            audit_id = store.write_audit(
                event_type=kwargs["event_type"],
                entity_type=kwargs["entity_type"],
                entity_id=kwargs["entity_id"],
                actor=kwargs.get("actor", "agent"),
                details=details,
            )
            return {
                "success": True,
                "audit_id": audit_id,
                "event_type": kwargs["event_type"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_approval_preview(self, **kwargs: Any) -> str:
        return f"Audit log: {kwargs.get('event_type', '?')} on {kwargs.get('entity_type', '?')}#{kwargs.get('entity_id', '?')}"
