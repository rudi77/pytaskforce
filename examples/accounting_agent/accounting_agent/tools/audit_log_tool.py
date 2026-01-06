"""
GoBD-compliant audit logging tool.

This tool creates immutable, timestamped audit records for all
accounting operations to ensure compliance with GoBD (Grundsätze
zur ordnungsmäßigen Führung und Aufbewahrung von Büchern,
Aufzeichnungen und Unterlagen in elektronischer Form).
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from accounting_agent.tools.tool_base import ApprovalRiskLevel


class AuditLogTool:
    """
    GoBD-compliant audit logging for all accounting operations.

    Creates immutable, timestamped audit records with:
    - Unique log ID (UUID)
    - ISO 8601 timestamp (UTC)
    - Operation type
    - Document reference
    - Decision rationale
    - Legal basis
    - Integrity hash (SHA-256)

    Files are written as JSON and cannot be modified after creation.
    """

    VALID_OPERATIONS = {
        "invoice_processed",
        "compliance_check",
        "booking_proposed",
        "manual_review",
        "document_extracted",
        "rule_applied",
        "tax_calculated",
        "user_decision"
    }

    def __init__(self, audit_path: str = ".taskforce_accounting/audit/"):
        """
        Initialize AuditLogTool with audit directory.

        Args:
            audit_path: Path to directory for storing audit logs
        """
        self._audit_path = Path(audit_path)
        self._audit_path.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        """Return tool name."""
        return "audit_log"

    @property
    def description(self) -> str:
        """Return tool description."""
        return (
            "Create GoBD-compliant audit log entries. "
            "Records accounting operations with timestamps, "
            "user context, and decision rationale. "
            "Entries are immutable and include integrity hashes."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """Return OpenAI function calling compatible parameter schema."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Type of operation being logged",
                    "enum": list(self.VALID_OPERATIONS)
                },
                "document_id": {
                    "type": "string",
                    "description": "Reference ID of the processed document (invoice number, file name)"
                },
                "details": {
                    "type": "object",
                    "description": "Operation-specific details (input data, results)"
                },
                "decision": {
                    "type": "string",
                    "description": "Decision or outcome of the operation"
                },
                "legal_basis": {
                    "type": "string",
                    "description": "Legal reference for the decision (e.g., §14 UStG)"
                },
                "user_id": {
                    "type": "string",
                    "description": "ID of the user who triggered the operation"
                }
            },
            "required": ["operation", "details"]
        }

    @property
    def requires_approval(self) -> bool:
        """Logging is automatic, no approval required."""
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        """Low risk - creates audit trail."""
        return ApprovalRiskLevel.LOW

    def get_approval_preview(self, **kwargs: Any) -> str:
        """Generate human-readable preview of operation."""
        operation = kwargs.get("operation", "unknown")
        document_id = kwargs.get("document_id", "N/A")
        return (
            f"Tool: {self.name}\n"
            f"Operation: Create audit log entry\n"
            f"Type: {operation}\n"
            f"Document: {document_id}"
        )

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters before execution."""
        if "operation" not in kwargs:
            return False, "Missing required parameter: operation"
        if "details" not in kwargs:
            return False, "Missing required parameter: details"

        operation = kwargs["operation"]
        if operation not in self.VALID_OPERATIONS:
            return False, f"Invalid operation: {operation}. Valid: {list(self.VALID_OPERATIONS)}"

        if not isinstance(kwargs["details"], dict):
            return False, "details must be a dictionary"

        return True, None

    async def execute(
        self,
        operation: str,
        details: dict[str, Any],
        document_id: str | None = None,
        decision: str | None = None,
        legal_basis: str | None = None,
        user_id: str | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Create immutable audit log entry.

        Args:
            operation: Type of operation
            details: Operation-specific details
            document_id: Reference to processed document
            decision: Decision or outcome
            legal_basis: Legal reference
            user_id: User who triggered operation

        Returns:
            Dictionary with:
            - success: bool
            - log_id: Unique log entry ID
            - timestamp: ISO 8601 timestamp
            - log_file: Path to created log file
            - integrity_hash: SHA-256 hash of entry
        """
        try:
            log_id = str(uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()

            # Create log entry
            log_entry = {
                "log_id": log_id,
                "timestamp": timestamp,
                "operation": operation,
                "document_id": document_id,
                "details": self._sanitize_details(details),
                "decision": decision,
                "legal_basis": legal_basis,
                "user_id": user_id,
                "metadata": {
                    "version": "1.0",
                    "gobd_compliant": True,
                    "created_by": "taskforce_accounting"
                }
            }

            # Calculate integrity hash (before adding hash to entry)
            content_for_hash = json.dumps(log_entry, sort_keys=True, ensure_ascii=False)
            integrity_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
            log_entry["integrity_hash"] = integrity_hash

            # Create filename with timestamp for chronological ordering
            date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            log_file = self._audit_path / f"{date_prefix}_{log_id[:8]}.json"

            # Write immutable log file
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_entry, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "log_id": log_id,
                "timestamp": timestamp,
                "log_file": str(log_file),
                "integrity_hash": integrity_hash,
                "operation": operation,
                "message": f"Audit log entry created: {operation}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create audit log: {str(e)}",
                "error_type": type(e).__name__
            }

    def _sanitize_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize details for logging, removing sensitive data.

        Args:
            details: Raw details dictionary

        Returns:
            Sanitized details dictionary
        """
        # Create a copy to avoid modifying original
        sanitized = {}

        sensitive_keys = {"password", "api_key", "secret", "token", "credential"}

        for key, value in details.items():
            key_lower = key.lower()

            # Mask sensitive fields
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_details(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    async def get_audit_trail(
        self,
        document_id: str | None = None,
        operation: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100
    ) -> dict[str, Any]:
        """
        Retrieve audit trail entries (read-only query).

        This is a utility method for reading the audit log.
        Note: This is NOT exposed as a separate tool parameter.

        Args:
            document_id: Filter by document ID
            operation: Filter by operation type
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            limit: Maximum entries to return

        Returns:
            Dictionary with matching audit entries
        """
        try:
            entries = []

            for log_file in sorted(self._audit_path.glob("*.json"))[:limit]:
                with open(log_file, encoding="utf-8") as f:
                    entry = json.load(f)

                # Apply filters
                if document_id and entry.get("document_id") != document_id:
                    continue
                if operation and entry.get("operation") != operation:
                    continue

                entries.append(entry)

            return {
                "success": True,
                "entries": entries,
                "count": len(entries),
                "total_files": len(list(self._audit_path.glob("*.json")))
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
