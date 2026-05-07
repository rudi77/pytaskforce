"""Regression test for the validate_params call inside the approval gate.

Before the fix, ``LeanAgent._maybe_request_approval`` invoked
``validate(tool_args)`` — passing the args dict positionally — but
every tool's ``validate_params`` signature is ``(self, **kwargs)``.
That mismatch produced a TypeError on every approval-gated call when
an approval service was actually installed, surfacing as a silent
"invalid params: validate_params() takes …" rejection regardless of
the actual arguments. The fix uses ``validate(**tool_args)`` and
honours the documented ``(is_valid, error_msg)`` return contract.
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_approval_service,
)
from taskforce.core.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)
from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.interfaces.tools import ApprovalRiskLevel


class _StubAgent:
    """Bare-minimum stand-in for LeanAgent that only carries a logger.

    ``_maybe_request_approval`` only touches ``self.logger``, so we can
    invoke the unbound coroutine with a stub instance and avoid wiring
    up the full Agent constructor (LLM provider, state manager, …).
    """

    def __init__(self) -> None:
        self.logger = structlog.get_logger("test")


class _RecordingValidator:
    """Tool stub that records every kwargs dict its validator sees."""

    requires_approval = True
    approval_risk_level = ApprovalRiskLevel.LOW
    name = "recording_validator"

    def __init__(self, valid: bool = True, error: str | None = None) -> None:
        self._valid = valid
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        self.calls.append(dict(kwargs))
        return (self._valid, self._error)

    def get_approval_preview(self, **kwargs: Any) -> str:
        return "preview"


class _AlwaysGrantApprover:
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.GRANTED,
            decided_by="test",
            reason="ok",
        )


@pytest.fixture(autouse=True)
def _reset_overrides():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


@pytest.mark.asyncio
async def test_validator_receives_kwargs_not_positional_dict() -> None:
    """The fix: ``validate(**tool_args)`` so kwargs unpacking works."""
    set_approval_service(_AlwaysGrantApprover())
    tool = _RecordingValidator(valid=True)

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=tool,
        tool_name="recording_validator",
        tool_args={"foo": 1, "bar": "baz"},
        session_id="s1",
    )

    assert outcome is None, "approval should pass through"
    assert tool.calls == [{"foo": 1, "bar": "baz"}]


@pytest.mark.asyncio
async def test_validator_failure_short_circuits_approval() -> None:
    """A False (is_valid, error_msg) result rejects without asking the admin."""
    set_approval_service(_AlwaysGrantApprover())
    tool = _RecordingValidator(valid=False, error="missing remind_at")

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=tool,
        tool_name="recording_validator",
        tool_args={"message": "hi"},
        session_id="s1",
    )

    assert outcome is not None
    assert outcome["success"] is False
    assert outcome["approval_status"] == "error"
    assert "missing remind_at" in outcome["error"]


@pytest.mark.asyncio
async def test_validator_can_return_plain_bool() -> None:
    """Older custom tools that return a bare bool still work."""

    class _BoolTool:
        requires_approval = True
        approval_risk_level = ApprovalRiskLevel.LOW
        name = "bool_tool"

        def validate_params(self, **kwargs: Any) -> bool:
            return False

        def get_approval_preview(self, **kwargs: Any) -> str:
            return "preview"

    set_approval_service(_AlwaysGrantApprover())
    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_BoolTool(),
        tool_name="bool_tool",
        tool_args={"x": 1},
        session_id="s1",
    )

    assert outcome is not None
    assert outcome["success"] is False
    assert outcome["approval_status"] == "error"


@pytest.mark.asyncio
async def test_no_approval_service_skips_validation_entirely() -> None:
    """Sanity: with no approver installed, the gate is skipped."""
    tool = _RecordingValidator(valid=False, error="should not be called")

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=tool,
        tool_name="recording_validator",
        tool_args={"x": 1},
        session_id="s1",
    )

    assert outcome is None
    assert tool.calls == []
