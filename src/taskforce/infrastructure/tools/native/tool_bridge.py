"""
Tool Bridge – Expose agent tools as synchronous Python functions.

Allows the PythonTool to call other agent tools directly within a single
``exec()`` call, eliminating extra LLM round-trips for sequential
tool operations (e.g. read file → process → write file).

Usage inside PythonTool code::

    content = tool_file_read(path="data.json")["output"]
    processed = json.loads(content)
    tool_file_write(path="out.json", content=json.dumps(processed))
    result = "Done"

Design notes:
- Each tool is wrapped as ``tool_<name>(**kwargs) -> dict`` in the
  Python namespace.
- ``python`` tool is excluded to prevent recursion.
- Uses a dedicated background event loop on a daemon thread so that
  synchronous code inside ``exec()`` can await async tools without
  blocking (or deadlocking) the caller's event loop.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import structlog

from taskforce.core.interfaces.tools import ToolProtocol

logger = structlog.get_logger(__name__)

# Tools excluded from bridging (recursion / security risks)
_EXCLUDED_TOOLS = frozenset({"python", "ask_user"})

# ---------------------------------------------------------------------------
# Shared background event loop (one per process, lazily created)
# ---------------------------------------------------------------------------
_bridge_loop: asyncio.AbstractEventLoop | None = None
_bridge_loop_lock = threading.Lock()


def _get_bridge_loop() -> asyncio.AbstractEventLoop:
    """Return the shared background event loop, creating it on first call."""
    global _bridge_loop
    if _bridge_loop is not None and _bridge_loop.is_running():
        return _bridge_loop

    with _bridge_loop_lock:
        if _bridge_loop is not None and _bridge_loop.is_running():
            return _bridge_loop

        loop = asyncio.new_event_loop()

        def _run(lp: asyncio.AbstractEventLoop) -> None:
            asyncio.set_event_loop(lp)
            lp.run_forever()

        t = threading.Thread(target=_run, args=(loop,), daemon=True)
        t.start()
        _bridge_loop = loop
        return loop


class ToolBridge:
    """Wraps a set of ToolProtocol instances as synchronous callables.

    Args:
        tools: Mapping of tool name → ToolProtocol instance.
    """

    def __init__(self, tools: dict[str, ToolProtocol], **_kw: Any) -> None:
        self._tools = {name: tool for name, tool in tools.items() if name not in _EXCLUDED_TOOLS}
        self._logger = logger.bind(component="ToolBridge")

    @property
    def available_tool_names(self) -> list[str]:
        """Return the names of all bridged tools."""
        return list(self._tools.keys())

    def get_namespace(self) -> dict[str, Any]:
        """Return a dict of ``tool_<name>`` → callable for injection into exec().

        Each callable has the signature ``(**kwargs) -> dict[str, Any]``.
        """
        namespace: dict[str, Any] = {}
        for name, tool in self._tools.items():
            func_name = f"tool_{name}"
            namespace[func_name] = self._make_sync_wrapper(name, tool)
        return namespace

    def _make_sync_wrapper(self, name: str, tool: ToolProtocol):
        """Create a synchronous wrapper for an async tool.execute()."""

        def wrapper(**kwargs: Any) -> dict[str, Any]:
            self._logger.debug("tool_bridge_call", tool=name, params=list(kwargs.keys()))
            coro = tool.execute(**kwargs)
            return self._run_async(coro)

        wrapper.__name__ = f"tool_{name}"
        wrapper.__doc__ = f"Call the '{name}' tool. Returns dict with result."
        return wrapper

    def _run_async(self, coro) -> Any:
        """Run an async coroutine from a sync context.

        Schedules ``coro`` on the shared background event loop (which runs
        on a dedicated daemon thread) and blocks until the result is ready.
        This avoids deadlocks when ``exec()`` runs on the caller's event
        loop thread.
        """
        loop = _get_bridge_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=120)

    def description_suffix(self) -> str:
        """Return a description snippet listing available bridge functions."""
        funcs = ", ".join(f"`tool_{n}(**kwargs)`" for n in sorted(self._tools))
        return (
            f"\n\nTool chaining: call other tools directly from Python code "
            f"without extra LLM round-trips. Available functions: {funcs}. "
            f"Each returns a dict (same as the tool's normal output). "
            f"Example: `content = tool_file_read(path='data.json')['output']`"
        )
