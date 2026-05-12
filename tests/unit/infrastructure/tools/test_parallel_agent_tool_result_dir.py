"""Per-scope routing for ``ParallelAgentTool`` sub-agent results (#212).

The tool persists oversized sub-agent results to a directory named
``sub_agent_results/``. Pre-#212 this was hardcoded to
``<work_dir>/sub_agent_results/`` — a per-(tenant, user) deployment
therefore mixed every user's runs in one directory. The new
``set_sub_agent_result_dir_override`` hook lets the enterprise plugin
route the directory per scope.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from taskforce.application import infrastructure_overrides
from taskforce.infrastructure.tools.orchestration.parallel_agent_tool import (
    ParallelAgentTool,
)


@pytest.fixture(autouse=True)
def _reset_override():
    """Drop any installed override between tests so the standalone
    fallback assertions stay deterministic."""
    infrastructure_overrides.set_sub_agent_result_dir_override(None)
    yield
    infrastructure_overrides.set_sub_agent_result_dir_override(None)


def _make_tool(work_dir: str | None = None) -> ParallelAgentTool:
    spawner = MagicMock()
    return ParallelAgentTool(sub_agent_spawner=spawner, work_dir=work_dir)


def test_resolve_result_dir_falls_back_to_work_dir():
    """No override → ``<work_dir>/sub_agent_results``. Bit-for-bit
    pre-#212 behaviour."""
    tool = _make_tool(work_dir=".dev")
    assert tool._resolve_result_dir() == Path(".dev") / "sub_agent_results"


def test_resolve_result_dir_falls_back_to_taskforce_when_no_work_dir():
    """No override and no work_dir → ``.taskforce/sub_agent_results``."""
    tool = _make_tool()
    assert tool._resolve_result_dir() == Path(".taskforce") / "sub_agent_results"


def test_resolve_result_dir_consults_override(tmp_path: Path):
    """Override wins over work_dir so the per-(tenant, user) plugin
    can route the directory regardless of what the tool was built
    with."""
    target = tmp_path / "tenants" / "acme" / "users" / "alice" / "sub_agent_results"
    infrastructure_overrides.set_sub_agent_result_dir_override(lambda: target)

    tool = _make_tool(work_dir=".dev")
    assert tool._resolve_result_dir() == target


def test_resolve_result_dir_consults_override_per_call(tmp_path: Path):
    """The override is called every time so a process-shared tool can
    switch scope between calls (matches how ContextVar-bound tenant
    + user context change per request)."""
    state = {"target": tmp_path / "alice" / "sub_agent_results"}
    infrastructure_overrides.set_sub_agent_result_dir_override(
        lambda: state["target"]
    )

    tool = _make_tool()
    assert tool._resolve_result_dir() == tmp_path / "alice" / "sub_agent_results"

    state["target"] = tmp_path / "bob" / "sub_agent_results"
    assert tool._resolve_result_dir() == tmp_path / "bob" / "sub_agent_results"


def test_resolve_result_dir_swallows_override_exception():
    """A misbehaving override (no tenant scope yet) must not crash a
    routine parallel-dispatch — we fall back to the work_dir default
    so the parent agent's mission can still complete."""
    def _broken():
        raise RuntimeError("no tenant scope")

    infrastructure_overrides.set_sub_agent_result_dir_override(_broken)
    tool = _make_tool(work_dir=".dev")
    assert tool._resolve_result_dir() == Path(".dev") / "sub_agent_results"
