"""Unit tests for LeanPromptBuilder with section-level caching."""

from __future__ import annotations

from unittest.mock import Mock

from taskforce.core.domain.context_builder import ContextBuilder
from taskforce.core.domain.context_policy import ContextPolicy
from taskforce.core.domain.lean_agent_components.prompt_builder import LeanPromptBuilder


def _make_builder(
    *,
    base_prompt: str = "Base system prompt.",
    planner: Mock | None = None,
    policy: ContextPolicy | None = None,
) -> LeanPromptBuilder:
    """Create a LeanPromptBuilder with sensible test defaults."""
    policy = policy or ContextPolicy.conservative_default()
    logger = Mock()
    return LeanPromptBuilder(
        base_system_prompt=base_prompt,
        planner=planner,
        context_builder=ContextBuilder(policy),
        context_policy=policy,
        logger=logger,
    )


class TestPlanSectionCaching:
    """Test plan section caching in LeanPromptBuilder."""

    def test_plan_section_cached_on_repeat_call(self):
        """Same plan content yields cached result without re-logging."""
        planner = Mock()
        planner.get_plan_summary.return_value = "Step 1: Do X\nStep 2: Do Y"

        builder = _make_builder(planner=planner)

        prompt1 = builder.build_system_prompt()
        prompt2 = builder.build_system_prompt()

        assert prompt1 == prompt2
        # get_plan_summary is called each time (to check for changes),
        # but the section string is reused from cache
        assert planner.get_plan_summary.call_count == 2

    def test_plan_section_invalidated_on_change(self):
        """Changed plan content invalidates the cache."""
        planner = Mock()
        planner.get_plan_summary.return_value = "Step 1: Do X"

        builder = _make_builder(planner=planner)
        prompt1 = builder.build_system_prompt()

        # Plan changes (e.g., step marked done)
        planner.get_plan_summary.return_value = "Step 1: Do X [DONE]\nStep 2: Do Y"
        prompt2 = builder.build_system_prompt()

        assert prompt1 != prompt2
        assert "DONE" in prompt2

    def test_no_planner_no_plan_section(self):
        """Without a planner, plan section is empty."""
        builder = _make_builder(planner=None)
        prompt = builder.build_system_prompt()
        assert "CURRENT PLAN STATUS" not in prompt

    def test_empty_plan_not_injected(self):
        """'No active plan.' is not injected."""
        planner = Mock()
        planner.get_plan_summary.return_value = "No active plan."

        builder = _make_builder(planner=planner)
        prompt = builder.build_system_prompt()
        assert "CURRENT PLAN STATUS" not in prompt


class TestContextPackSectionCaching:
    """Test context pack section caching in LeanPromptBuilder."""

    def test_context_section_cached_on_repeat_call(self):
        """Same messages yield cached context section."""
        builder = _make_builder()
        messages = [
            {"role": "user", "content": "test"},
        ]

        section1 = builder._build_context_pack_section(
            mission="Test", state=None, messages=messages
        )
        section2 = builder._build_context_pack_section(
            mission="Test", state=None, messages=messages
        )

        assert section1 == section2

    def test_context_section_invalidated_on_new_message(self):
        """Adding a message invalidates the context cache."""
        builder = _make_builder()
        messages: list[dict] = [
            {"role": "user", "content": "test"},
        ]

        builder._build_context_pack_section(mission="Test", state=None, messages=messages)
        key_before = builder._cached_context_key

        # Add a new message
        messages.append({"role": "tool", "content": '{"handle": {"id": "h1"}}'})

        builder._build_context_pack_section(mission="Test", state=None, messages=messages)
        key_after = builder._cached_context_key

        # Cache key should change because message count changed
        assert key_before != key_after


class TestDeduplicationWiring:
    """Test that deduplication is correctly wired through the builder."""

    def test_deduplication_disabled_when_zero(self):
        """deduplicate_visible_window=0 disables deduplication."""
        import json

        policy = ContextPolicy(deduplicate_visible_window=0)
        builder = _make_builder(policy=policy)

        messages = [
            {
                "role": "tool",
                "tool_call_id": "c1",
                "content": json.dumps(
                    {
                        "handle": {"id": "h1", "tool": "python", "size_chars": 100},
                        "preview_text": "Result: 42",
                        "truncated": False,
                    }
                ),
            },
        ]

        section = builder._build_context_pack_section(mission=None, state=None, messages=messages)
        assert "Result: 42" in section

    def test_deduplication_skips_visible_previews(self):
        """Previews in the visible window are skipped."""
        import json

        policy = ContextPolicy(deduplicate_visible_window=10)
        builder = _make_builder(policy=policy)

        # Single tool message — it's within the visible window of 10
        messages = [
            {
                "role": "tool",
                "tool_call_id": "c1",
                "content": json.dumps(
                    {
                        "handle": {"id": "h1", "tool": "python", "size_chars": 100},
                        "preview_text": "Result: 42",
                        "truncated": False,
                    }
                ),
            },
        ]

        section = builder._build_context_pack_section(mission=None, state=None, messages=messages)

        # The preview should be deduplicated (skipped) since the tool
        # message is within the visible window
        assert "Result: 42" not in section
