"""
Unit tests for tool registry resolution helpers.
"""

from taskforce.infrastructure.tools.registry import (
    get_tool_definition,
    get_tool_definition_by_type,
    get_tool_name_for_type,
    resolve_tool_spec,
)


def test_get_tool_definition_returns_copy():
    """Definitions should be deep-copied to prevent shared mutations."""
    definition = get_tool_definition("web_search")
    assert definition is not None
    definition["params"]["extra"] = "value"

    fresh_definition = get_tool_definition("web_search")
    assert fresh_definition is not None
    assert "extra" not in fresh_definition["params"]


def test_get_tool_name_for_type():
    """Tool types should resolve to short names."""
    assert get_tool_name_for_type("WebSearchTool") == "web_search"
    assert get_tool_name_for_type("UnknownTool") is None


def test_get_tool_definition_by_type():
    """Tool types should resolve to full definitions."""
    definition = get_tool_definition_by_type("PythonTool")
    assert definition is not None
    assert definition["module"] == "taskforce.infrastructure.tools.native.python_tool"


def test_resolve_tool_spec_string():
    """String tool names should resolve to full definitions."""
    resolved = resolve_tool_spec("file_read")
    assert resolved is not None
    assert resolved["type"] == "FileReadTool"
    assert resolved["module"] == "taskforce.infrastructure.tools.native.file_tools"


def test_resolve_tool_spec_type_only_merges_defaults():
    """Type-only specs should inherit defaults and merge params."""
    resolved = resolve_tool_spec({"type": "LLMTool", "params": {"model_alias": "alt"}})
    assert resolved is not None
    assert resolved["module"] == "taskforce.infrastructure.tools.native.llm_tool"
    assert resolved["params"]["model_alias"] == "alt"


def test_resolve_tool_spec_module_override():
    """Module overrides should take precedence over registry defaults."""
    resolved = resolve_tool_spec(
        {
            "type": "PythonTool",
            "module": "taskforce.infrastructure.tools.native.python_tool",
            "params": {},
        }
    )
    assert resolved is not None
    assert resolved["module"] == "taskforce.infrastructure.tools.native.python_tool"


def test_resolve_tool_spec_invalid():
    """Invalid specs should return None."""
    assert resolve_tool_spec("unknown_tool") is None
    assert resolve_tool_spec({"module": "missing.type"}) is None
