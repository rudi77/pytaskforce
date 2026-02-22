"""Tests for parallel tool execution helpers."""

from __future__ import annotations

import asyncio
import sys
import time
import types
from typing import Any


def _install_structlog_stub() -> None:
    try:
        import structlog  # noqa: F401
        import structlog.testing  # noqa: F401

        return
    except Exception:
        pass

    structlog_module = types.ModuleType("structlog")

    class _StubLogger:
        def bind(self, **kwargs: Any) -> _StubLogger:
            return self

        def warning(self, *args: Any, **kwargs: Any) -> None:
            return None

        def info(self, *args: Any, **kwargs: Any) -> None:
            return None

        def error(self, *args: Any, **kwargs: Any) -> None:
            return None

        def debug(self, *args: Any, **kwargs: Any) -> None:
            return None

    def _get_logger(*args: Any, **kwargs: Any) -> _StubLogger:
        return _StubLogger()

    structlog_module.get_logger = _get_logger  # type: ignore[attr-defined]
    structlog_module.make_filtering_bound_logger = (  # type: ignore[attr-defined]
        lambda *args, **kwargs: _StubLogger
    )
    structlog_module.configure = lambda *args, **kwargs: None  # type: ignore[attr-defined]

    testing_module = types.ModuleType("structlog.testing")
    testing_module.LogCapture = object  # type: ignore[attr-defined]

    typing_module = types.ModuleType("structlog.typing")
    typing_module.FilteringBoundLogger = Any  # type: ignore[attr-defined]

    sys.modules.setdefault("structlog", structlog_module)
    sys.modules.setdefault("structlog.testing", testing_module)
    sys.modules.setdefault("structlog.typing", typing_module)


_install_structlog_stub()

from taskforce.core.domain.planning_helpers import (
    ToolCallRequest,
    _execute_tool_calls,
)
from taskforce.core.interfaces.tools import ApprovalRiskLevel, ToolProtocol


class FakeAgent:
    """Minimal agent stub for tool execution tests."""

    def __init__(self, tools: list[ToolProtocol], max_parallel_tools: int) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.max_parallel_tools = max_parallel_tools

    async def _execute_tool(
        self, tool_name: str, tool_args: dict[str, object], session_id: str | None = None
    ) -> dict[str, object]:
        tool = self.tools[tool_name]
        return await tool.execute(**tool_args)


class SleepTool(ToolProtocol):
    """Tool that sleeps to simulate I/O latency."""

    def __init__(self, name: str, delay: float, supports_parallelism: bool) -> None:
        self._name = name
        self._delay = delay
        self._supports_parallelism = supports_parallelism

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Sleep tool for testing."

    @property
    def parameters_schema(self) -> dict[str, object]:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def requires_approval(self) -> bool:
        return False

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.LOW

    @property
    def supports_parallelism(self) -> bool:
        return self._supports_parallelism

    def get_approval_preview(self, **kwargs: object) -> str:
        return f"Tool: {self.name}"

    async def execute(self, **kwargs: object) -> dict[str, object]:
        await asyncio.sleep(self._delay)
        return {"success": True, "output": self.name}

    def validate_params(self, **kwargs: object) -> tuple[bool, str | None]:
        return True, None


def test_execute_tool_calls_runs_parallel_when_enabled() -> None:
    tools = [
        SleepTool("tool_a", 0.25, True),
        SleepTool("tool_b", 0.25, True),
    ]
    agent = FakeAgent(tools, max_parallel_tools=2)
    requests = [
        ToolCallRequest("call_a", "tool_a", {}),
        ToolCallRequest("call_b", "tool_b", {}),
    ]

    start_time = time.monotonic()
    results = asyncio.run(_execute_tool_calls(agent, requests))
    duration = time.monotonic() - start_time

    assert duration < 0.45
    assert [request.tool_call_id for request, _ in results] == ["call_a", "call_b"]


def test_execute_tool_calls_preserves_order_for_mixed_tools() -> None:
    tools = [
        SleepTool("serial_tool", 0.01, False),
        SleepTool("parallel_tool", 0.01, True),
    ]
    agent = FakeAgent(tools, max_parallel_tools=2)
    requests = [
        ToolCallRequest("call_serial", "serial_tool", {}),
        ToolCallRequest("call_parallel", "parallel_tool", {}),
    ]

    results = asyncio.run(_execute_tool_calls(agent, requests))

    assert [request.tool_call_id for request, _ in results] == [
        "call_serial",
        "call_parallel",
    ]
    assert [result["output"] for _, result in results] == [
        "serial_tool",
        "parallel_tool",
    ]
