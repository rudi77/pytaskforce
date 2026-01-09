"""Tool execution helpers for Agent."""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from taskforce.core.interfaces.tool_result_store import ToolResultStoreProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.tools.tool_converter import (
    create_tool_result_preview,
    tool_result_preview_to_message,
    tool_result_to_message,
)
from taskforce.infrastructure.tracing.file_tracer import get_file_tracer


class ToolExecutor:
    """Execute tools and report standardized results."""

    def __init__(
        self,
        *,
        tools: dict[str, ToolProtocol],
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self._tools = tools
        self._logger = logger

    async def execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str = "",
    ) -> dict[str, Any]:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {tool_name}"}

        # Get file tracer for logging (may be None)
        file_tracer = get_file_tracer()

        try:
            # Validate parameters before execution
            if hasattr(tool, "validate_params"):
                is_valid, error_msg = tool.validate_params(**tool_args)
                if not is_valid:
                    self._logger.warning(
                        "tool_validation_failed",
                        tool=tool_name,
                        error=error_msg,
                        args_keys=list(tool_args.keys()),
                    )
                    return {"success": False, "error": f"Parameter validation failed: {error_msg}"}

            self._logger.info("tool_execute", tool=tool_name, args_keys=list(tool_args.keys()))

            # Log tool call start to file tracer
            if file_tracer:
                file_tracer.log_tool_call(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    args=tool_args,
                )

            start_time = time.time()
            result = await tool.execute(**tool_args)
            latency_ms = int((time.time() - start_time) * 1000)

            self._logger.info("tool_complete", tool=tool_name, success=result.get("success"))

            # Log tool result to file tracer
            if file_tracer:
                result_preview = str(result.get("output", result.get("content", "")))[:500]
                file_tracer.log_tool_result(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    success=result.get("success", False),
                    result_preview=result_preview,
                    latency_ms=latency_ms,
                )

            return result
        except Exception as error:
            self._logger.error("tool_exception", tool=tool_name, error=str(error))

            # Log tool error to file tracer
            if file_tracer:
                file_tracer.log_tool_result(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    success=False,
                    error=str(error),
                )

            return {"success": False, "error": str(error)}


class ToolResultMessageFactory:
    """Build message history entries for tool results."""

    def __init__(
        self,
        *,
        tool_result_store: ToolResultStoreProtocol | None,
        result_store_threshold: int,
        logger: structlog.stdlib.BoundLogger,
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
        result and returns a handle+preview message. Otherwise, returns a
        standard message with the full result (truncated).
        """
        result_json = json.dumps(tool_result, ensure_ascii=False, default=str)
        result_size = len(result_json)

        if self._tool_result_store and result_size > self._result_store_threshold:
            handle = await self._tool_result_store.put(
                tool_name=tool_name,
                result=tool_result,
                session_id=session_id,
                metadata={
                    "step": step,
                    "success": tool_result.get("success", False),
                },
            )

            preview = create_tool_result_preview(handle, tool_result)

            self._logger.info(
                "tool_result_stored_with_handle",
                tool=tool_name,
                handle_id=handle.id,
                size_chars=result_size,
                preview_length=len(preview.preview_text),
            )

            return tool_result_preview_to_message(tool_call_id, tool_name, preview)

        return tool_result_to_message(tool_call_id, tool_name, tool_result)
