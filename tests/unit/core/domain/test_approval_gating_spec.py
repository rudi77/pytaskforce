"""Spec-coverage tests for tool approval gating.

Covers the parts of ``docs/spec/approval-gating.md`` that lacked a focused
test: the no-requires-approval skip, per-call tenant-bypass re-read, the
preview-exception fallback, the CLI prompt service (stdin lock + stderr),
and the best-effort mission lifecycle hook.

Spec: docs/spec/approval-gating.md — tests tagged @pytest.mark.spec("approval-gating.*").
"""

from __future__ import annotations

import asyncio
import io
import time
from typing import Any

import pytest
import structlog

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    set_approval_bypass_override,
    set_approval_service,
    set_mission_lifecycle_hook,
)
from taskforce.core.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)
from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.interfaces.tools import ApprovalRiskLevel


class _StubAgent:
    """Minimal agent stub carrying just a logger + (optional) bypass set."""

    def __init__(self, bypass: frozenset[str] = frozenset()) -> None:
        from taskforce.application.infrastructure_overrides import (
            get_approval_bypass_override as _bypass_provider,
        )
        from taskforce.application.infrastructure_overrides import (
            get_approval_service as _service_provider,
        )

        self.logger = structlog.get_logger("test")
        self._approval_bypass_tools = bypass
        self._approval_service_provider = _service_provider
        self._approval_bypass_provider = _bypass_provider


class _RecordingApprover:
    """Approval service that records every request and grants by default."""

    def __init__(self, status: ApprovalStatus = ApprovalStatus.GRANTED) -> None:
        self.calls: list[ApprovalRequest] = []
        self._status = status

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.calls.append(request)
        return ApprovalDecision(
            request_id=request.request_id,
            status=self._status,
            decided_by="test",
            reason="recorded",
        )


class _ApprovalTool:
    requires_approval = True
    approval_risk_level = ApprovalRiskLevel.HIGH
    name = "python"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return True, None

    def get_approval_preview(self, **kwargs: Any) -> str:
        return "python preview"


@pytest.fixture(autouse=True)
def _reset_overrides():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


# ---------------------------------------------------------------------------
# Gate skip conditions
# ---------------------------------------------------------------------------


@pytest.mark.spec("approval-gating.tool_without_requires_approval_skips_gate")
@pytest.mark.asyncio
async def test_tool_without_requires_approval_skips_gate() -> None:
    """A tool with ``requires_approval`` False never reaches the service."""
    approver = _RecordingApprover(status=ApprovalStatus.DENIED)
    set_approval_service(approver)

    class _PlainTool:
        requires_approval = False
        name = "plain"

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_PlainTool(),
        tool_name="plain",
        tool_args={},
        session_id="s1",
    )

    assert outcome is None
    assert approver.calls == [], "ungated tool must not consult the service"


@pytest.mark.spec("approval-gating.tenant_bypass_reread_on_each_call")
@pytest.mark.asyncio
async def test_tenant_bypass_reread_on_each_call() -> None:
    """A mid-session edit to the tenant bypass list applies on the next call.

    The same agent instance is used for both calls — proving the override
    is read per call, not cached at construction time.
    """
    approver = _RecordingApprover(status=ApprovalStatus.DENIED)
    set_approval_service(approver)
    agent = _StubAgent()  # no profile-level bypass
    tool = _ApprovalTool()

    # First call: no override → gate runs → denied.
    first = await LeanAgent._maybe_request_approval(
        agent, tool=tool, tool_name="python", tool_args={}, session_id="s1"
    )
    assert first is not None and first["approval_status"] == "denied"

    # Edit the tenant override — no agent rebuild.
    set_approval_bypass_override(["python"])

    # Second call on the SAME agent: the re-read picks up the new bypass.
    second = await LeanAgent._maybe_request_approval(
        agent, tool=tool, tool_name="python", tool_args={}, session_id="s1"
    )
    assert second is None, "tenant bypass edit must take effect without restart"


@pytest.mark.spec("approval-gating.preview_exception_falls_back_to_tool_name")
@pytest.mark.asyncio
async def test_preview_exception_falls_back_to_tool_name() -> None:
    """A crash inside ``get_approval_preview`` falls back to the tool name."""
    approver = _RecordingApprover(status=ApprovalStatus.GRANTED)
    set_approval_service(approver)

    class _BadPreviewTool:
        requires_approval = True
        approval_risk_level = ApprovalRiskLevel.LOW
        name = "bad_preview"

        def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
            return True, None

        def get_approval_preview(self, **kwargs: Any) -> str:
            raise RuntimeError("preview boom")

    outcome = await LeanAgent._maybe_request_approval(
        _StubAgent(),
        tool=_BadPreviewTool(),
        tool_name="bad_preview",
        tool_args={"x": 1},
        session_id="s1",
    )

    # A buggy preview never aborts the gate — the call still proceeds.
    assert outcome is None
    assert len(approver.calls) == 1
    assert approver.calls[0].preview == "bad_preview"


# ---------------------------------------------------------------------------
# CLI prompt service
# ---------------------------------------------------------------------------


def _make_request(tool_name: str = "python", preview: str = "run code") -> ApprovalRequest:
    return ApprovalRequest(
        request_id=f"req-{tool_name}",
        session_id="s1",
        tool_name=tool_name,
        tool_params={},
        risk_level=ApprovalRiskLevel.HIGH,
        preview=preview,
    )


@pytest.mark.spec("approval-gating.cli_prompts_serialised_under_concurrent_calls")
@pytest.mark.asyncio
async def test_cli_prompts_serialised_under_concurrent_calls(monkeypatch) -> None:
    """Concurrent CLI approval prompts are serialised by the module lock."""
    from taskforce.infrastructure.approval import cli_approval

    # Reset the lazily-created lock so it binds to this test's event loop.
    monkeypatch.setattr(cli_approval, "_stdin_lock", None)

    state = {"active": 0, "peak": 0}

    def fake_ask(_prompt: str) -> str:
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.02)
        state["active"] -= 1
        return "y"

    monkeypatch.setattr(cli_approval, "_ask", fake_ask)

    service = cli_approval.CLIApprovalService()
    await asyncio.gather(*(service.request_approval(_make_request(f"t{i}")) for i in range(4)))

    assert state["peak"] == 1, "the stdin lock must keep prompts strictly serial"


@pytest.mark.spec("approval-gating.cli_prompt_writes_to_stderr_not_stdout")
def test_cli_prompt_writes_to_stderr_not_stdout(monkeypatch) -> None:
    """The CLI prompt is written to stderr so a captured stdout still shows it."""
    from taskforce.infrastructure.approval import cli_approval

    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    answer = cli_approval._ask("[approval] python (HIGH): run code → allow? [y/N] ")

    assert answer == "y"
    assert "[approval] python" in err.getvalue()
    assert out.getvalue() == "", "nothing must be written to stdout"


# ---------------------------------------------------------------------------
# Mission lifecycle hook
# ---------------------------------------------------------------------------


@pytest.mark.spec("approval-gating.mission_lifecycle_hook_errors_do_not_break_mission")
@pytest.mark.asyncio
async def test_mission_lifecycle_hook_errors_do_not_break_mission() -> None:
    """A hook that raises is logged, not propagated — the mission survives."""
    from taskforce.application.executor import AgentExecutor

    class _CrashingHook:
        async def on_mission_started(self, **_kwargs: Any) -> None:
            raise RuntimeError("audit pipeline down")

        async def on_mission_completed(self, **_kwargs: Any) -> None:
            raise RuntimeError("audit pipeline down")

    set_mission_lifecycle_hook(_CrashingHook())
    executor = AgentExecutor()

    # Neither emit must raise — a broken audit hook cannot break a mission.
    await executor._emit_mission_started(mission="m", session_id="s1", profile="dev", agent_id=None)
    await executor._emit_mission_completed(
        mission="m",
        session_id="s1",
        profile="dev",
        agent_id=None,
        success=True,
        error=None,
        duration_seconds=1.0,
    )
