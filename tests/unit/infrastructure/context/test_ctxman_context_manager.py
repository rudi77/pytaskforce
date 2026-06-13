"""Unit tests for CtxmanContextManager against a fake ctxman client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from taskforce.core.domain.lean_agent_components.message_history_manager import (
    MessageHistoryManager,
)
from taskforce.core.domain.token_budgeter import TokenBudgeter
from taskforce.infrastructure.context.ctxman_client import (
    CtxmanBudgetExceededError,
    CtxmanGoneError,
    CtxmanIncompleteUnitError,
    CtxmanUnavailableError,
    RenderResult,
)
from taskforce.infrastructure.context.ctxman_context_manager import (
    CtxmanConfig,
    CtxmanContextManager,
    build_ctxman_context_manager_factory,
)
from taskforce.infrastructure.context.frame_binding import (
    FrameBinding,
    reset_frame_binding,
    set_frame_binding,
)


class FakeCtxmanClient:
    """Records calls and returns canned ctxman responses."""

    def __init__(self) -> None:
        self.created_sessions: list[dict[str, Any]] = []
        self.appended: list[tuple[str, list[dict[str, Any]], str]] = []
        self.renders: list[dict[str, Any]] = []
        self.static_replacements: list[list[dict[str, Any]]] = []
        self.gc_calls: list[str] = []
        self.pushed_frames: list[str] = []
        self.popped_frames: list[tuple[str, str]] = []
        self.archived: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.closed = False
        self.render_messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hello"},
        ]
        self.watermark_state = "ok"

    async def create_session(self, **kwargs: Any) -> tuple[str, int]:
        self.created_sessions.append(kwargs)
        return f"sess-{len(self.created_sessions)}", 0

    async def append_segments(
        self,
        session_id: str,
        segments: list[dict[str, Any]],
        *,
        idempotency_key: str,
        if_match: int | None = None,
    ) -> tuple[list[str], int]:
        self.appended.append((session_id, segments, idempotency_key))
        return [f"seg-{i}" for i in range(len(segments))], len(self.appended)

    async def render(self, session_id: str, **kwargs: Any) -> RenderResult:
        self.renders.append({"session_id": session_id, **kwargs})
        return RenderResult(
            messages=list(self.render_messages),
            system="static base",
            tools=[],
            builtin_tools=[{"name": "expand_context_ref"}],
            context_version=len(self.renders),
            tokens_total=4321,
            watermark_state=self.watermark_state,
        )

    async def replace_static_segments(
        self,
        session_id: str,
        segments: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.static_replacements.append(segments)
        return {"static_epoch": 1, "context_version": 99}

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "context_version": 50}

    async def get_ref(self, session_id: str, segment_id: str) -> dict[str, Any]:
        return {"content": f"full content of {segment_id}"}

    async def gc(self, session_id: str, *, level: str = "minor") -> str:
        self.gc_calls.append(level)
        return "job-1"

    async def upload_blob(self, session_id: str, content: bytes, **kwargs: Any) -> dict:
        return {"store": "fs", "key": "sha256:x", "size_bytes": len(content)}

    async def push_frame(self, session_id: str, label: str, **kwargs: Any) -> str:
        self.pushed_frames.append(label)
        return f"frame-{len(self.pushed_frames)}"

    async def pop_frame(
        self,
        session_id: str,
        frame_id: str,
        *,
        return_content: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.popped_frames.append((frame_id, return_content))
        return {"return_segment_id": "seg-r", "context_version": 1}

    async def archive_session(self, session_id: str, *, idempotency_key: str) -> None:
        self.archived.append(session_id)

    async def get_events(
        self,
        session_id: str,
        *,
        after_seq: int = -1,
    ) -> list[dict[str, Any]]:
        return [event for event in self.events if event.get("seq", 0) > after_seq]

    async def stream_events(self, session_id: str, *, after_seq: int = -1):
        for event in self.events:
            if event.get("seq", 0) > after_seq:
                yield event

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def mock_logger() -> Mock:
    return Mock()


@pytest.fixture
def mock_history_manager() -> Mock:
    mhm = Mock(spec=MessageHistoryManager)
    mhm.build_initial_messages = Mock(
        return_value=[
            {"role": "system", "content": "base prompt"},
            {"role": "user", "content": "the mission"},
        ]
    )
    mhm.compress_messages = AsyncMock(side_effect=lambda msgs: msgs)
    mhm.preflight_budget_check = Mock(side_effect=lambda msgs: msgs)
    return mhm


@pytest.fixture
def fake_client() -> FakeCtxmanClient:
    return FakeCtxmanClient()


def _make_adapter(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
    **overrides: Any,
) -> CtxmanContextManager:
    kwargs: dict[str, Any] = {
        "client": fake_client,
        "provider": "openai",
        "message_history_manager": mock_history_manager,
        "openai_tools": [
            {"type": "function", "function": {"name": "file_read", "parameters": {}}},
        ],
        "token_budgeter": TokenBudgeter(logger=mock_logger, max_input_tokens=100_000),
        "logger": mock_logger,
    }
    kwargs.update(overrides)
    return CtxmanContextManager(**kwargs)


@pytest.fixture
def adapter(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> CtxmanContextManager:
    return _make_adapter(fake_client, mock_history_manager, mock_logger)


# ---------------------------------------------------------------------------
# Protocol parity / list identity
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.messages_list_identity_stable")
async def test_messages_list_identity_stable_across_sync(
    adapter: CtxmanContextManager,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    messages_ref = adapter.messages
    adapter.append_message({"role": "assistant", "content": "thinking"})
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert adapter.messages is messages_ref
    assert messages_ref[0]["role"] == "system"


@pytest.mark.spec("context-manager-ctxman.system_prompt_overlaid_locally")
async def test_render_result_overlaid_with_local_system_prompt(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    adapter._build_system_prompt_fn = lambda **_: "dynamic full prompt"
    await adapter.prepare_for_llm(rebuild_system_prompt=True)
    # System prompt is the locally built one, NOT the render's static base.
    assert adapter.messages[0] == {"role": "system", "content": "dynamic full prompt"}
    assert adapter.messages[1:] == fake_client.render_messages
    assert adapter.system_prompt == "dynamic full prompt"


@pytest.mark.spec("context-manager-ctxman.prepare_before_initialize_is_noop")
async def test_prepare_for_llm_before_initialize_is_noop(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
    mock_logger: Mock,
) -> None:
    await adapter.prepare_for_llm()
    assert not fake_client.created_sessions
    mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# Session lifecycle / flush
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.lazy_session_with_static_region")
async def test_first_prepare_creates_session_with_static_region(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.created_sessions) == 1
    static = fake_client.created_sessions[0]["static_segments"]
    assert static[0]["kind"] == "system_prompt"
    assert static[0]["content"] == "base prompt"
    assert any(segment["kind"] == "tool_def" for segment in static)
    # Headroom for the locally overlaid dynamic prompt is reserved.
    overrides = fake_client.created_sessions[0]["policy_overrides"]
    assert overrides["budget_tokens"] == 100_000 - 4096


@pytest.mark.spec("context-manager-ctxman.outbox_flushed_as_single_batch")
async def test_outbox_flushed_once_as_single_batch(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    adapter.append_message({"role": "assistant", "content": "step"})
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.appended) == 1
    _, segments, _ = fake_client.appended[0]
    # Staged history (mission user msg) + appended assistant msg, no system.
    assert [segment["kind"] for segment in segments] == ["user_msg", "assistant_msg"]
    # Second prepare without new messages → no further append.
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.appended) == 1


@pytest.mark.spec("context-manager-ctxman.failed_flush_replays_same_key")
async def test_failed_flush_retries_with_same_idempotency_key(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    keys: list[str] = []
    original_append = fake_client.append_segments
    fail_next = {"value": True}

    async def flaky_append(session_id, segments, *, idempotency_key, if_match=None):
        keys.append(idempotency_key)
        if fail_next["value"]:
            fail_next["value"] = False
            raise CtxmanUnavailableError("down")
        return await original_append(
            session_id,
            segments,
            idempotency_key=idempotency_key,
            if_match=if_match,
        )

    fake_client.append_segments = flaky_append  # type: ignore[method-assign]
    await adapter.prepare_for_llm(rebuild_system_prompt=False)  # degrades
    await adapter.prepare_for_llm(rebuild_system_prompt=False)  # retries flush
    assert len(keys) == 2
    assert keys[0] == keys[1]


@pytest.mark.spec("context-manager-ctxman.restore_creates_fresh_session")
async def test_restore_creates_fresh_session_and_bulk_appends(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.created_sessions) == 1

    adapter.restore(
        [
            {"role": "system", "content": "restored prompt"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
        ]
    )
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.created_sessions) == 2
    _, segments, _ = fake_client.appended[-1]
    assert [segment["kind"] for segment in segments] == ["user_msg", "assistant_msg"]


# ---------------------------------------------------------------------------
# Conversation-scoped session reuse (#457)
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.fresh_session_persists_record_into_state")
async def test_fresh_session_persists_record_into_state(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    """First turn creates a session and writes its id + flush cursor into the
    conversation state dict so the next turn can reuse it (#457)."""
    state: dict[str, Any] = {}
    adapter = _make_adapter(fake_client, mock_history_manager, mock_logger)
    adapter.initialize("the mission", state, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.created_sessions) == 1
    record = state["_ctxman_session"]
    assert record["session_id"] == adapter._session_id
    assert record["flush_seq"] >= 1


@pytest.mark.spec("context-manager-ctxman.resume_attaches_without_recreating_session")
async def test_resume_attaches_without_recreating_session(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    """A turn whose state already carries a ctxman session attaches to it —
    no new session is created, and the render targets the saved id (#457)."""
    state: dict[str, Any] = {"_ctxman_session": {"session_id": "sess-existing", "flush_seq": 5}}
    adapter = _make_adapter(fake_client, mock_history_manager, mock_logger)
    adapter.initialize("the mission", state, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert fake_client.created_sessions == []
    assert adapter._session_id == "sess-existing"
    assert fake_client.renders[-1]["session_id"] == "sess-existing"


def _history_mock(messages: list[dict[str, Any]]) -> Mock:
    history = Mock(spec=MessageHistoryManager)
    history.build_initial_messages = Mock(return_value=messages)
    history.compress_messages = AsyncMock(side_effect=lambda m: m)
    history.preflight_budget_check = Mock(side_effect=lambda m: m)
    return history


@pytest.mark.spec("context-manager-ctxman.resume_stages_only_the_new_user_turn")
async def test_resume_stages_only_the_new_user_turn(
    fake_client: FakeCtxmanClient,
    mock_logger: Mock,
) -> None:
    """On resume only the new user turn is staged — the prior turns already
    live in the ctxman session (every turn flushes its final answer on close,
    #463). Re-staging the full history would collide on the per-turn append
    idempotency key or duplicate (ctxman dedups per batch key, not per
    segment). The append key continues the saved flush sequence (#457)."""
    history = _history_mock(
        [
            {"role": "system", "content": "base"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2 the new turn"},
        ]
    )
    state: dict[str, Any] = {"_ctxman_session": {"session_id": "sess-existing", "flush_seq": 2}}
    adapter = _make_adapter(fake_client, history, mock_logger)
    adapter.initialize("u2 the new turn", state, "base")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    _, segments, key = fake_client.appended[-1]
    assert [s["kind"] for s in segments] == ["user_msg"]
    assert segments[0]["content"] == "u2 the new turn"
    assert key == "sess-existing:2"


@pytest.mark.spec("context-manager-ctxman.final_answer_flushed_at_turn_end")
async def test_flush_sends_pending_final_answer(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    """flush() pushes the pending outbox (the final assistant answer) to the
    session synchronously at turn end, so it doesn't depend on the deferred
    close — which can hang behind post-mission work or be cancelled by the
    next turn (#465)."""
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    appended_before = len(fake_client.appended)
    adapter.append_message({"role": "assistant", "content": "Final reply"})
    await adapter.flush()
    assert len(fake_client.appended) == appended_before + 1
    _, segments, _ = fake_client.appended[-1]
    assert any(
        s.get("kind") == "assistant_msg" and s.get("content") == "Final reply" for s in segments
    )
    # Idempotent: a second flush with nothing pending is a no-op.
    await adapter.flush()
    assert len(fake_client.appended) == appended_before + 1


@pytest.mark.spec("context-manager-ctxman.final_answer_flushed_on_close")
async def test_aclose_flushes_final_assistant_answer(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    """Regression (#463): the final assistant answer has no subsequent
    prepare_for_llm to flush it, so without an explicit flush on close it never
    reaches the session — the render then shows the user turns with no
    assistant reply. aclose must flush the pending outbox before archiving."""
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    appended_before = len(fake_client.appended)
    adapter.append_message({"role": "assistant", "content": "Final reply"})
    await adapter.aclose()
    assert len(fake_client.appended) == appended_before + 1
    _, segments, _ = fake_client.appended[-1]
    assert any(
        s.get("kind") == "assistant_msg" and s.get("content") == "Final reply" for s in segments
    )


async def test_flush_cursor_persisted_and_advances(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    """The flush cursor is persisted and advances so a later turn's append
    key never reuses an earlier turn's (#457)."""
    state: dict[str, Any] = {}
    adapter = _make_adapter(fake_client, mock_history_manager, mock_logger)
    adapter.initialize("the mission", state, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    first = state["_ctxman_session"]["flush_seq"]
    adapter.append_message({"role": "assistant", "content": "more"})
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert state["_ctxman_session"]["flush_seq"] > first


@pytest.mark.spec("context-manager-ctxman.gone_session_recreated_with_full_history")
async def test_gone_session_is_recreated_with_full_history(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    """If the saved session has expired (410 Gone), drop it, create a fresh
    one, and recover (#457)."""
    state: dict[str, Any] = {"_ctxman_session": {"session_id": "sess-gone", "flush_seq": 9}}
    adapter = _make_adapter(fake_client, mock_history_manager, mock_logger)
    adapter.initialize("the mission", state, "base prompt")

    original_render = fake_client.render
    fail_next = {"value": True}

    async def gone_then_ok(session_id: str, **kwargs: Any) -> RenderResult:
        if fail_next["value"] and session_id == "sess-gone":
            fail_next["value"] = False
            raise CtxmanGoneError("session gone")
        return await original_render(session_id, **kwargs)

    fake_client.render = gone_then_ok  # type: ignore[method-assign]
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.created_sessions) == 1
    assert adapter._session_id != "sess-gone"
    assert state["_ctxman_session"]["session_id"] == adapter._session_id


# ---------------------------------------------------------------------------
# Budget machinery is server-side
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.compress_and_preflight_are_noops")
async def test_compress_and_preflight_are_noops(
    adapter: CtxmanContextManager,
    mock_history_manager: Mock,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.compress()
    adapter.preflight_check()
    mock_history_manager.compress_messages.assert_not_awaited()
    mock_history_manager.preflight_budget_check.assert_not_called()


@pytest.mark.spec("context-manager-ctxman.budget_413_triggers_gc_and_retry")
async def test_budget_exceeded_render_triggers_gc_and_retry(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "taskforce.infrastructure.context.ctxman_context_manager.asyncio.sleep",
        AsyncMock(),
    )
    adapter.initialize("the mission", {}, "base prompt")
    original_render = fake_client.render
    fail_next = {"value": True}

    async def flaky_render(session_id: str, **kwargs: Any) -> RenderResult:
        if fail_next["value"]:
            fail_next["value"] = False
            raise CtxmanBudgetExceededError("budget")
        return await original_render(session_id, **kwargs)

    fake_client.render = flaky_render  # type: ignore[method-assign]
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert fake_client.gc_calls == ["major"]
    assert adapter.messages[1:] == fake_client.render_messages


async def test_hard_watermark_triggers_gc(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    fake_client.watermark_state = "hard"
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert "major" in fake_client.gc_calls


# ---------------------------------------------------------------------------
# Failure modes (on_unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.degrade_keeps_local_context")
async def test_degrade_mode_keeps_local_messages_on_outage(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    adapter = _make_adapter(
        fake_client,
        mock_history_manager,
        mock_logger,
        on_unavailable="degrade",
    )
    fake_client.create_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=CtxmanUnavailableError("down")
    )
    adapter.initialize("the mission", {}, "base prompt")
    adapter._build_system_prompt_fn = lambda **_: "dynamic prompt"
    await adapter.prepare_for_llm()  # must not raise
    assert adapter.messages[0]["content"] == "dynamic prompt"
    assert adapter.messages[1] == {"role": "user", "content": "the mission"}


@pytest.mark.spec("context-manager-ctxman.fail_mode_propagates_outage")
async def test_fail_mode_raises_on_outage(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    adapter = _make_adapter(
        fake_client,
        mock_history_manager,
        mock_logger,
        on_unavailable="fail",
    )
    fake_client.create_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=CtxmanUnavailableError("down")
    )
    adapter.initialize("the mission", {}, "base prompt")
    with pytest.raises(CtxmanUnavailableError):
        await adapter.prepare_for_llm()


@pytest.mark.spec("context-manager-ctxman.open_units_repaired_with_synthetic_results")
async def test_incomplete_unit_repaired_with_synthetic_tool_results(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    adapter.append_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_X", "function": {"name": "t", "arguments": "{}"}},
            ],
        }
    )
    original_append = fake_client.append_segments
    fail_next = {"value": True}

    async def strict_append(session_id, segments, *, idempotency_key, if_match=None):
        if fail_next["value"]:
            fail_next["value"] = False
            raise CtxmanIncompleteUnitError("open", open_tool_call_ids=["call_X"])
        return await original_append(
            session_id,
            segments,
            idempotency_key=idempotency_key,
            if_match=if_match,
        )

    fake_client.append_segments = strict_append  # type: ignore[method-assign]
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    _, segments, _ = fake_client.appended[-1]
    synthetic = [s for s in segments if s.get("content") == "[tool call cancelled]"]
    assert len(synthetic) == 1
    assert synthetic[0]["tool_call_id"] == "call_X"


# ---------------------------------------------------------------------------
# Static region updates
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.static_put_only_on_base_prompt_change")
async def test_static_region_replaced_only_on_base_prompt_change(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert fake_client.static_replacements == []

    adapter._base_system_prompt = "changed base prompt"
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    assert len(fake_client.static_replacements) == 1
    assert fake_client.static_replacements[0][0]["content"] == "changed base prompt"


# ---------------------------------------------------------------------------
# Page faults
# ---------------------------------------------------------------------------


async def test_expand_ref_returns_content(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    result = await adapter.expand_ref("seg-42")
    assert result == {"success": True, "content": "full content of seg-42"}


@pytest.mark.spec("context-manager-ctxman.expand_ref_410_returns_summary")
async def test_expand_ref_gone_returns_summary(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    fake_client.get_ref = AsyncMock(  # type: ignore[method-assign]
        side_effect=CtxmanGoneError("gone", summary="old log file", origin="skill://x")
    )
    result = await adapter.expand_ref("seg-42")
    assert result["success"] is True
    assert result["evicted"] is True
    assert "old log file" in result["content"]
    assert "skill://x" in result["content"]


async def test_expand_ref_without_session_fails_cleanly(
    adapter: CtxmanContextManager,
) -> None:
    result = await adapter.expand_ref("seg-1")
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.push_frame_flushes_outbox_first")
async def test_push_frame_flushes_outbox_before_push(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    binding = await adapter.push_frame("research")
    assert binding is not None
    assert binding.frame_id == "frame-1"
    # Outbox (staged mission message) flushed before the frame push.
    assert len(fake_client.appended) == 1
    assert fake_client.pushed_frames == ["research"]

    await adapter.pop_frame(binding, return_content="done")
    assert fake_client.popped_frames == [("frame-1", "done")]


@pytest.mark.spec("context-manager-ctxman.frame_bound_adapter_shares_session")
async def test_frame_bound_adapter_uses_parent_session_and_frame_scope(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    binding = FrameBinding(client=fake_client, session_id="parent-sess", frame_id="f1")
    adapter = _make_adapter(
        fake_client,
        mock_history_manager,
        mock_logger,
        frame_binding=binding,
        owns_client=False,
    )
    adapter.initialize("sub mission", {}, "sub base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    # No own session created; renders against the parent session in frame scope.
    assert fake_client.created_sessions == []
    assert fake_client.renders[-1]["session_id"] == "parent-sess"
    assert fake_client.renders[-1]["scope"] == "frame"
    assert adapter.frames_supported is False
    # Shared client is not closed by the frame-bound adapter.
    await adapter.aclose()
    assert fake_client.closed is False


async def test_owning_adapter_closes_client(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    await adapter.aclose()
    assert fake_client.closed is True
    # No session was ever created — nothing to archive.
    assert fake_client.archived == []


# ---------------------------------------------------------------------------
# Archive on close
# ---------------------------------------------------------------------------


@pytest.mark.spec("context-manager-ctxman.session_archived_on_close")
async def test_aclose_archives_active_session(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    await adapter.aclose()
    assert fake_client.archived == [adapter._session_id]
    assert fake_client.closed is True


async def test_aclose_skips_archive_when_disabled(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    adapter = _make_adapter(
        fake_client,
        mock_history_manager,
        mock_logger,
        archive_on_close=False,
    )
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    await adapter.aclose()
    assert fake_client.archived == []
    assert fake_client.closed is True


@pytest.mark.spec("context-manager-ctxman.archive_failure_does_not_break_shutdown")
async def test_aclose_survives_archive_failure(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
    mock_logger: Mock,
) -> None:
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    fake_client.archive_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=CtxmanUnavailableError("promotion_failed")
    )
    await adapter.aclose()  # must not raise
    assert fake_client.closed is True
    assert any(
        call.args and call.args[0] == "ctxman_archive_failed"
        for call in mock_logger.warning.call_args_list
    )


async def test_frame_bound_adapter_never_archives(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    binding = FrameBinding(client=fake_client, session_id="parent-sess", frame_id="f1")
    adapter = _make_adapter(
        fake_client,
        mock_history_manager,
        mock_logger,
        frame_binding=binding,
        owns_client=False,
    )
    adapter.initialize("sub mission", {}, "sub base prompt")
    await adapter.aclose()
    assert fake_client.archived == []
    assert fake_client.closed is False


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def test_get_events_without_session_returns_empty(
    adapter: CtxmanContextManager,
) -> None:
    assert await adapter.get_events() == []


async def test_get_and_stream_events_respect_cursor(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    fake_client.events = [
        {"seq": 1, "type": "segment_appended"},
        {"seq": 2, "type": "render_served"},
        {"seq": 3, "type": "frame_pushed"},
    ]
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)

    pulled = await adapter.get_events(after_seq=1)
    assert [event["seq"] for event in pulled] == [2, 3]

    streamed = [event async for event in adapter.stream_events(after_seq=2)]
    assert [event["seq"] for event in streamed] == [3]


async def test_stream_events_without_session_yields_nothing(
    adapter: CtxmanContextManager,
) -> None:
    events = [event async for event in adapter.stream_events()]
    assert events == []


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


async def test_snapshot_includes_watermark_status_item(
    adapter: CtxmanContextManager,
    fake_client: FakeCtxmanClient,
) -> None:
    fake_client.watermark_state = "soft"
    adapter.initialize("the mission", {}, "base prompt")
    await adapter.prepare_for_llm(rebuild_system_prompt=False)
    snapshot = adapter.snapshot()
    status_items = [item for item in snapshot.system_prompt if "watermark=soft" in item.title]
    assert len(status_items) == 1
    assert "server_tokens=4321" in status_items[0].title


# ---------------------------------------------------------------------------
# Config / factory
# ---------------------------------------------------------------------------


def test_ctxman_config_rejects_invalid_on_unavailable() -> None:
    with pytest.raises(ValueError, match="on_unavailable"):
        CtxmanConfig.from_dict({"on_unavailable": "explode"})


def test_factory_builds_frame_bound_adapter_when_binding_active(
    fake_client: FakeCtxmanClient,
    mock_history_manager: Mock,
    mock_logger: Mock,
) -> None:
    factory = build_ctxman_context_manager_factory(CtxmanConfig())
    binding = FrameBinding(client=fake_client, session_id="parent", frame_id="f1")
    token = set_frame_binding(binding)
    try:
        adapter = factory(
            message_history_manager=mock_history_manager,
            openai_tools=[],
            token_budgeter=TokenBudgeter(logger=mock_logger, max_input_tokens=1000),
            logger=mock_logger,
        )
    finally:
        reset_frame_binding(token)
    assert adapter._frame_binding is binding
    assert adapter._client is fake_client
    assert adapter._owns_client is False
