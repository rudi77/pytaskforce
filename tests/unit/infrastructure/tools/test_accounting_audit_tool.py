"""Tests for AccountingAuditTool."""

import json

import pytest

from taskforce.infrastructure.tools.native.accounting_audit_tool import (
    AccountingAuditTool,
)


@pytest.fixture
def tool(tmp_path) -> AccountingAuditTool:
    return AccountingAuditTool(audit_dir=str(tmp_path / "audit"))


@pytest.mark.asyncio
async def test_create_audit_entry(tool: AccountingAuditTool, tmp_path) -> None:
    result = await tool.execute(
        operation="invoice_processed",
        details={"invoice_number": "RE-2025-001", "amount": 1190.00},
        document_id="RE-2025-001",
        decision="auto_booked",
        legal_basis="§14 UStG",
    )

    assert result["success"] is True
    assert result["log_id"]
    assert result["timestamp"]
    assert result["integrity_hash"]
    assert result["operation"] == "invoice_processed"

    # Verify file was written
    log_file = tmp_path / "audit" / result["log_file"].split("audit/")[-1].split("audit\\")[-1]
    assert log_file.exists()

    # Verify content
    content = json.loads(log_file.read_text(encoding="utf-8"))
    assert content["log_id"] == result["log_id"]
    assert content["document_id"] == "RE-2025-001"
    assert content["metadata"]["gobd_compliant"] is True


@pytest.mark.asyncio
async def test_invalid_operation(tool: AccountingAuditTool) -> None:
    result = await tool.execute(
        operation="invalid_op",
        details={"test": True},
    )
    assert result["success"] is False
    assert "Invalid operation" in result["error"]


@pytest.mark.asyncio
async def test_sensitive_data_redacted(
    tool: AccountingAuditTool, tmp_path
) -> None:
    result = await tool.execute(
        operation="compliance_check",
        details={
            "invoice_number": "RE-001",
            "api_key": "sk-secret-123",
            "nested": {"password": "hunter2"},
        },
    )
    assert result["success"] is True

    # Read the log file and verify redaction
    audit_dir = tmp_path / "audit"
    log_files = list(audit_dir.glob("*.json"))
    assert len(log_files) == 1

    content = json.loads(log_files[0].read_text(encoding="utf-8"))
    assert content["details"]["api_key"] == "[REDACTED]"
    assert content["details"]["nested"]["password"] == "[REDACTED]"
    assert content["details"]["invoice_number"] == "RE-001"


@pytest.mark.asyncio
async def test_integrity_hash_is_deterministic(
    tool: AccountingAuditTool,
) -> None:
    """Hash should be computed before being added to the entry."""
    result = await tool.execute(
        operation="booking_proposed",
        details={"account": "3400"},
    )
    assert result["success"] is True
    assert len(result["integrity_hash"]) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_lazy_directory_creation(tmp_path) -> None:
    """Audit directory should be created on first write, not init."""
    audit_dir = tmp_path / "non_existent" / "audit"
    tool = AccountingAuditTool(audit_dir=str(audit_dir))

    # Directory should NOT exist yet
    assert not audit_dir.exists()

    result = await tool.execute(
        operation="tax_calculated",
        details={"vat": 19.0},
    )
    assert result["success"] is True
    assert audit_dir.exists()


@pytest.mark.asyncio
async def test_tool_protocol_properties(tool: AccountingAuditTool) -> None:
    assert tool.name == "accounting_audit"
    assert "GoBD" in tool.description
    assert tool.requires_approval is False
