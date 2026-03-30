"""
GoBD-compliant audit logging tool for accounting operations.

Creates immutable, timestamped audit records to ensure compliance
with GoBD (Grundsaetze zur ordnungsgemaessen Fuehrung und Aufbewahrung
von Buechern, Aufzeichnungen und Unterlagen in elektronischer Form).

Adapted from examples/accounting_agent for use as a native BaseTool.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from taskforce.infrastructure.tools.base_tool import BaseTool

logger = structlog.get_logger(__name__)

_VALID_OPERATIONS = {
    "invoice_processed",
    "compliance_check",
    "booking_proposed",
    "manual_review",
    "document_extracted",
    "rule_applied",
    "tax_calculated",
    "user_decision",
}

_SENSITIVE_KEYS = {"password", "api_key", "secret", "token", "credential"}


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Sanitize details for logging, redacting sensitive fields."""
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_details(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_details(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class AccountingAuditTool(BaseTool):
    """GoBD-compliant audit logging for accounting operations.

    Creates immutable, timestamped audit records with unique ID,
    ISO 8601 timestamp, operation type, decision rationale,
    and SHA-256 integrity hash.
    """

    tool_name = "accounting_audit"
    tool_description = (
        "Create GoBD-compliant audit log entries for accounting operations. "
        "Records timestamps, operation details, decisions, and legal basis. "
        "Entries are immutable with SHA-256 integrity hashes."
    )
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": (
                    "Type of operation being logged. One of: "
                    "invoice_processed, compliance_check, booking_proposed, "
                    "manual_review, document_extracted, rule_applied, "
                    "tax_calculated, user_decision"
                ),
                "enum": sorted(_VALID_OPERATIONS),
            },
            "document_id": {
                "type": "string",
                "description": (
                    "Reference ID of the processed document " "(invoice number, file name)"
                ),
            },
            "details": {
                "type": "object",
                "description": "Operation-specific details (input data, results)",
            },
            "decision": {
                "type": "string",
                "description": "Decision or outcome of the operation",
            },
            "legal_basis": {
                "type": "string",
                "description": ("Legal reference for the decision (e.g. §14 UStG)"),
            },
        },
        "required": ["operation", "details"],
    }

    def __init__(self, audit_dir: str = ".taskforce_accounting/audit") -> None:
        """Initialize with audit directory path.

        Args:
            audit_dir: Directory for storing audit log files.
                Created lazily on first write.
        """
        self._audit_dir = Path(audit_dir)

    async def _execute(self, **kwargs: Any) -> dict[str, Any]:
        """Create an immutable audit log entry."""
        operation: str | None = kwargs.get("operation")
        details: dict[str, Any] | None = kwargs.get("details")
        if not operation:
            return {"success": False, "error": "Missing required parameter: operation"}
        if not details or not isinstance(details, dict):
            return {"success": False, "error": "Missing required parameter: details (must be a dict)"}
        document_id: str | None = kwargs.get("document_id")
        decision: str | None = kwargs.get("decision")
        legal_basis: str | None = kwargs.get("legal_basis")

        if operation not in _VALID_OPERATIONS:
            return {
                "success": False,
                "error": (
                    f"Invalid operation: {operation}. " f"Valid: {sorted(_VALID_OPERATIONS)}"
                ),
            }

        # Ensure audit directory exists (lazy creation)
        self._audit_dir.mkdir(parents=True, exist_ok=True)

        log_id = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()

        log_entry: dict[str, Any] = {
            "log_id": log_id,
            "timestamp": timestamp,
            "operation": operation,
            "document_id": document_id,
            "details": _sanitize_details(details),
            "decision": decision,
            "legal_basis": legal_basis,
            "metadata": {
                "version": "1.0",
                "gobd_compliant": True,
                "created_by": "taskforce_accounting",
            },
        }

        # SHA-256 integrity hash (computed before adding hash to entry)
        content_for_hash = json.dumps(log_entry, sort_keys=True, ensure_ascii=False)
        integrity_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
        log_entry["integrity_hash"] = integrity_hash

        # Write immutable log file
        date_prefix = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        log_file = self._audit_dir / f"{date_prefix}_{log_id[:8]}.json"

        log_file.write_text(
            json.dumps(log_entry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(
            "accounting.audit_log_created",
            log_id=log_id,
            operation=operation,
            document_id=document_id,
            log_file=str(log_file),
        )

        return {
            "success": True,
            "log_id": log_id,
            "timestamp": timestamp,
            "log_file": str(log_file),
            "integrity_hash": integrity_hash,
            "operation": operation,
            "message": f"Audit log entry created: {operation}",
        }
