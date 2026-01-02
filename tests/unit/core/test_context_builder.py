"""
Unit tests for ContextBuilder (Story 9.2)

Tests the deterministic context pack building with budget enforcement.
"""

import json

import pytest

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy


class TestContextPolicy:
    """Test ContextPolicy model."""

    def test_default_policy(self):
        """Test default policy creation."""
        policy = ContextPolicy()
        assert policy.max_items == 10
        assert policy.max_chars_per_item == 500
        assert policy.max_total_chars == 3000
        assert policy.include_latest_tool_previews_n == 5

    def test_conservative_default(self):
        """Test conservative default policy."""
        policy = ContextPolicy.conservative_default()
        assert policy.max_items == 5
        assert policy.max_chars_per_item == 300
        assert policy.max_total_chars == 1500
        assert policy.include_latest_tool_previews_n == 3

    def test_policy_validation(self):
        """Test policy validation."""
        with pytest.raises(ValueError, match="max_items must be positive"):
            ContextPolicy(max_items=0)

        with pytest.raises(ValueError, match="max_chars_per_item must be positive"):
            ContextPolicy(max_chars_per_item=-1)

        with pytest.raises(ValueError, match="max_total_chars must be positive"):
            ContextPolicy(max_total_chars=0)

    def test_policy_auto_adjustment(self):
        """Test that max_total_chars is adjusted if unachievable."""
        policy = ContextPolicy(
            max_items=10, max_chars_per_item=100, max_total_chars=5000
        )
        # max_total_chars should be adjusted to 10 * 100 = 1000
        assert policy.max_total_chars == 1000

    def test_is_tool_allowed(self):
        """Test tool allowlist filtering."""
        # No allowlist = all allowed
        policy = ContextPolicy(allow_tools=None)
        assert policy.is_tool_allowed("any_tool")

        # With allowlist
        policy = ContextPolicy(allow_tools=["file_read", "python"])
        assert policy.is_tool_allowed("file_read")
        assert policy.is_tool_allowed("python")
        assert not policy.is_tool_allowed("web_search")

    def test_from_dict(self):
        """Test policy creation from dictionary."""
        data = {
            "max_items": 8,
            "max_chars_per_item": 400,
            "max_total_chars": 2000,
            "include_latest_tool_previews_n": 4,
            "allow_tools": ["file_read"],
            "allow_selectors": ["first_chars", "last_chars"],
        }
        policy = ContextPolicy.from_dict(data)
        assert policy.max_items == 8
        assert policy.max_chars_per_item == 400
        assert policy.allow_tools == ["file_read"]

    def test_to_dict(self):
        """Test policy serialization to dictionary."""
        policy = ContextPolicy(max_items=5, allow_tools=["python"])
        data = policy.to_dict()
        assert data["max_items"] == 5
        assert data["allow_tools"] == ["python"]


class TestContextBuilder:
    """Test ContextBuilder deterministic context pack construction."""

    def test_empty_context_pack(self):
        """Test building context pack with no data."""
        policy = ContextPolicy.conservative_default()
        builder = ContextBuilder(policy)

        pack = builder.build_context_pack()
        assert pack == ""

    def test_mission_only_context_pack(self):
        """Test context pack with only mission."""
        policy = ContextPolicy.conservative_default()
        builder = ContextBuilder(policy)

        mission = "Analyze the CSV file"
        pack = builder.build_context_pack(mission=mission)

        assert "CONTEXT PACK (BUDGETED)" in pack
        assert mission in pack

    def test_mission_too_long_excluded(self):
        """Test that overly long mission is excluded."""
        policy = ContextPolicy(max_chars_per_item=50)
        builder = ContextBuilder(policy)

        mission = "A" * 100  # Exceeds max_chars_per_item
        pack = builder.build_context_pack(mission=mission)

        # Mission should not be included
        assert mission not in pack

    def test_tool_preview_extraction(self):
        """Test extracting tool previews from message history."""
        policy = ContextPolicy.conservative_default()
        builder = ContextBuilder(policy)

        # Create message history with tool previews (Story 9.1 format)
        messages = [
            {"role": "user", "content": "Do something"},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps({
                    "handle": {
                        "id": "handle_1",
                        "tool": "file_read",
                        "size_chars": 1000,
                    },
                    "preview_text": "File contents preview...",
                    "truncated": True,
                }),
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": json.dumps({
                    "handle": {
                        "id": "handle_2",
                        "tool": "python",
                        "size_chars": 500,
                    },
                    "preview_text": "Result: 42",
                    "truncated": False,
                }),
            },
        ]

        pack = builder.build_context_pack(messages=messages)

        assert "CONTEXT PACK (BUDGETED)" in pack
        assert "Recent Tool Results" in pack
        assert "file_read" in pack
        assert "python" in pack
        assert "File contents preview..." in pack
        assert "Result: 42" in pack

    def test_respects_max_items(self):
        """Test that builder respects max_items limit."""
        policy = ContextPolicy(
            max_items=2, max_chars_per_item=500, max_total_chars=1000
        )
        builder = ContextBuilder(policy)

        # Create 5 tool previews
        messages = []
        for i in range(5):
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": json.dumps({
                    "handle": {
                        "id": f"handle_{i}",
                        "tool": f"tool_{i}",
                        "size_chars": 100,
                    },
                    "preview_text": f"Preview {i}",
                    "truncated": False,
                }),
            })

        pack = builder.build_context_pack(messages=messages)

        # Should only include 2 items (max_items=2)
        assert pack.count("tool_") == 2

    def test_respects_max_total_chars(self):
        """Test that builder respects max_total_chars budget."""
        policy = ContextPolicy(
            max_items=10,
            max_chars_per_item=500,
            max_total_chars=100,  # Very small budget
        )
        builder = ContextBuilder(policy)

        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps({
                    "handle": {
                        "id": "handle_1",
                        "tool": "file_read",
                        "size_chars": 1000,
                    },
                    "preview_text": "A" * 200,  # Large preview
                    "truncated": True,
                }),
            }
        ]

        pack = builder.build_context_pack(messages=messages)

        # Pack should be truncated or limited
        assert len(pack) <= policy.max_total_chars + 100  # Allow some header overhead

    def test_respects_max_chars_per_item(self):
        """Test that builder caps individual items."""
        policy = ContextPolicy(max_chars_per_item=50)
        builder = ContextBuilder(policy)

        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps({
                    "handle": {
                        "id": "handle_1",
                        "tool": "file_read",
                        "size_chars": 1000,
                    },
                    "preview_text": "A" * 200,  # Exceeds max_chars_per_item
                    "truncated": True,
                }),
            }
        ]

        pack = builder.build_context_pack(messages=messages)

        # Preview should be truncated to max_chars_per_item + "..." suffix
        # Count occurrences of 'A' in pack (allow for "..." suffix)
        a_count = pack.count("A")
        assert a_count <= policy.max_chars_per_item + 3  # Allow for "..." suffix

    def test_tool_allowlist_filtering(self):
        """Test that builder filters by tool allowlist."""
        policy = ContextPolicy(allow_tools=["file_read"])
        builder = ContextBuilder(policy)

        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps({
                    "handle": {
                        "id": "handle_1",
                        "tool": "file_read",
                        "size_chars": 100,
                    },
                    "preview_text": "Allowed tool",
                    "truncated": False,
                }),
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": json.dumps({
                    "handle": {
                        "id": "handle_2",
                        "tool": "web_search",
                        "size_chars": 100,
                    },
                    "preview_text": "Blocked tool",
                    "truncated": False,
                }),
            },
        ]

        pack = builder.build_context_pack(messages=messages)

        assert "file_read" in pack
        assert "Allowed tool" in pack
        assert "web_search" not in pack
        assert "Blocked tool" not in pack

    def test_latest_previews_first(self):
        """Test that latest previews are prioritized."""
        policy = ContextPolicy(include_latest_tool_previews_n=2)
        builder = ContextBuilder(policy)

        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps({
                    "handle": {"id": "h1", "tool": "tool_1", "size_chars": 100},
                    "preview_text": "Old preview",
                    "truncated": False,
                }),
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": json.dumps({
                    "handle": {"id": "h2", "tool": "tool_2", "size_chars": 100},
                    "preview_text": "Recent preview 1",
                    "truncated": False,
                }),
            },
            {
                "role": "tool",
                "tool_call_id": "call_3",
                "content": json.dumps({
                    "handle": {"id": "h3", "tool": "tool_3", "size_chars": 100},
                    "preview_text": "Recent preview 2",
                    "truncated": False,
                }),
            },
        ]

        pack = builder.build_context_pack(messages=messages)

        # Should include the 2 latest previews
        assert "Recent preview 1" in pack
        assert "Recent preview 2" in pack
        # Old preview might or might not be included depending on budget

    def test_deterministic_output(self):
        """Test that same inputs produce same output (determinism)."""
        policy = ContextPolicy.conservative_default()
        builder = ContextBuilder(policy)

        mission = "Test mission"
        messages = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": json.dumps({
                    "handle": {"id": "h1", "tool": "python", "size_chars": 100},
                    "preview_text": "Result: 42",
                    "truncated": False,
                }),
            }
        ]

        pack1 = builder.build_context_pack(mission=mission, messages=messages)
        pack2 = builder.build_context_pack(mission=mission, messages=messages)

        assert pack1 == pack2

    def test_apply_selector_first_chars(self):
        """Test first_chars selector."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        content = "A" * 1000
        result = builder.apply_selector(content, "first_chars", max_chars=100)

        assert len(result) == 100
        assert result == "A" * 100

    def test_apply_selector_last_chars(self):
        """Test last_chars selector."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        content = "A" * 500 + "B" * 500
        result = builder.apply_selector(content, "last_chars", max_chars=100)

        assert len(result) == 100
        assert result == "B" * 100

    def test_apply_selector_unknown_defaults_to_first(self):
        """Test unknown selector defaults to first_chars."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        content = "A" * 1000
        result = builder.apply_selector(content, "unknown_selector", max_chars=100)

        assert len(result) == 100
        assert result == "A" * 100

