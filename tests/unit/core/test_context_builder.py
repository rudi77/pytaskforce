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
        policy = ContextPolicy(max_items=10, max_chars_per_item=100, max_total_chars=5000)
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
                "content": json.dumps(
                    {
                        "handle": {
                            "id": "handle_1",
                            "tool": "file_read",
                            "size_chars": 1000,
                        },
                        "preview_text": "File contents preview...",
                        "truncated": True,
                    }
                ),
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": json.dumps(
                    {
                        "handle": {
                            "id": "handle_2",
                            "tool": "python",
                            "size_chars": 500,
                        },
                        "preview_text": "Result: 42",
                        "truncated": False,
                    }
                ),
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
        policy = ContextPolicy(max_items=2, max_chars_per_item=500, max_total_chars=1000)
        builder = ContextBuilder(policy)

        # Create 5 tool previews
        messages = []
        for i in range(5):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{i}",
                    "content": json.dumps(
                        {
                            "handle": {
                                "id": f"handle_{i}",
                                "tool": f"tool_{i}",
                                "size_chars": 100,
                            },
                            "preview_text": f"Preview {i}",
                            "truncated": False,
                        }
                    ),
                }
            )

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
                "content": json.dumps(
                    {
                        "handle": {
                            "id": "handle_1",
                            "tool": "file_read",
                            "size_chars": 1000,
                        },
                        "preview_text": "A" * 200,  # Large preview
                        "truncated": True,
                    }
                ),
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
                "content": json.dumps(
                    {
                        "handle": {
                            "id": "handle_1",
                            "tool": "file_read",
                            "size_chars": 1000,
                        },
                        "preview_text": "A" * 200,  # Exceeds max_chars_per_item
                        "truncated": True,
                    }
                ),
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
                "content": json.dumps(
                    {
                        "handle": {
                            "id": "handle_1",
                            "tool": "file_read",
                            "size_chars": 100,
                        },
                        "preview_text": "Allowed tool",
                        "truncated": False,
                    }
                ),
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": json.dumps(
                    {
                        "handle": {
                            "id": "handle_2",
                            "tool": "web_search",
                            "size_chars": 100,
                        },
                        "preview_text": "Blocked tool",
                        "truncated": False,
                    }
                ),
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
                "content": json.dumps(
                    {
                        "handle": {"id": "h1", "tool": "tool_1", "size_chars": 100},
                        "preview_text": "Old preview",
                        "truncated": False,
                    }
                ),
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": json.dumps(
                    {
                        "handle": {"id": "h2", "tool": "tool_2", "size_chars": 100},
                        "preview_text": "Recent preview 1",
                        "truncated": False,
                    }
                ),
            },
            {
                "role": "tool",
                "tool_call_id": "call_3",
                "content": json.dumps(
                    {
                        "handle": {"id": "h3", "tool": "tool_3", "size_chars": 100},
                        "preview_text": "Recent preview 2",
                        "truncated": False,
                    }
                ),
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
                "content": json.dumps(
                    {
                        "handle": {"id": "h1", "tool": "python", "size_chars": 100},
                        "preview_text": "Result: 42",
                        "truncated": False,
                    }
                ),
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


class TestContextPackDeduplication:
    """Test context pack deduplication of visible tool results."""

    def _make_tool_message(self, handle_id: str, tool: str, preview: str) -> dict:
        """Helper to create a tool message with preview data."""
        return {
            "role": "tool",
            "tool_call_id": f"call_{handle_id}",
            "content": json.dumps(
                {
                    "handle": {"id": handle_id, "tool": tool, "size_chars": 100},
                    "preview_text": preview,
                    "truncated": False,
                }
            ),
        }

    def test_visible_previews_are_skipped(self):
        """Tool previews in the visible window are deduplicated."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        messages = [
            self._make_tool_message("h1", "python", "Result: 42"),
            self._make_tool_message("h2", "file_read", "File contents"),
        ]

        # Without deduplication
        pack_all = builder.build_context_pack(messages=messages)
        assert "Result: 42" in pack_all
        assert "File contents" in pack_all

        # With deduplication (visible window covers all messages)
        pack_dedup = builder.build_context_pack(messages=messages, visible_window_size=10)
        assert "Result: 42" not in pack_dedup
        assert "File contents" not in pack_dedup

    def test_non_visible_previews_are_kept(self):
        """Tool previews outside the visible window are included."""
        policy = ContextPolicy(include_latest_tool_previews_n=5)
        builder = ContextBuilder(policy)

        # Create 15 messages: 5 old tool messages + 10 filler user messages
        messages = [
            self._make_tool_message(f"old_{i}", "python", f"Old result {i}") for i in range(5)
        ]
        for i in range(10):
            messages.append({"role": "user", "content": f"Message {i}"})

        # visible_window_size=5 means only the last 5 messages are visible
        # The old tool messages (positions 0-4) are outside the window
        pack = builder.build_context_pack(messages=messages, visible_window_size=5)

        # Old tool results should still be in the context pack
        assert "Old result" in pack

    def test_deduplication_disabled_with_none(self):
        """visible_window_size=None disables deduplication."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        messages = [
            self._make_tool_message("h1", "python", "Result: 42"),
        ]

        pack = builder.build_context_pack(messages=messages, visible_window_size=None)
        assert "Result: 42" in pack

    def test_deduplication_with_empty_messages(self):
        """Deduplication handles empty message list gracefully."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        pack = builder.build_context_pack(messages=[], visible_window_size=10)
        assert pack == ""

    def test_get_visible_tool_ids(self):
        """_get_visible_tool_ids extracts handle IDs from visible window."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        messages = [
            self._make_tool_message("h1", "python", "Result 1"),
            {"role": "user", "content": "Next question"},
            self._make_tool_message("h2", "file_read", "Result 2"),
        ]

        visible_ids = builder._get_visible_tool_ids(messages, visible_window_size=2)
        # Only the last 2 messages: user message + h2 tool message
        assert "h2" in visible_ids
        assert "h1" not in visible_ids

    def test_get_visible_tool_ids_handles_malformed_content(self):
        """_get_visible_tool_ids handles non-JSON tool content gracefully."""
        policy = ContextPolicy()
        builder = ContextBuilder(policy)

        messages = [
            {"role": "tool", "content": "not json"},
            {"role": "tool", "content": ""},
            {"role": "tool", "content": json.dumps({"no_handle": True})},
        ]

        visible_ids = builder._get_visible_tool_ids(messages, visible_window_size=10)
        assert len(visible_ids) == 0


class TestContextPolicyDeduplication:
    """Test ContextPolicy deduplicate_visible_window field."""

    def test_default_value(self):
        """Default deduplicate_visible_window is 10."""
        policy = ContextPolicy()
        assert policy.deduplicate_visible_window == 10

    def test_from_dict_with_dedup(self):
        """from_dict parses deduplicate_visible_window."""
        policy = ContextPolicy.from_dict({"deduplicate_visible_window": 20})
        assert policy.deduplicate_visible_window == 20

    def test_from_dict_default(self):
        """from_dict uses default when key is absent."""
        policy = ContextPolicy.from_dict({})
        assert policy.deduplicate_visible_window == 10

    def test_to_dict_includes_dedup(self):
        """to_dict includes deduplicate_visible_window."""
        policy = ContextPolicy(deduplicate_visible_window=5)
        data = policy.to_dict()
        assert data["deduplicate_visible_window"] == 5

    def test_roundtrip(self):
        """from_dict / to_dict roundtrip preserves the field."""
        original = ContextPolicy(deduplicate_visible_window=15)
        restored = ContextPolicy.from_dict(original.to_dict())
        assert restored.deduplicate_visible_window == 15

    def test_validation_negative(self):
        """Negative deduplicate_visible_window raises ValueError."""
        with pytest.raises(ValueError, match="deduplicate_visible_window"):
            ContextPolicy(deduplicate_visible_window=-1)

    def test_zero_disables(self):
        """Zero is valid (disables deduplication)."""
        policy = ContextPolicy(deduplicate_visible_window=0)
        assert policy.deduplicate_visible_window == 0
