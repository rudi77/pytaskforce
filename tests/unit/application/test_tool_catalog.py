"""
Unit Tests for Tool Catalog Service
====================================

Tests the ToolCatalog service for tool validation and catalog generation.

Story: 8.2 - Tool Catalog + Allowlist Validation
"""

import pytest

from taskforce.application.tool_catalog import ToolCatalog, get_tool_catalog


def test_tool_catalog_singleton():
    """Test that get_tool_catalog returns singleton instance."""
    catalog1 = get_tool_catalog()
    catalog2 = get_tool_catalog()
    assert catalog1 is catalog2


def test_get_native_tools_returns_list():
    """Test get_native_tools returns list of tool definitions."""
    catalog = ToolCatalog()
    tools = catalog.get_native_tools()

    assert isinstance(tools, list)
    assert len(tools) > 0


def test_native_tool_structure():
    """Test that native tools have required fields."""
    catalog = ToolCatalog()
    tools = catalog.get_native_tools()

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "parameters_schema" in tool
        assert "requires_approval" in tool
        assert "approval_risk_level" in tool
        assert "origin" in tool
        assert tool["origin"] == "native"
        assert isinstance(tool["name"], str)
        assert isinstance(tool["description"], str)
        assert isinstance(tool["parameters_schema"], dict)
        assert isinstance(tool["requires_approval"], bool)


def test_get_native_tool_names_returns_set():
    """Test get_native_tool_names returns set of tool names."""
    catalog = ToolCatalog()
    tool_names = catalog.get_native_tool_names()

    assert isinstance(tool_names, set)
    assert len(tool_names) > 0
    assert all(isinstance(name, str) for name in tool_names)


def test_required_native_tools_present():
    """Test that all required native tools are present."""
    catalog = ToolCatalog()
    tool_names = catalog.get_native_tool_names()

    required_tools = {
        "web_search",
        "web_fetch",
        "file_read",
        "file_write",
        "python",
        "git",
        "github",
        "powershell",
        "ask_user",
    }

    assert required_tools.issubset(tool_names)


def test_validate_native_tools_valid():
    """Test validation with valid tool names."""
    catalog = ToolCatalog()
    is_valid, invalid_tools = catalog.validate_native_tools(
        ["web_search", "file_read", "python"]
    )

    assert is_valid is True
    assert invalid_tools == []


def test_validate_native_tools_invalid():
    """Test validation with invalid tool names."""
    catalog = ToolCatalog()
    is_valid, invalid_tools = catalog.validate_native_tools(
        ["web_search", "invalid_tool", "another_bad_tool"]
    )

    assert is_valid is False
    assert "invalid_tool" in invalid_tools
    assert "another_bad_tool" in invalid_tools
    assert "web_search" not in invalid_tools


def test_validate_native_tools_empty_list():
    """Test validation with empty tool list."""
    catalog = ToolCatalog()
    is_valid, invalid_tools = catalog.validate_native_tools([])

    assert is_valid is True
    assert invalid_tools == []


def test_validate_native_tools_all_invalid():
    """Test validation with all invalid tool names."""
    catalog = ToolCatalog()
    is_valid, invalid_tools = catalog.validate_native_tools(
        ["fake1", "fake2", "fake3"]
    )

    assert is_valid is False
    assert len(invalid_tools) == 3
    assert "fake1" in invalid_tools
    assert "fake2" in invalid_tools
    assert "fake3" in invalid_tools


def test_validate_native_tools_case_sensitive():
    """Test that tool name validation is case-sensitive."""
    catalog = ToolCatalog()
    is_valid, invalid_tools = catalog.validate_native_tools(
        ["Web_Search", "FILE_READ"]
    )

    assert is_valid is False
    assert "Web_Search" in invalid_tools
    assert "FILE_READ" in invalid_tools


def test_tool_catalog_deterministic():
    """Test that catalog returns consistent results."""
    catalog = ToolCatalog()
    tools1 = catalog.get_native_tools()
    tools2 = catalog.get_native_tools()

    assert len(tools1) == len(tools2)
    names1 = {tool["name"] for tool in tools1}
    names2 = {tool["name"] for tool in tools2}
    assert names1 == names2

