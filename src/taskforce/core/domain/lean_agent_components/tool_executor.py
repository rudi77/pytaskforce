"""Tool execution helpers for Agent."""

from __future__ import annotations

import json
from typing import Any

import structlog

from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.multimodal import (
    build_multimodal_content,
    has_image_attachments,
)
from taskforce.core.interfaces.logging import LoggerProtocol
from taskforce.core.interfaces.tool_result_store import ToolResultStoreProtocol
from taskforce.core.interfaces.tools import ToolProtocol
from taskforce.core.tools.tool_converter import (
    tool_result_to_message,
)

MAX_LOGGED_STRING_CHARS = 4000


def _truncate_for_log(value: Any, max_chars: int = MAX_LOGGED_STRING_CHARS) -> Any:
    """Return a log-safe copy of *value* with long strings truncated.

    Preserves dict/list structure so downstream log parsers keep field names
    and types; only string leaves are shortened.
    """
    if isinstance(value, str):
        if len(value) > max_chars:
            return value[:max_chars] + f"...[+{len(value) - max_chars} chars]"
        return value
    if isinstance(value, dict):
        return {k: _truncate_for_log(v, max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_truncate_for_log(v, max_chars) for v in value]
    return value


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

        logged_args = _truncate_for_log(tool_args)
        try:
            self._logger.info("tool_execute", tool=tool_name, args=logged_args)
            result = await tool.execute(**tool_args)
            if not isinstance(result, dict):
                result = {"success": True, "data": result}
            success = result.get("success")
            logged_result = _truncate_for_log(result)
            if success is False:
                self._logger.warning(
                    "tool_complete",
                    tool=tool_name,
                    success=False,
                    error=result.get("error"),
                    error_type=result.get("error_type"),
                    details=_truncate_for_log(result.get("details")),
                    result=logged_result,
                )
            else:
                self._logger.info(
                    "tool_complete",
                    tool=tool_name,
                    success=success,
                    result=logged_result,
                )
            return result
        except Exception as error:
            self._logger.error(
                "tool_exception",
                tool=tool_name,
                args=logged_args,
                error=str(error),
                error_type=type(error).__name__,
            )
            return {"success": False, "error": str(error)}


class ToolResultMessageFactory:
    """Build message history entries for tool results."""

    def __init__(
        self,
        *,
        tool_result_store: ToolResultStoreProtocol | None,
        result_store_threshold: int,
        logger: LoggerProtocol | structlog.stdlib.BoundLogger,
        tools: dict[str, ToolProtocol] | None = None,
    ) -> None:
        self._tool_result_store = tool_result_store
        self._result_store_threshold = result_store_threshold
        self._logger = logger
        self._tools = tools or {}

    def _threshold_for(self, tool_name: str) -> int:
        """Resolve the result-store threshold for ``tool_name``.

        Per-tool override wins: any tool exposing a non-None
        ``tool_result_store_threshold`` attribute (e.g. via ``BaseTool``)
        sets its own cap. Otherwise the framework default is used.
        """
        tool = self._tools.get(tool_name)
        if tool is not None:
            override = getattr(tool, "tool_result_store_threshold", None)
            if isinstance(override, int) and override >= 0:
                return override
        return self._result_store_threshold

    async def build_messages(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        tool_result: dict[str, Any],
        session_id: str,
        step: int,
    ) -> list[dict[str, Any]]:
        """Return the tool message plus any multimodal follow-ups.

        Tools that produce media (images today, audio/video later) signal
        this by returning an ``attachments`` list shaped like the gateway
        convention::

            {"type": "image", "data_url": "data:image/...;base64,...",
             "mime_type": "image/jpeg", "file_path": "/tmp/x.jpg"}

        For each call, this returns:

        1. The standard ``role="tool"`` message (with ``attachments``
           stripped from the payload so base64 never leaks into the text
           tool message).
        2. If any image attachments are present, a follow-up
           ``role="user"`` message whose ``content`` is OpenAI-shaped
           multimodal blocks built via
           :func:`taskforce.core.domain.multimodal.build_multimodal_content`.
           LiteLLM translates this to the right per-provider format
           (Anthropic ``image`` blocks, Gemini ``inlineData`` etc.).
        """
        attachments: list[dict[str, Any]] | None = None
        if isinstance(tool_result, dict):
            raw = tool_result.get("attachments")
            if isinstance(raw, list) and raw:
                attachments = raw
                tool_result = {k: v for k, v in tool_result.items() if k != "attachments"}

        tool_msg = await self.build_message(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_result=tool_result,
            session_id=session_id,
            step=step,
        )
        messages: list[dict[str, Any]] = [tool_msg]

        if has_image_attachments(attachments):
            count = len(attachments) if attachments else 0
            caption = f"[Tool '{tool_name}' returned {count} attachment(s).]"
            content = build_multimodal_content(caption, attachments)
            messages.append({"role": MessageRole.USER.value, "content": content})

        return messages

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

        NOTE: this returns only the ``role="tool"`` message. Callers that
        want media attachments (e.g. images) to actually reach a
        vision-capable LLM should use :meth:`build_messages` instead, which
        returns the tool message plus any multimodal follow-up user
        messages.
        """
        if not isinstance(tool_result, dict):
            tool_result = {"success": True, "data": tool_result}
        result_json = json.dumps(tool_result, ensure_ascii=False, default=str)
        result_size = len(result_json)

        # Never store file_read results — the agent explicitly asked for this content.
        # Storing it again would create an infinite loop (read file → too large → store
        # to new file → agent reads new file → too large → ...).
        is_read_tool = tool_name in ("file_read", "fetch_result")
        threshold = self._threshold_for(tool_name)

        if self._tool_result_store and result_size > threshold and not is_read_tool:
            handle = await self._tool_result_store.put(
                tool_name=tool_name,
                result=tool_result,
                session_id=session_id,
                metadata={
                    "step": step,
                    "success": tool_result.get("success", False),
                },
            )

            # Return an opaque handle. Internal cache paths may sit outside
            # the active workspace, so agents must use fetch_result instead
            # of file_read to retrieve full stored data.
            result_file = self._tool_result_store._result_path(handle.id)
            file_ref = {
                "success": tool_result.get("success", False),
                "truncated": True,
                "handle_id": handle.id,
                "size_chars": result_size,
                "message": (
                    "Result too large for inline response "
                    f"({result_size} chars). "
                    f"Use fetch_result with handle_id={handle.id!r} to access "
                    "the full result."
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
