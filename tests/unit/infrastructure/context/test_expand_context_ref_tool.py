"""Unit tests for the expand_context_ref page-fault tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from taskforce.infrastructure.context.expand_context_ref_tool import (
    ExpandContextRefTool,
)


def test_tool_metadata() -> None:
    tool = ExpandContextRefTool()
    assert tool.name == "expand_context_ref"
    assert tool.parameters_schema["required"] == ["segment_id"]
    assert tool.requires_approval is False


async def test_execute_without_bound_context_manager_fails_cleanly() -> None:
    tool = ExpandContextRefTool()
    result = await tool.execute(segment_id="seg-1")
    assert result["success"] is False
    assert "not bound" in result["error"]


async def test_execute_delegates_to_context_manager() -> None:
    tool = ExpandContextRefTool()
    context_manager = Mock()
    context_manager.expand_ref = AsyncMock(return_value={"success": True, "content": "expanded"})
    tool.set_context_manager_ref(context_manager)
    result = await tool.execute(segment_id="seg-7")
    context_manager.expand_ref.assert_awaited_once_with("seg-7")
    assert result == {"success": True, "content": "expanded"}
