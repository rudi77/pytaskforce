"""Tool for retrieving full stored tool results by handle ID.

When tool results are large (>1500 chars), they are stored and the agent
receives only a preview. This tool lets the agent fetch the complete result
when the preview is not sufficient (e.g., truncated email lists, long
file contents, search results).

Example flow:
1. Agent calls gmail(action=list, max_results=20) → gets preview of first 2000 chars
2. Agent sees "truncated: true" in the preview
3. Agent calls fetch_result(handle_id="abc123") → gets full result
"""

from __future__ import annotations

from typing import Any

from taskforce.infrastructure.tools.base_tool import BaseTool


class FetchResultTool(BaseTool):
    """Retrieve the full content of a previously stored tool result."""

    tool_name = "fetch_result"
    tool_description = (
        "Retrieve the full content of a truncated tool result. "
        "When a tool result was too large and shows 'truncated: true' with a handle ID, "
        "use this tool to get the complete data."
    )
    tool_parameters_schema = {
        "type": "object",
        "properties": {
            "handle_id": {
                "type": "string",
                "description": "The handle ID from a truncated tool result (found in the 'handle.id' field)",
            },
        },
        "required": ["handle_id"],
    }

    def __init__(self, tool_result_store: Any = None) -> None:
        self._store = tool_result_store

    async def _execute(self, **params: Any) -> dict[str, Any]:
        handle_id = params["handle_id"]

        if not self._store:
            return {"success": False, "error": "Tool result store not available"}

        from taskforce.core.domain.tool_result import ToolResultHandle

        handle = ToolResultHandle(
            id=handle_id,
            tool_name="unknown",
            session_id="",
        )

        result = await self._store.fetch(handle)

        if result is None:
            return {
                "success": False,
                "error": f"No stored result found for handle '{handle_id}'",
            }

        return result
