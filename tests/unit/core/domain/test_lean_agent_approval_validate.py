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


@pytest.mark.spec("approval-gating.invalid_params_short_circuit_before_prompt")
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
    assert outcome["error_kind"] == "invalid_params"
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
    assert outcome["error_kind"] == "invalid_params"


@pytest.mark.spec("approval-gating.no_service_installed_runs_tool_anyway")
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


# ---------------------------------------------------------------------------
# Issue #177 — auto-approve for scheduled-workflow trigger origin.
# ---------------------------------------------------------------------------


class _RecordingApprover:
    """Approval service stub that records whether it was consulted."""

    def __init__(self) -> None:
        self.calls: list[ApprovalRequest] = []

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.calls.append(request)
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.GRANTED,
            decided_by="test",
            reason="ok",
        )


class _ScheduledOptInTool:
    """Tool that opts into auto-approve for the scheduled_workflow origin."""

    requires_approval = True
    approval_risk_level = ApprovalRiskLevel.MEDIUM
    name = "scheduled_opt_in"
    auto_approve_for_origins = frozenset({"scheduled_workflow"})

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return (True, None)

    def get_approval_preview(self, **kwargs: Any) -> str:
        return "preview"


@pytest.mark.spec("tools.auto_approve_for_origin_skips_gate")
@pytest.mark.spec("approval-gating.auto_approve_for_origin_skips_gate")
@pytest.mark.asyncio
async def test_scheduled_workflow_origin_auto_approves_opted_in_tool() -> None:
    """Issue #177: scheduler-fired calls bypass the human-decision queue."""
    from taskforce.core.domain.trigger_context import (
        SCHEDULED_WORKFLOW_ORIGIN,
        trigger_origin,
    )

    approver = _RecordingApprover()
    set_approval_service(approver)

    with trigger_origin(SCHEDULED_WORKFLOW_ORIGIN):
        outcome = await LeanAgent._maybe_request_approval(
            _StubAgent(),
            tool=_ScheduledOptInTool(),
            tool_name="scheduled_opt_in",
            tool_args={"message": "hi"},
            session_id="s1",
        )

    assert outcome is None, "auto-approve must let the call proceed"
    assert approver.calls == [], "approval service must not be consulted on the auto-approve path"


@pytest.mark.asyncio
async def test_interactive_call_still_hits_approval_queue() -> None:
    """Without a trigger origin, even opted-in tools still go through the queue."""
    approver = _RecordingApprover()
    set_approval_service(approver)

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_ScheduledOptInTool(),
        tool_name="scheduled_opt_in",
        tool_args={"message": "hi"},
        session_id="s1",
    )

    assert outcome is None, "approver granted, so the call proceeds"
    assert len(approver.calls) == 1, "but the human queue WAS consulted"
    # And the request carries no trigger_origin metadata.
    assert approver.calls[0].metadata == {}


@pytest.mark.asyncio
async def test_origin_set_but_tool_not_opted_in_still_hits_queue() -> None:
    """Origin alone is not enough — the tool must opt in explicitly."""
    from taskforce.core.domain.trigger_context import (
        SCHEDULED_WORKFLOW_ORIGIN,
        trigger_origin,
    )

    class _NotOptedIn:
        requires_approval = True
        approval_risk_level = ApprovalRiskLevel.MEDIUM
        name = "not_opted_in"
        # No auto_approve_for_origins — the gate must keep waiting.

        def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
            return (True, None)

        def get_approval_preview(self, **kwargs: Any) -> str:
            return "preview"

    approver = _RecordingApprover()
    set_approval_service(approver)

    with trigger_origin(SCHEDULED_WORKFLOW_ORIGIN):
        outcome = await LeanAgent._maybe_request_approval(
            _StubAgent(),
            tool=_NotOptedIn(),
            tool_name="not_opted_in",
            tool_args={"x": 1},
            session_id="s1",
        )

    assert outcome is None  # approver granted
    assert len(approver.calls) == 1, "non-opted-in tools always hit the queue"
    # The origin still rides along in metadata so the audit trail can show it.
    assert approver.calls[0].metadata == {"trigger_origin": SCHEDULED_WORKFLOW_ORIGIN}


# ---------------------------------------------------------------------------
# Issue #190 sub-item (a) — structured error_kind on every approval failure.
# ---------------------------------------------------------------------------


class _DenyingApprover:
    """Approval service that always denies."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.DENIED,
            decided_by="admin",
            reason="not allowed",
        )


class _TimingOutApprover:
    """Approval service that times out."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.TIMED_OUT,
            decided_by="system",
            reason="no admin response",
        )


class _CrashingApprover:
    """Approval service that itself fails — distinguishes pipeline
    breakage from a deliberate user decision."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        raise RuntimeError("queue offline")


class _SimpleApprovalTool:
    requires_approval = True
    approval_risk_level = ApprovalRiskLevel.LOW
    name = "simple_approval_tool"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return (True, None)

    def get_approval_preview(self, **kwargs: Any) -> str:
        return "preview"


@pytest.mark.spec("approval-gating.denied_decision_returns_terminal_failure")
@pytest.mark.asyncio
async def test_denied_approval_payload_carries_error_kind() -> None:
    set_approval_service(_DenyingApprover())

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_SimpleApprovalTool(),
        tool_name="simple_approval_tool",
        tool_args={"x": 1},
        session_id="s1",
    )

    assert outcome is not None
    assert outcome["success"] is False
    assert outcome["terminal_failure"] is True
    assert outcome["approval_status"] == "denied"
    # New contract — react loop / UI read error_kind to pick the
    # user-facing message and skip the retry nudge.
    assert outcome["error_kind"] == "approval_denied"


@pytest.mark.spec("approval-gating.timed_out_decision_distinct_from_denied")
@pytest.mark.asyncio
async def test_timed_out_approval_payload_carries_error_kind() -> None:
    set_approval_service(_TimingOutApprover())

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_SimpleApprovalTool(),
        tool_name="simple_approval_tool",
        tool_args={"x": 1},
        session_id="s1",
    )

    assert outcome is not None
    assert outcome["approval_status"] == "timed_out"
    assert outcome["error_kind"] == "approval_timeout"
    assert outcome["terminal_failure"] is True


@pytest.mark.spec("approval-gating.service_exception_yields_error_kind_approval_error")
@pytest.mark.asyncio
async def test_service_crash_payload_carries_error_kind() -> None:
    set_approval_service(_CrashingApprover())

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_SimpleApprovalTool(),
        tool_name="simple_approval_tool",
        tool_args={"x": 1},
        session_id="s1",
    )

    assert outcome is not None
    assert outcome["approval_status"] == "error"
    assert outcome["error_kind"] == "approval_error"
    assert outcome["terminal_failure"] is True


@pytest.mark.asyncio
async def test_validate_fail_payload_carries_error_kind() -> None:
    """Even the early validation-fail path (before the admin is asked)
    must surface error_kind so the loop classifies it consistently."""
    set_approval_service(_AlwaysGrantApprover())

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_RecordingValidator(valid=False, error="missing field"),
        tool_name="recording_validator",
        tool_args={"x": 1},
        session_id="s1",
    )

    assert outcome is not None
    # Validation failures use a distinct ``invalid_params`` kind — NOT the
    # terminal ``approval_error`` (which the spec reserves for a genuine
    # approval-service crash). Re-issuing with corrected args is fine, so
    # terminal_failure stays False (see approval-gating.md invariants / F3).
    assert outcome["error_kind"] == "invalid_params"
    assert outcome["terminal_failure"] is False
