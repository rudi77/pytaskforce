"""Tool execution helpers for Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.tool_result_store import ToolResultStoreProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.tools.tool_converter import (
    create_tool_result_preview,
    tool_result_preview_to_message,
    tool_result_to_message,
)


class ToolExecutor:
    """Execute tools and report standardized results."""

    def __init__(
        self,
        *,
        tools: dict[str, ToolProtocol],
        logger: LoggerProtocol,
    ) -> None:
        self._tools = tools
        self._logger = logger

    def get_tool(self, tool_name: str) -> ToolProtocol | None:
        """Return tool instance by name, or None."""
        return self._tools.get(tool_name)

    async def execute(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {tool_name}"}

        try:
            self._logger.info("tool_execute", tool=tool_name, args_keys=list(tool_args.keys()))
            result = await tool.execute(**tool_args)
            if not isinstance(result, dict):
                result = {"success": True, "data": result}
            self._logger.info("tool_complete", tool=tool_name, success=result.get("success"))
            return result
        except Exception as error:
            self._logger.error("tool_exception", tool=tool_name, error=str(error))
            return {"success": False, "error": str(error)}


class ToolResultMessageFactory:
    """Build message history entries for tool results."""

    def __init__(
        self,
        *,
        tool_result_store: ToolResultStoreProtocol | None,
        result_store_threshold: int,
        logger: LoggerProtocol | structlog.stdlib.BoundLogger,
    ) -> None:
        self._tool_result_store = tool_result_store
        self._result_store_threshold = result_store_threshold
        self._logger = logger

    async def build_message(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        tool_result: dict[str, Any],
        session_id: str,
        step: int,
    ) -> dict[str, Any]:
        """
        Create a tool message for message history.

        If tool_result_store is available and the result is large, stores the
        full result to a file and returns a short message with the file path.
        The agent can use file_read to access the complete data.
        Otherwise, returns the result inline.
        """
        if not isinstance(tool_result, dict):
            tool_result = {"success": True, "data": tool_result}
        result_json = json.dumps(tool_result, ensure_ascii=False, default=str)
        result_size = len(result_json)

        # Never store file_read results — the agent explicitly asked for this content.
        # Storing it again would create an infinite loop (read file → too large → store
        # to new file → agent reads new file → too large → ...).
        is_read_tool = tool_name in ("file_read", "fetch_result")

        if self._tool_result_store and result_size > self._result_store_threshold and not is_read_tool:
            handle = await self._tool_result_store.put(
                tool_name=tool_name,
                result=tool_result,
                session_id=session_id,
                metadata={
                    "step": step,
                    "success": tool_result.get("success", False),
                },
            )

            # Return a simple file reference — agent uses file_read to get full data
            result_file = self._tool_result_store._result_path(handle.id)
            file_ref = {
                "success": tool_result.get("success", False),
                "result_file": str(result_file),
                "size_chars": result_size,
                "message": (
                    f"Result too large for inline response ({result_size} chars). "
                    f"Full data saved to: {result_file} — use file_read to access."
                ),
            }

            self._logger.info(
                "tool_result_stored_to_file",
                tool=tool_name,
                file=str(result_file),
                size_chars=result_size,
            )

            return tool_result_to_message(tool_call_id, tool_name, file_ref)

        return tool_result_to_message(tool_call_id, tool_name, tool_result)
