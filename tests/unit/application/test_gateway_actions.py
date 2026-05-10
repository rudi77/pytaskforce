"""Tests for the per-conversation action log surface in CommunicationGateway.

Covers issue #157:

- ``/actions`` slash command returns the previous turn's tool-call summary.
- Footer mode appends a one-liner to every outbound reply.
- Footer mode is opt-in (default ``disabled``) and never affects ``/actions``.
- The slash command works even when footer mode is disabled.
"""

from __future__ import annotations

from typing import Any

import pytest

from taskforce.application.gateway import CommunicationGateway
from taskforce.core.domain.enums import EventType
from taskforce.core.domain.gateway import InboundMessage
from taskforce.core.domain.models import ExecutionResult
from taskforce.infrastructure.communication.gateway_conversation_store import (
    InMemoryGatewayConversationStore,
)
from taskforce.infrastructure.communication.recipient_registry import (
    InMemoryRecipientRegistry,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _ToolEventExecutor:
    """Executor stub that drives the gateway's progress callback.

    Each call to ``execute_mission`` emits a configurable sequence of
    ``ProgressUpdate``-shaped events through ``progress_callback``
    before returning a canned :class:`ExecutionResult`. The events are
    pulled from ``self.events`` (consumed once), so tests can prime
    different turns with different traffic.
    """

    def __init__(self) -> None:
        self.events: list[list[tuple[str, dict[str, Any]]]] = []
        self.reply: str = "Agent reply"

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        callback = kwargs.get("progress_callback")
        if self.events:
            stream = self.events.pop(0)
            if callback is not None:
                from datetime import datetime

                from taskforce.application.executor import ProgressUpdate

                for event_type, data in stream:
                    callback(
                        ProgressUpdate(
                            timestamp=datetime.now(),
                            event_type=event_type,
                            message="",
                            details=dict(data),
                        )
                    )
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message=self.reply,
        )


class _CapturingSender:
    """Outbound sender that captures every dispatched message."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []

    @property
    def channel(self) -> str:
        return "telegram"

    async def send(
        self,
        *,
        recipient_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.sent.append((recipient_id, message, metadata))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_gateway(
    *,
    actions_summary_mode: str = "disabled",
    max_action_logs: int = 10,
) -> tuple[CommunicationGateway, _ToolEventExecutor, _CapturingSender]:
    executor = _ToolEventExecutor()
    sender = _CapturingSender()
    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=InMemoryGatewayConversationStore(),
        recipient_registry=InMemoryRecipientRegistry(),
        outbound_senders={"telegram": sender},
        actions_summary_mode=actions_summary_mode,
        max_action_logs=max_action_logs,
    )
    return gateway, executor, sender


# ---------------------------------------------------------------------------
# /actions slash command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_actions_command_with_no_prior_turn() -> None:
    gateway, _executor, sender = _build_gateway()

    response = await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-1",
            message="/actions",
            sender_id="user-1",
        )
    )

    assert response.status == "actions_summary"
    assert "No prior actions" in response.reply
    # /actions never invokes the agent, so the only outbound send is the
    # summary itself (no agent reply).
    assert len(sender.sent) == 1
    assert "No prior actions" in sender.sent[0][1]


@pytest.mark.asyncio
async def test_actions_command_returns_previous_turn_summary() -> None:
    gateway, executor, sender = _build_gateway()
    executor.events.append(
        [
            (
                EventType.TOOL_CALL.value,
                {"tool": "file_read", "id": "c1", "args": {"path": "x.txt"}},
            ),
            (
                EventType.TOOL_RESULT.value,
                {"tool": "file_read", "id": "c1", "success": True},
            ),
            (
                EventType.TOOL_CALL.value,
                {"tool": "python", "id": "c2", "args": {"code": "1+1"}},
            ),
            (
                EventType.TOOL_RESULT.value,
                {
                    "tool": "python",
                    "id": "c2",
                    "success": False,
                    "error": "boom",
                },
            ),
        ]
    )

    # Turn 1: drive a real mission so an action log is recorded.
    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-1",
            message="What is in x.txt?",
            sender_id="user-1",
        )
    )

    sender.sent.clear()

    # Turn 2: ask for the action summary.
    response = await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-1",
            message="/actions",
            sender_id="user-1",
        )
    )

    assert response.status == "actions_summary"
    assert "[ok] file_read" in response.reply
    assert "[fail] python" in response.reply
    assert "boom" in response.reply
    assert "2 tools" in response.reply
    assert "1 ok" in response.reply
    assert "1 fail" in response.reply

    # The summary is also delivered to the channel.
    assert len(sender.sent) == 1
    assert "[ok] file_read" in sender.sent[0][1]


@pytest.mark.asyncio
async def test_actions_command_works_with_footer_disabled() -> None:
    """The slash command must work in either summary mode."""
    gateway, executor, _sender = _build_gateway(
        actions_summary_mode="disabled",
    )
    executor.events.append(
        [
            (EventType.TOOL_CALL.value, {"tool": "x", "id": "1"}),
            (EventType.TOOL_RESULT.value, {"tool": "x", "id": "1", "success": True}),
        ]
    )
    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-2",
            message="hi",
            sender_id="user-2",
        )
    )

    response = await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-2",
            message="/actions",
            sender_id="user-2",
        )
    )
    assert "[ok] x" in response.reply


@pytest.mark.asyncio
async def test_actions_command_does_not_clear_history() -> None:
    """``/actions`` must never trigger the reset path."""
    gateway, executor, _sender = _build_gateway()
    executor.events.append(
        [
            (EventType.TOOL_CALL.value, {"tool": "wiki", "id": "1"}),
            (EventType.TOOL_RESULT.value, {"tool": "wiki", "id": "1", "success": True}),
        ]
    )

    # First turn populates history.
    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-3",
            message="What's new?",
            sender_id="user-3",
        )
    )

    # /actions should not reset.
    response = await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-3",
            message="/actions",
            sender_id="user-3",
        )
    )
    assert response.status == "actions_summary"

    logs = gateway.get_action_logs("telegram", "chat-3")
    assert len(logs) == 1


# ---------------------------------------------------------------------------
# Footer mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_footer_mode_appends_summary_line_to_outbound_reply() -> None:
    gateway, executor, sender = _build_gateway(actions_summary_mode="footer")
    executor.events.append(
        [
            (EventType.TOOL_CALL.value, {"tool": "a", "id": "1"}),
            (EventType.TOOL_RESULT.value, {"tool": "a", "id": "1", "success": True}),
            (EventType.TOOL_CALL.value, {"tool": "b", "id": "2"}),
            (EventType.TOOL_RESULT.value, {"tool": "b", "id": "2", "success": True}),
        ]
    )

    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-9",
            message="do stuff",
            sender_id="u",
        )
    )

    assert len(sender.sent) == 1
    sent_message = sender.sent[0][1]
    assert sent_message.startswith("Agent reply")
    assert "— Actions: 2 tools" in sent_message
    assert "2 ok" in sent_message
    assert "0 fail" in sent_message


@pytest.mark.asyncio
async def test_disabled_mode_does_not_append_footer() -> None:
    gateway, executor, sender = _build_gateway(actions_summary_mode="disabled")
    executor.events.append(
        [
            (EventType.TOOL_CALL.value, {"tool": "a", "id": "1"}),
            (EventType.TOOL_RESULT.value, {"tool": "a", "id": "1", "success": True}),
        ]
    )

    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-10",
            message="do stuff",
            sender_id="u",
        )
    )

    assert len(sender.sent) == 1
    assert "Actions:" not in sender.sent[0][1]


@pytest.mark.asyncio
async def test_footer_skipped_when_no_tools_fired() -> None:
    """No tool activity → footer mode emits no line."""
    gateway, _executor, sender = _build_gateway(actions_summary_mode="footer")

    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-11",
            message="just chat",
            sender_id="u",
        )
    )

    assert len(sender.sent) == 1
    assert "Actions:" not in sender.sent[0][1]


# ---------------------------------------------------------------------------
# Storage / configuration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_log_storage_is_capped_per_conversation() -> None:
    gateway, executor, _sender = _build_gateway(max_action_logs=2)
    for _ in range(4):
        executor.events.append(
            [
                (EventType.TOOL_CALL.value, {"tool": "x", "id": "1"}),
                (EventType.TOOL_RESULT.value, {"tool": "x", "id": "1", "success": True}),
            ]
        )
        await gateway.handle_message(
            InboundMessage(
                channel="telegram",
                conversation_id="chat-cap",
                message="round",
                sender_id="u",
            )
        )

    logs = gateway.get_action_logs("telegram", "chat-cap")
    # Only the last two turns are retained, but the turn_index keeps
    # climbing so the ordering is unambiguous.
    assert len(logs) == 2
    assert [log.turn_index for log in logs] == [2, 3]


def test_invalid_summary_mode_raises_value_error() -> None:
    with pytest.raises(ValueError):
        CommunicationGateway(
            executor=_ToolEventExecutor(),
            conversation_store=InMemoryGatewayConversationStore(),
            recipient_registry=InMemoryRecipientRegistry(),
            outbound_senders={"telegram": _CapturingSender()},
            actions_summary_mode="bogus",
        )


# ---------------------------------------------------------------------------
# Integration with ConversationManager (ADR-016 path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_log_is_recorded_on_conversation_manager_path(tmp_path) -> None:
    """The conversation-manager handler must also drive the recorder."""
    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.infrastructure.persistence.file_conversation_store import (
        FileConversationStore,
    )

    executor = _ToolEventExecutor()
    sender = _CapturingSender()
    conv_store = FileConversationStore(work_dir=str(tmp_path))
    conv_manager = ConversationManager(conv_store)
    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=InMemoryGatewayConversationStore(),
        recipient_registry=InMemoryRecipientRegistry(),
        outbound_senders={"telegram": sender},
        conversation_manager=conv_manager,
        actions_summary_mode="footer",
    )

    executor.events.append(
        [
            (EventType.TOOL_CALL.value, {"tool": "wiki", "id": "1"}),
            (EventType.TOOL_RESULT.value, {"tool": "wiki", "id": "1", "success": True}),
            (EventType.TOOL_CALL.value, {"tool": "send_notification", "id": "2"}),
            (
                EventType.TOOL_RESULT.value,
                {"tool": "send_notification", "id": "2", "success": False, "error": "401"},
            ),
        ]
    )

    await gateway.handle_message(
        InboundMessage(
            channel="telegram",
            conversation_id="chat-cm",
            message="Recap last week",
            sender_id="user-cm",
        )
    )

    logs = gateway.get_action_logs("telegram", "chat-cm")
    assert len(logs) == 1
    assert {r.tool_name for r in logs[0].records} == {"wiki", "send_notification"}
    assert logs[0].failure_count == 1
    # Footer mode must propagate to the outbound dispatch on this path too.
    assert "— Actions: 2 tools" in sender.sent[0][1]
