"""Integration tests against a live ctxman service.

Skipped unless ``CTXMAN_BASE_URL`` is set, e.g.::

    # terminal 1 (ctxman repo): dotnet run --project src/Ctxman.Api
    $env:CTXMAN_BASE_URL = "http://localhost:5291"
    pytest tests/integration/test_ctxman_integration.py -q
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.infrastructure.context.ctxman_client import (
    CtxmanClient,
    CtxmanUnavailableError,
)
from taskforce.infrastructure.context.ctxman_context_manager import (
    CtxmanContextManager,
)

CTXMAN_BASE_URL = os.environ.get("CTXMAN_BASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not CTXMAN_BASE_URL,
        reason="CTXMAN_BASE_URL not set (live ctxman service required)",
    ),
]


@pytest.fixture
def client() -> CtxmanClient:
    assert CTXMAN_BASE_URL is not None
    return CtxmanClient(base_url=CTXMAN_BASE_URL, timeout_seconds=15)


@pytest.fixture
def adapter(client: CtxmanClient) -> CtxmanContextManager:
    logger = Mock()
    history_manager = Mock()
    history_manager.build_initial_messages = Mock(
        return_value=[
            {"role": "system", "content": "You are a test agent."},
            {"role": "user", "content": "Integration test mission"},
        ]
    )
    history_manager.compress_messages = AsyncMock(side_effect=lambda msgs: msgs)
    history_manager.preflight_budget_check = Mock(side_effect=lambda msgs: msgs)
    return CtxmanContextManager(
        client=client,
        provider="openai",
        on_unavailable="fail",
        message_history_manager=history_manager,
        openai_tools=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        token_budgeter=TokenBudgeter(logger=logger, max_input_tokens=100_000),
        logger=logger,
    )


async def test_full_turn_roundtrip(
    adapter: CtxmanContextManager,
    client: CtxmanClient,
) -> None:
    """initialize → tool-call unit → prepare_for_llm → rendered context."""
    adapter.initialize("Integration test mission", {}, "You are a test agent.")
    adapter.append_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_int_1",
                    "function": {"name": "file_read", "arguments": "{}"},
                }
            ],
        }
    )
    adapter.append_message(
        {"role": "tool", "tool_call_id": "call_int_1", "content": "file contents"}
    )
    await adapter.prepare_for_llm(rebuild_system_prompt=False)

    assert adapter._session_id is not None
    assert adapter.messages[0]["role"] == "system"
    assert len(adapter.messages) > 1
    assert adapter._last_watermark in ("ok", "soft", "hard", "emergency")

    detail = await client.get_session(adapter._session_id)
    assert detail["session_id"] == adapter._session_id

    events = await client.get_events(adapter._session_id, after_seq=-1)
    event_types = {event["type"] for event in events}
    assert "segment_appended" in event_types

    # SSE stream serves the same snapshot with stable seq cursors.
    streamed = [event async for event in client.stream_events(adapter._session_id, after_seq=-1)]
    assert [event["seq"] for event in streamed] == [event["seq"] for event in events]

    # aclose archives the session (terminal promotion). A dev instance
    # without a compaction key 503s — then the session simply stays active.
    session_id = adapter._session_id
    await adapter.aclose()
    fresh_client = CtxmanClient(base_url=CTXMAN_BASE_URL, timeout_seconds=15)
    try:
        detail = await fresh_client.get_session(session_id)
        assert detail["status"] in ("active", "archived")
    finally:
        await fresh_client.aclose()


async def test_frame_roundtrip(adapter: CtxmanContextManager, client: CtxmanClient) -> None:
    """push_frame → segments in frame → pop_frame produces frame events."""
    adapter.initialize("Frame test mission", {}, "You are a test agent.")
    binding = await adapter.push_frame("integration_sub_agent")
    assert binding is not None

    # Key must be unique per run: ctxman replays identical idempotency
    # keys byte-identically for 24h, which would target the prior session.
    await client.append_segments(
        binding.session_id,
        [{"kind": "user_msg", "role": "user", "content": "frame-local message"}],
        idempotency_key=f"int-frame-seg-{binding.session_id}",
    )
    try:
        await adapter.pop_frame(binding, return_content="Sub-agent completed")
    except CtxmanUnavailableError as exc:
        if "promotion_failed" in str(exc):
            # Frame pop runs terminal promotion via the compaction LLM
            # (ctxman spec §3.3). A dev instance without
            # Compaction:*:api_key always 503s here — config issue of the
            # local ctxman stack, not of the integration.
            await adapter.aclose()
            pytest.skip(
                "ctxman has no compaction model configured " "(promotion_failed on frame pop)"
            )
        raise

    events = await client.get_events(binding.session_id, after_seq=-1)
    event_types = [event["type"] for event in events]
    assert "frame_pushed" in event_types
    assert "frame_popped" in event_types

    await adapter.aclose()


async def test_expand_ref_gone_semantics(adapter: CtxmanContextManager) -> None:
    """expand_ref on an unknown segment fails cleanly (404) without crash."""
    adapter.initialize("Ref test mission", {}, "You are a test agent.")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    result: dict[str, Any] = await adapter.expand_ref("01nonexistentsegmentid000000")
    # Unknown segment → 404 → clean error dict (410 path returns success+summary).
    assert "success" in result
    await adapter.aclose()
