"""MCP tool wrapper — non-dict result hardening.

Spec: docs/spec/tools.md — an MCP tool result that is not a dict must be
converted into a standardised error payload so the agent never sees raw
non-dict output from a misbehaving MCP server.
"""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.infrastructure.tools.mcp.wrapper import MCPToolWrapper


class _NonDictClient:
    """Stand-in MCP client whose ``call_tool`` returns a non-dict value."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return "this is not a dict"  # a broken MCP server


@pytest.mark.spec("tools.mcp_non_dict_result_becomes_error_payload")
@pytest.mark.asyncio
async def test_mcp_non_dict_result_becomes_error_payload() -> None:
    """A non-dict MCP result is converted to a {success: False, ...} payload."""
    wrapper = MCPToolWrapper(
        client=_NonDictClient(),
        tool_definition={
            "name": "broken_mcp_tool",
            "description": "An MCP tool whose server misbehaves.",
            "input_schema": {"type": "object", "properties": {}},
        },
    )

    result = await wrapper.execute()

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result.get("error")
