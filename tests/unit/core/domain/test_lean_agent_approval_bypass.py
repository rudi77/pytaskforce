"""Tests for the profile-level ``approval_bypass_tools`` list.

Profile YAML can declare ``agent.approval_bypass_tools: [python, shell]``
to opt out of the ApprovalServiceProtocol gate for trusted single-user
workflows (local dev, scheduled butler runs). Tools listed here skip
the gate even when their ``requires_approval`` is ``True`` — so the
approval service is never consulted and the call proceeds directly to
``tool_executor.execute``.

This is distinct from ``ToolProtocol.auto_approve_for_origins``: that
mechanism requires a non-None trigger origin (scheduler/butler context)
and applies per-tool. The bypass list is profile-scoped and works for
interactive chat sessions too.
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog

from taskforce.application.infrastructure_overrides import (
    clear_infrastructure_overrides,
    get_approval_bypass_override,
    set_approval_bypass_override,
    set_approval_service,
)
from taskforce.application.settings_hydrator import hydrate_approval
from taskforce.core.domain.settings import APPROVAL
from taskforce.core.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
)
from taskforce.core.domain.lean_agent import LeanAgent
from taskforce.core.interfaces.tools import ApprovalRiskLevel


class _StubAgent:
    """Minimal agent stub: logger + bypass set."""

    def __init__(self, bypass: frozenset[str] = frozenset()) -> None:
        self.logger = structlog.get_logger("test")
        self._approval_bypass_tools = bypass


class _ApprovalTool:
    requires_approval = True
    approval_risk_level = ApprovalRiskLevel.HIGH
    name = "python"

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        return True, None

    def get_approval_preview(self, **kwargs: Any) -> str:
        return "python preview"


class _RecordingDenier:
    """Approver that fails the test if it gets called."""

    def __init__(self) -> None:
        self.calls: list[ApprovalRequest] = []

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.calls.append(request)
        return ApprovalDecision(
            request_id=request.request_id,
            status=ApprovalStatus.DENIED,
            decided_by="test",
            reason="should-have-been-bypassed",
        )


@pytest.fixture(autouse=True)
def _reset_overrides():
    clear_infrastructure_overrides()
    yield
    clear_infrastructure_overrides()


@pytest.mark.spec("tools.approval_bypass_list_skips_gate")
@pytest.mark.asyncio
async def test_bypass_list_skips_approval_service_entirely() -> None:
    """Tool in bypass list → gate returns None, service never consulted."""
    denier = _RecordingDenier()
    set_approval_service(denier)

    agent = _StubAgent(bypass=frozenset({"python"}))
    outcome = await LeanAgent._maybe_request_approval(
        agent,
        tool=_ApprovalTool(),
        tool_name="python",
        tool_args={"code": "print('hi')"},
        session_id="s1",
    )

    assert outcome is None, "bypass should allow tool execution to proceed"
    assert denier.calls == [], "approval service must NOT be invoked when bypassed"


@pytest.mark.asyncio
async def test_unbypassed_tool_still_hits_the_approver() -> None:
    """Sanity: empty bypass list → service is consulted as before."""
    denier = _RecordingDenier()
    set_approval_service(denier)

    agent = _StubAgent(bypass=frozenset())
    outcome = await LeanAgent._maybe_request_approval(
        agent,
        tool=_ApprovalTool(),
        tool_name="python",
        tool_args={"code": "print('hi')"},
        session_id="s1",
    )

    assert outcome is not None, "denial must surface as a structured payload"
    assert outcome["approval_status"] == "denied"
    assert len(denier.calls) == 1, "service should have been consulted exactly once"


@pytest.mark.asyncio
async def test_bypass_list_is_exact_match_not_substring() -> None:
    """A tool named 'python' must not be bypassed by 'py'."""
    denier = _RecordingDenier()
    set_approval_service(denier)

    agent = _StubAgent(bypass=frozenset({"py"}))
    outcome = await LeanAgent._maybe_request_approval(
        agent,
        tool=_ApprovalTool(),
        tool_name="python",
        tool_args={"code": "print('hi')"},
        session_id="s1",
    )

    assert outcome is not None, "partial-name bypass must NOT fire"
    assert outcome["approval_status"] == "denied"
    assert len(denier.calls) == 1


# ---------------------------------------------------------------------------
# Tenant-level override (settings store → infrastructure_overrides)
# ---------------------------------------------------------------------------


class _DictStore:
    """In-memory stand-in for SettingsStoreProtocol for the hydrator test."""

    def __init__(self, payload: dict[str, dict] | None = None) -> None:
        self._data = payload or {}

    def get(self, section: str) -> dict | None:
        return self._data.get(section)


def test_hydrate_approval_writes_override_from_settings_section() -> None:
    """``hydrate_approval`` must propagate bypass_tools to the global override."""
    store = _DictStore({APPROVAL: {"bypass_tools": ["python", "shell"]}})
    written = hydrate_approval(store)

    assert written == ["python", "shell"]
    assert get_approval_bypass_override() == frozenset({"python", "shell"})


def test_hydrate_approval_empty_section_clears_override() -> None:
    """Removing the section (or saving an empty list) clears the override."""
    set_approval_bypass_override(["python"])
    assert get_approval_bypass_override() == frozenset({"python"})

    hydrate_approval(_DictStore())  # no APPROVAL section
    assert get_approval_bypass_override() == frozenset()


def test_hydrate_approval_drops_non_string_entries() -> None:
    """One garbage entry must not poison the whole bypass list."""
    store = _DictStore({APPROVAL: {"bypass_tools": ["python", None, 42, "", "shell"]}})
    written = hydrate_approval(store)

    assert written == ["python", "shell"]
    assert get_approval_bypass_override() == frozenset({"python", "shell"})


@pytest.mark.asyncio
async def test_tenant_override_bypasses_even_with_empty_profile_list() -> None:
    """UI-edited bypass must work for agents with no profile-level config."""
    denier = _RecordingDenier()
    set_approval_service(denier)
    set_approval_bypass_override(["python"])

    agent = _StubAgent(bypass=frozenset())  # empty per-agent list
    outcome = await LeanAgent._maybe_request_approval(
        agent,
        tool=_ApprovalTool(),
        tool_name="python",
        tool_args={"code": "print('hi')"},
        session_id="s1",
    )

    assert outcome is None, "tenant-level override must skip the gate"
    assert denier.calls == [], "approval service must not be called when bypassed"


@pytest.mark.asyncio
async def test_profile_and_tenant_bypass_are_unioned() -> None:
    """Either source alone bypasses; together both still work independently."""
    denier = _RecordingDenier()
    set_approval_service(denier)

    # Profile bypasses 'shell', tenant bypasses 'python' — both pass.
    set_approval_bypass_override(["python"])
    agent = _StubAgent(bypass=frozenset({"shell"}))

    class _ShellTool(_ApprovalTool):
        name = "shell"

    py_outcome = await LeanAgent._maybe_request_approval(
        agent,
        tool=_ApprovalTool(),
        tool_name="python",
        tool_args={},
        session_id="s1",
    )
    shell_outcome = await LeanAgent._maybe_request_approval(
        agent,
        tool=_ShellTool(),
        tool_name="shell",
        tool_args={},
        session_id="s1",
    )

    assert py_outcome is None, "tenant bypass should skip python"
    assert shell_outcome is None, "profile bypass should skip shell"
    assert denier.calls == [], "neither source should call the service"


def test_clear_infrastructure_overrides_resets_approval_override() -> None:
    """Lifecycle test fixture relies on this."""
    set_approval_bypass_override(["python"])
    assert get_approval_bypass_override() == frozenset({"python"})

    clear_infrastructure_overrides()
    assert get_approval_bypass_override() == frozenset()
