"""Unit tests for ContextManager."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from taskforce.core.domain.lean_agent_components.context_manager import ContextManager
from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.core.interfaces.context_manager import ContextItem, ContextSnapshot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_logger() -> Mock:
    return Mock()


@pytest.fixture
def mock_token_budgeter(mock_logger: Mock) -> TokenBudgeter:
    return TokenBudgeter(logger=mock_logger, max_input_tokens=100_000)


@pytest.fixture
def mock_history_manager() -> Mock:
    """Mock MessageHistoryManager with key methods."""
    mhm = Mock(spec=MessageHistoryManager)
    mhm.build_initial_messages = Mock(
        return_value=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
    )
    mhm.compress_messages = AsyncMock(side_effect=lambda msgs: msgs)
    mhm.preflight_budget_check = Mock(side_effect=lambda msgs: msgs)
    return mhm


@pytest.fixture
def openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


@pytest.fixture
def ctx(
    mock_history_manager: Mock,
    openai_tools: list[dict[str, Any]],
    mock_token_budgeter: TokenBudgeter,
    mock_logger: Mock,
) -> ContextManager:
    return ContextManager(
        message_history_manager=mock_history_manager,
        openai_tools=openai_tools,
        token_budgeter=mock_token_budgeter,
        logger=mock_logger,
    )


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


def test_not_initialized_by_default(ctx: ContextManager) -> None:
    assert not ctx.is_initialized
    assert ctx.messages == []
    assert ctx.system_prompt == ""


@pytest.mark.spec("context-manager.system_prompt_always_at_index_zero")
def test_initialize_builds_messages(ctx: ContextManager) -> None:
    ctx.initialize(mission="Hello", state={}, base_system_prompt="You are helpful.")

    assert ctx.is_initialized
    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "system"
    assert ctx.messages[1]["role"] == "user"
    assert ctx.system_prompt == "You are helpful."


@pytest.mark.spec("context-manager.restore_recovers_full_message_list")
def test_restore_replaces_messages(ctx: ContextManager) -> None:
    restored = [
        {"role": "system", "content": "Restored prompt"},
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    ctx.restore(restored)

    assert ctx.is_initialized
    assert len(ctx.messages) == 3
    assert ctx.system_prompt == "Restored prompt"


@pytest.mark.spec("context-manager.restore_recovers_full_message_list")
def test_restore_handles_no_system_message(ctx: ContextManager) -> None:
    ctx.restore([{"role": "user", "content": "orphan"}])

    assert ctx.is_initialized
    assert ctx.system_prompt == ""


# ---------------------------------------------------------------------------
# Mutation tests
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager.system_prompt_always_at_index_zero")
def test_set_system_prompt_updates_first_message(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="old")

    ctx.set_system_prompt("new prompt")

    assert ctx.messages[0]["content"] == "new prompt"
    assert ctx.system_prompt == "new prompt"


@pytest.mark.spec("context-manager.system_prompt_always_at_index_zero")
def test_set_system_prompt_on_empty_messages(ctx: ContextManager) -> None:
    ctx.set_system_prompt("fresh prompt")

    assert len(ctx.messages) == 1
    assert ctx.messages[0] == {"role": "system", "content": "fresh prompt"}


def test_append_message(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")
    initial_count = len(ctx.messages)

    ctx.append_message({"role": "user", "content": "nudge"})

    assert len(ctx.messages) == initial_count + 1
    assert ctx.messages[-1]["content"] == "nudge"


@pytest.mark.spec("context-manager.compression_mutates_in_place")
def test_messages_property_returns_same_list_object(ctx: ContextManager) -> None:
    """External code holding a reference to messages must see mutations."""
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")

    ref = ctx.messages
    ctx.append_message({"role": "user", "content": "added"})

    assert ref is ctx.messages
    assert ref[-1]["content"] == "added"


# ---------------------------------------------------------------------------
# Compression tests
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager.compression_mutates_in_place")
async def test_compress_mutates_in_place(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")
    ref = ctx.messages

    await ctx.compress()

    assert ref is ctx.messages  # Same list object


@pytest.mark.spec("context-manager.compression_mutates_in_place")
async def test_compress_replaces_content_when_new_list_returned(
    ctx: ContextManager,
    mock_history_manager: Mock,
) -> None:
    """When compress_messages returns a NEW list, content must be swapped in-place."""
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")
    ref = ctx.messages

    compressed = [{"role": "system", "content": "compressed"}]
    mock_history_manager.compress_messages = AsyncMock(return_value=compressed)

    await ctx.compress()

    assert ref is ctx.messages  # Still the same list object
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["content"] == "compressed"


def test_preflight_check_mutates_in_place(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")
    ref = ctx.messages

    ctx.preflight_check()

    assert ref is ctx.messages


def test_preflight_check_replaces_content_when_new_list_returned(
    ctx: ContextManager,
    mock_history_manager: Mock,
) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")
    ref = ctx.messages

    truncated = [{"role": "system", "content": "truncated"}]
    mock_history_manager.preflight_budget_check = Mock(return_value=truncated)

    ctx.preflight_check()

    assert ref is ctx.messages
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["content"] == "truncated"


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


def test_snapshot_returns_context_snapshot(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="You are helpful.")

    snap = ctx.snapshot()

    assert isinstance(snap, ContextSnapshot)
    assert snap.max_tokens == 100_000
    assert snap.total_tokens > 0
    assert len(snap.system_prompt) == 1
    assert snap.system_prompt[0].title == "System prompt"
    assert len(snap.tools) == 1
    assert snap.tools[0].title == "file_read"


def test_snapshot_includes_content_when_requested(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="Be helpful.")

    snap = ctx.snapshot(include_content=True)

    assert snap.system_prompt[0].content is not None
    assert "Be helpful" in snap.system_prompt[0].content


def test_snapshot_excludes_content_by_default(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="Be helpful.")

    snap = ctx.snapshot(include_content=False)

    assert snap.system_prompt[0].content is None


def test_snapshot_includes_tool_call_messages(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")
    ctx.append_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "file_read", "arguments": "{}"},
                }
            ],
        }
    )
    ctx.append_message(
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "file_read",
            "content": '{"success": true}',
        }
    )

    snap = ctx.snapshot()

    # Find tool_call and tool_result items (skip system messages)
    msg_titles = [m.title for m in snap.messages]
    assert any("tool_call" in t for t in msg_titles)
    assert any("tool [file_read]" in t for t in msg_titles)


def test_snapshot_skips_system_message_in_messages_section(
    ctx: ContextManager,
) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")

    snap = ctx.snapshot()

    msg_titles = [m.title for m in snap.messages]
    assert not any("system" in t.lower() for t in msg_titles)


def test_snapshot_with_skill_manager(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")

    skill_mgr = Mock()
    skill_mgr.active_skill_name = "pdf-processing"
    skill_mgr.get_active_instructions = Mock(return_value="Process PDFs carefully.")
    skill_mgr.list_skills = Mock(return_value=["pdf-processing", "web-scraper"])
    skill_mgr.get_skill = Mock(return_value=Mock(description="Scrape web pages"))

    snap = ctx.snapshot(skill_manager=skill_mgr)

    assert len(snap.skills) == 2
    assert snap.skills[0].title == "Active skill: pdf-processing"
    assert snap.skills[1].title == "Loaded: web-scraper"


def test_snapshot_without_skill_manager(ctx: ContextManager) -> None:
    ctx.initialize(mission="test", state={}, base_system_prompt="sys")

    snap = ctx.snapshot(skill_manager=None)

    assert snap.skills == []


# ---------------------------------------------------------------------------
# Tools property
# ---------------------------------------------------------------------------


def test_tools_returns_openai_tools(
    ctx: ContextManager, openai_tools: list[dict[str, Any]],
) -> None:
    assert ctx.tools is openai_tools


# ---------------------------------------------------------------------------
# prepare_for_llm tests
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx_with_callback(
    mock_history_manager: Mock,
    openai_tools: list[dict[str, Any]],
    mock_token_budgeter: TokenBudgeter,
    mock_logger: Mock,
) -> ContextManager:
    """ContextManager with a build_system_prompt_fn callback."""
    return ContextManager(
        message_history_manager=mock_history_manager,
        openai_tools=openai_tools,
        token_budgeter=mock_token_budgeter,
        logger=mock_logger,
        build_system_prompt_fn=lambda **kwargs: "Dynamic system prompt",
    )


@pytest.mark.spec("context-manager.system_prompt_always_at_index_zero")
async def test_prepare_for_llm_rebuilds_system_prompt(
    ctx_with_callback: ContextManager,
) -> None:
    ctx_with_callback.initialize(
        mission="test", state={}, base_system_prompt="old",
    )

    await ctx_with_callback.prepare_for_llm(mission="test", state={})

    assert ctx_with_callback.system_prompt == "Dynamic system prompt"
    assert ctx_with_callback.messages[0]["content"] == "Dynamic system prompt"


async def test_prepare_for_llm_skips_rebuild_when_disabled(
    ctx_with_callback: ContextManager,
) -> None:
    ctx_with_callback.initialize(
        mission="test", state={}, base_system_prompt="original",
    )

    await ctx_with_callback.prepare_for_llm(
        rebuild_system_prompt=False, mission="test", state={},
    )

    assert ctx_with_callback.system_prompt == "original"


async def test_prepare_for_llm_runs_compression(
    ctx_with_callback: ContextManager,
    mock_history_manager: Mock,
) -> None:
    ctx_with_callback.initialize(
        mission="test", state={}, base_system_prompt="sys",
    )

    await ctx_with_callback.prepare_for_llm(mission="test", state={})

    mock_history_manager.compress_messages.assert_called_once()
    mock_history_manager.preflight_budget_check.assert_called_once()


async def test_prepare_for_llm_skips_compression_when_disabled(
    ctx_with_callback: ContextManager,
    mock_history_manager: Mock,
) -> None:
    ctx_with_callback.initialize(
        mission="test", state={}, base_system_prompt="sys",
    )

    await ctx_with_callback.prepare_for_llm(
        apply_compression=False, mission="test", state={},
    )

    mock_history_manager.compress_messages.assert_not_called()
    mock_history_manager.preflight_budget_check.assert_not_called()


async def test_prepare_for_llm_without_callback(ctx: ContextManager) -> None:
    """prepare_for_llm works even without a callback (no-op for prompt rebuild)."""
    ctx.initialize(mission="test", state={}, base_system_prompt="original")

    await ctx.prepare_for_llm(mission="test", state={})

    # System prompt unchanged (no callback)
    assert ctx.system_prompt == "original"


@pytest.mark.spec("context-manager.compression_mutates_in_place")
async def test_prepare_for_llm_preserves_message_identity(
    ctx_with_callback: ContextManager,
) -> None:
    """Messages list identity must be preserved through prepare_for_llm."""
    ctx_with_callback.initialize(
        mission="test", state={}, base_system_prompt="sys",
    )
    ref = ctx_with_callback.messages

    await ctx_with_callback.prepare_for_llm(mission="test", state={})

    assert ref is ctx_with_callback.messages


@pytest.mark.spec("context-manager.prepare_for_llm_before_init_is_noop_warning")
async def test_prepare_for_llm_on_uninitialized_context(
    ctx: ContextManager, mock_logger: Mock,
) -> None:
    """prepare_for_llm on uninitialized context should no-op with warning."""
    await ctx.prepare_for_llm(mission="test", state={})

    mock_logger.warning.assert_called_once_with(
        "prepare_for_llm_called_before_initialize",
    )
    assert ctx.messages == []


# ---------------------------------------------------------------------------
# Sub-agent snapshot registration
# ---------------------------------------------------------------------------


def _make_dummy_snapshot() -> ContextSnapshot:
    return ContextSnapshot(
        total_tokens=100,
        max_tokens=1000,
        utilization_percent=10.0,
        system_prompt=[ContextItem(title="sys", tokens=50)],
        messages=[ContextItem(title="1. user", tokens=50)],
    )


def test_register_sub_agent_context_stores_entry(ctx: ContextManager) -> None:
    snap = _make_dummy_snapshot()

    ctx.register_sub_agent_context(
        specialist="research", session_id="sess-1", snapshot=snap,
    )

    result = ctx.snapshot()
    assert len(result.sub_agents) == 1
    assert result.sub_agents[0].specialist == "research"
    assert result.sub_agents[0].snapshot is snap


@pytest.mark.spec("context-manager.sub_agent_snapshots_capped_at_ten")
def test_register_sub_agent_context_respects_max(ctx: ContextManager) -> None:
    snap = _make_dummy_snapshot()

    for i in range(ctx.MAX_SUB_AGENT_SNAPSHOTS + 5):
        ctx.register_sub_agent_context(
            specialist=f"agent-{i}", session_id=f"sess-{i}", snapshot=snap,
        )

    result = ctx.snapshot()
    assert len(result.sub_agents) == ctx.MAX_SUB_AGENT_SNAPSHOTS


@pytest.mark.spec("context-manager.sub_agent_snapshots_cleared_on_initialize")
def test_initialize_clears_sub_agent_entries(ctx: ContextManager) -> None:
    snap = _make_dummy_snapshot()
    ctx.register_sub_agent_context(
        specialist="old", session_id="sess-old", snapshot=snap,
    )

    ctx.initialize(mission="new", state={}, base_system_prompt="sys")

    result = ctx.snapshot()
    assert len(result.sub_agents) == 0


# ---------------------------------------------------------------------------
# Snapshot immutability
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager.snapshot_is_frozen_tree")
def test_snapshot_root_is_frozen(ctx: ContextManager) -> None:
    """The ContextSnapshot returned by snapshot() is a frozen dataclass."""
    ctx.initialize(mission="test", state={}, base_system_prompt="You are helpful.")

    snap = ctx.snapshot()

    with pytest.raises(FrozenInstanceError):
        snap.total_tokens = 0  # type: ignore[misc]


@pytest.mark.spec("context-manager.snapshot_is_frozen_tree")
def test_snapshot_nested_items_are_frozen(ctx: ContextManager) -> None:
    """Nested ContextItem / SubAgentContextEntry nodes are frozen too —
    mutating any part of the snapshot tree does not affect the live context."""
    ctx.initialize(mission="test", state={}, base_system_prompt="You are helpful.")
    ctx.register_sub_agent_context(
        specialist="research", session_id="sess-1", snapshot=_make_dummy_snapshot(),
    )

    snap = ctx.snapshot()

    with pytest.raises(FrozenInstanceError):
        snap.system_prompt[0].title = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snap.sub_agents[0].specialist = "mutated"  # type: ignore[misc]
