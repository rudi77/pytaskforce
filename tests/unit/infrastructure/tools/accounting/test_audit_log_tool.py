"""
Tests for AuditLogTool.

Tests GoBD-compliant audit logging.
"""

import json
import pytest
from pathlib import Path

from taskforce.infrastructure.tools.native.accounting.audit_log_tool import (
    AuditLogTool,
)


@pytest.fixture
def audit_dir(tmp_path: Path) -> Path:
    """Create temporary audit directory."""
    audit_path = tmp_path / "audit"
    return audit_path


@pytest.fixture
def audit_tool(audit_dir: Path) -> AuditLogTool:
    """Create AuditLogTool with temporary directory."""
    return AuditLogTool(audit_path=str(audit_dir))


class TestAuditLogTool:
    """Test suite for AuditLogTool."""

    def test_tool_metadata(self, audit_tool: AuditLogTool):
        """Test tool metadata properties."""
        assert audit_tool.name == "audit_log"
        assert "GoBD" in audit_tool.description
        assert audit_tool.requires_approval is False

    def test_parameters_schema(self, audit_tool: AuditLogTool):
        """Test parameter schema structure."""
        schema = audit_tool.parameters_schema
        assert schema["type"] == "object"
        assert "operation" in schema["properties"]
        assert "details" in schema["properties"]
        assert "operation" in schema["required"]
        assert "details" in schema["required"]

    def test_validate_params_missing_operation(self, audit_tool: AuditLogTool):
        """Test validation fails without operation."""
        valid, error = audit_tool.validate_params(details={})
        assert valid is False
        assert "operation" in error

    def test_validate_params_missing_details(self, audit_tool: AuditLogTool):
        """Test validation fails without details."""
        valid, error = audit_tool.validate_params(operation="invoice_processed")
        assert valid is False
        assert "details" in error

    def test_validate_params_invalid_operation(self, audit_tool: AuditLogTool):
        """Test validation fails with invalid operation."""
        valid, error = audit_tool.validate_params(
            operation="invalid_operation",
            details={}
        )
        assert valid is False
        assert "Invalid operation" in error

    def test_validate_params_valid(self, audit_tool: AuditLogTool):
        """Test validation passes with valid data."""
        valid, error = audit_tool.validate_params(
            operation="invoice_processed",
            details={"invoice_id": "123"}
        )
        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_create_audit_log_entry(
        self, audit_tool: AuditLogTool, audit_dir: Path
    ):
        """Test creating an audit log entry."""
        result = await audit_tool.execute(
            operation="invoice_processed",
            details={"invoice_number": "RE-2024-001", "amount": 1000.00},
            document_id="RE-2024-001",
            decision="approved",
            legal_basis="§14 UStG"
        )

        assert result["success"] is True
        assert "log_id" in result
        assert "timestamp" in result
        assert "log_file" in result
        assert "integrity_hash" in result

        # Verify file was created
        log_file = Path(result["log_file"])
        assert log_file.exists()

    @pytest.mark.asyncio
    async def test_audit_log_content(
        self, audit_tool: AuditLogTool, audit_dir: Path
    ):
        """Test audit log file content."""
        result = await audit_tool.execute(
            operation="compliance_check",
            details={"status": "compliant", "fields_checked": 10},
            document_id="INV-001",
            decision="passed",
            legal_basis="§14 Abs. 4 UStG",
            user_id="user-123"
        )

        # Read and verify log content
        log_file = Path(result["log_file"])
        with open(log_file, encoding="utf-8") as f:
            log_data = json.load(f)

        assert log_data["operation"] == "compliance_check"
        assert log_data["document_id"] == "INV-001"
        assert log_data["decision"] == "passed"
        assert log_data["legal_basis"] == "§14 Abs. 4 UStG"
        assert log_data["user_id"] == "user-123"
        assert log_data["details"]["status"] == "compliant"
        assert "integrity_hash" in log_data
        assert "timestamp" in log_data

    @pytest.mark.asyncio
    async def test_integrity_hash(
        self, audit_tool: AuditLogTool, audit_dir: Path
    ):
        """Test that integrity hash is SHA-256."""
        result = await audit_tool.execute(
            operation="booking_proposed",
            details={"account": "4930", "amount": 100}
        )

        assert result["success"] is True
        # SHA-256 produces 64 hex characters
        assert len(result["integrity_hash"]) == 64

    @pytest.mark.asyncio
    async def test_timestamp_format(
        self, audit_tool: AuditLogTool
    ):
        """Test timestamp is ISO 8601 format with timezone."""
        result = await audit_tool.execute(
            operation="manual_review",
            details={"reviewer": "accountant"}
        )

        assert result["success"] is True
        timestamp = result["timestamp"]
        # ISO 8601 format with timezone
        assert "T" in timestamp
        assert "+" in timestamp or "Z" in timestamp

    @pytest.mark.asyncio
    async def test_gobd_metadata(
        self, audit_tool: AuditLogTool, audit_dir: Path
    ):
        """Test GoBD compliance metadata in log."""
        result = await audit_tool.execute(
            operation="invoice_processed",
            details={"test": "data"}
        )

        log_file = Path(result["log_file"])
        with open(log_file, encoding="utf-8") as f:
            log_data = json.load(f)

        assert "metadata" in log_data
        assert log_data["metadata"]["gobd_compliant"] is True
        assert log_data["metadata"]["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_sanitize_sensitive_data(
        self, audit_tool: AuditLogTool, audit_dir: Path
    ):
        """Test that sensitive data is redacted."""
        result = await audit_tool.execute(
            operation="invoice_processed",
            details={
                "invoice_number": "123",
                "api_key": "secret-key-12345",
                "password": "supersecret",
                "nested": {"token": "abc123"}
            }
        )

        log_file = Path(result["log_file"])
        with open(log_file, encoding="utf-8") as f:
            log_data = json.load(f)

        # Sensitive fields should be redacted
        assert log_data["details"]["api_key"] == "[REDACTED]"
        assert log_data["details"]["password"] == "[REDACTED]"
        assert log_data["details"]["nested"]["token"] == "[REDACTED]"
        # Non-sensitive fields should be preserved
        assert log_data["details"]["invoice_number"] == "123"

    @pytest.mark.asyncio
    async def test_file_naming_chronological(
        self, audit_tool: AuditLogTool, audit_dir: Path
    ):
        """Test that log files are named for chronological ordering."""
        result = await audit_tool.execute(
            operation="invoice_processed",
            details={"test": "data"}
        )

        log_file = Path(result["log_file"])
        # Filename should start with date prefix YYYYMMDD_HHMMSS
        filename = log_file.name
        assert filename.count("_") >= 2
        assert filename.endswith(".json")

    @pytest.mark.asyncio
    async def test_all_valid_operations(
        self, audit_tool: AuditLogTool
    ):
        """Test all valid operation types."""
        valid_operations = [
            "invoice_processed",
            "compliance_check",
            "booking_proposed",
            "manual_review",
            "document_extracted",
            "rule_applied",
            "tax_calculated",
            "user_decision"
        ]

        for operation in valid_operations:
            result = await audit_tool.execute(
                operation=operation,
                details={"test": operation}
            )
            assert result["success"] is True, f"Failed for operation: {operation}"

    @pytest.mark.asyncio
    async def test_directory_creation(self, tmp_path: Path):
        """Test that audit directory is created if not exists."""
        new_audit_path = tmp_path / "new_audit_dir"
        assert not new_audit_path.exists()

        tool = AuditLogTool(audit_path=str(new_audit_path))
        assert new_audit_path.exists()

    @pytest.mark.asyncio
    async def test_get_audit_trail(
        self, audit_tool: AuditLogTool
    ):
        """Test retrieving audit trail entries."""
        # Create some log entries
        for i in range(3):
            await audit_tool.execute(
                operation="invoice_processed",
                details={"index": i},
                document_id=f"DOC-{i}"
            )

        # Retrieve audit trail
        result = await audit_tool.get_audit_trail()

        assert result["success"] is True
        assert result["count"] == 3
        assert len(result["entries"]) == 3

    @pytest.mark.asyncio
    async def test_get_audit_trail_filter_document(
        self, audit_tool: AuditLogTool
    ):
        """Test filtering audit trail by document ID."""
        await audit_tool.execute(
            operation="invoice_processed",
            details={"test": 1},
            document_id="DOC-A"
        )
        await audit_tool.execute(
            operation="invoice_processed",
            details={"test": 2},
            document_id="DOC-B"
        )

        result = await audit_tool.get_audit_trail(document_id="DOC-A")

        assert result["success"] is True
        assert result["count"] == 1
        assert result["entries"][0]["document_id"] == "DOC-A"

    @pytest.mark.asyncio
    async def test_get_audit_trail_filter_operation(
        self, audit_tool: AuditLogTool
    ):
        """Test filtering audit trail by operation type."""
        await audit_tool.execute(
            operation="invoice_processed",
            details={"test": 1}
        )
        await audit_tool.execute(
            operation="compliance_check",
            details={"test": 2}
        )

        result = await audit_tool.get_audit_trail(operation="compliance_check")

        assert result["success"] is True
        assert result["count"] == 1
        assert result["entries"][0]["operation"] == "compliance_check"
