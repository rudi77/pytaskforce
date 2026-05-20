"""Tests for the gateway's typing-keepalive integration.

Verifies that when a channel sender exposes ``send_typing``, the gateway
* fires the indicator at least once before the agent finishes,
* keeps the task isolated from the main execution path (a flaky
  indicator must not block message delivery), and
* cancels the keepalive cleanly whether the agent run completes
  normally OR raises.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from taskforce.application.gateway import CommunicationGateway
from taskforce.core.domain.gateway import InboundMessage
from taskforce.core.domain.models import ExecutionResult
from taskforce.infrastructure.communication.gateway_conversation_store import (
    InMemoryGatewayConversationStore,
)
from taskforce.infrastructure.communication.recipient_registry import (
    InMemoryRecipientRegistry,
)


class _SlowExecutor:
    """Executor that yields the loop a few times before completing.

    The yields let the keepalive task get scheduled at least once so the
    test can observe the typing call.
    """

    def __init__(self, *, raise_on_run: Exception | None = None) -> None:
        self._raise = raise_on_run
        self.calls = 0

    async def execute_mission(self, **kwargs: Any) -> ExecutionResult:
        self.calls += 1
        # Yield repeatedly so the keepalive coro can take its first turn.
        for _ in range(5):
            await asyncio.sleep(0)
        if self._raise is not None:
            raise self._raise
        return ExecutionResult(
            session_id=kwargs["session_id"],
            status="completed",
            final_message="Agent reply",
        )


class _RecordingSender:
    """FakeSender that also counts send_typing invocations."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.typing_calls: list[str] = []

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
        self.sent.append((recipient_id, message))

    async def send_typing(self, recipient_id: str) -> None:
        self.typing_calls.append(recipient_id)


def _build_gateway(executor, sender) -> CommunicationGateway:
    return CommunicationGateway(
        executor=executor,
        conversation_store=InMemoryGatewayConversationStore(),
        recipient_registry=InMemoryRecipientRegistry(),
        outbound_senders={"telegram": sender},
    )


def _inbound(text: str = "Hi") -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        conversation_id="chat-42",
        message=text,
        sender_id="user-7",
    )


@pytest.mark.asyncio
async def test_keepalive_fires_during_normal_run() -> None:
    sender = _RecordingSender()
    executor = _SlowExecutor()
    gateway = _build_gateway(executor, sender)

    await gateway.handle_message(_inbound())

    # At least one typing call must have hit the sender — proves the
    # indicator was started before the executor returned.
    assert sender.typing_calls, "expected at least one send_typing call"
    assert sender.typing_calls[0] == "chat-42"
    # And the final reply still got delivered (keepalive must not block send).
    assert sender.sent and sender.sent[0][0] == "chat-42"


@pytest.mark.asyncio
async def test_keepalive_cancelled_after_normal_completion() -> None:
    sender = _RecordingSender()
    gateway = _build_gateway(_SlowExecutor(), sender)

    await gateway.handle_message(_inbound())

    # No leaked tasks named after our keepalive: it was cancelled and
    # awaited in _execute_agent's finally block.
    pending = [
        t for t in asyncio.all_tasks() if t.get_name().startswith("typing-keepalive:")
    ]
    assert pending == [], f"leaked typing-keepalive tasks: {pending}"


@pytest.mark.asyncio
async def test_keepalive_cancelled_when_executor_raises() -> None:
    sender = _RecordingSender()
    boom = RuntimeError("planned blowup")
    gateway = _build_gateway(_SlowExecutor(raise_on_run=boom), sender)

    with pytest.raises(RuntimeError, match="planned blowup"):
        await gateway.handle_message(_inbound())

    pending = [
        t for t in asyncio.all_tasks() if t.get_name().startswith("typing-keepalive:")
    ]
    assert pending == [], (
        "executor crash must still clean up the keepalive task, "
        f"found: {pending}"
    )


@pytest.mark.asyncio
async def test_keepalive_skipped_for_legacy_sender_without_send_typing() -> None:
    """Senders that pre-date the ``send_typing`` Protocol addition must
    not trigger the keepalive loop. Otherwise the loop's broad
    ``except Exception`` would silently catch an ``AttributeError`` on
    every 4 s tick — no behavioural impact, but DEBUG-log spam per
    active chat for third-party / older integrations.
    """

    class _LegacySender:
        """Implements ``send`` but not ``send_typing`` (pre-typing API)."""

        @property
        def channel(self) -> str:
            return "telegram"

        async def send(self, **kwargs: Any) -> None:
            self.last = kwargs

    sender = _LegacySender()
    gateway = _build_gateway(_SlowExecutor(), sender)

    response = await gateway.handle_message(_inbound())
    assert response.status == "completed"

    # No keepalive task was ever created.
    pending = [
        t for t in asyncio.all_tasks() if t.get_name().startswith("typing-keepalive:")
    ]
    assert pending == [], f"unexpected keepalive task: {pending}"


@pytest.mark.asyncio
async def test_keepalive_swallows_per_iteration_errors() -> None:
    """A flaky sender.send_typing must NOT propagate into the main path."""

    class _BlowingSender(_RecordingSender):
        async def send_typing(self, recipient_id: str) -> None:
            self.typing_calls.append(recipient_id)
            raise RuntimeError("typing broke")

    sender = _BlowingSender()
    gateway = _build_gateway(_SlowExecutor(), sender)

    # The agent run must complete normally regardless of typing errors.
    response = await gateway.handle_message(_inbound())
    assert response.status == "completed"
    assert sender.typing_calls, "send_typing was still invoked despite errors"


@pytest.mark.asyncio
async def test_keepalive_fires_on_queue_path(tmp_path) -> None:
    """Regression: ADR-016 Phase 4 routes through ``_handle_via_queue``
    which bypasses ``_execute_agent``. Without explicit wiring on the
    queue path the typing indicator never fires for the live
    Butler+PersistentAgentService deployment — exactly the symptom
    reported by users running ``dev.ps1``. This test pins typing on
    the queue path so the regression cannot silently come back.
    """
    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.application.request_queue import RequestProcessor, RequestQueue
    from taskforce.infrastructure.persistence.file_conversation_store import (
        FileConversationStore,
    )

    conv_store = FileConversationStore(work_dir=str(tmp_path))
    conv_manager = ConversationManager(conv_store)
    sender = _RecordingSender()
    executor = _SlowExecutor()
    queue = RequestQueue(max_size=10)

    gateway = CommunicationGateway(
        executor=executor,
        conversation_store=InMemoryGatewayConversationStore(),
        recipient_registry=InMemoryRecipientRegistry(),
        outbound_senders={"telegram": sender},
        conversation_manager=conv_manager,
        request_queue=queue,
    )

    processor = RequestProcessor(queue, executor, conversation_manager=conv_manager)
    consumer = asyncio.create_task(processor.run())
    try:
        response = await asyncio.wait_for(
            gateway.handle_message(_inbound()), timeout=5.0
        )
    finally:
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

    assert response.status == "completed"
    assert sender.typing_calls, (
        "queue path must also fire send_typing — without this wiring the "
        "live Butler/PersistentAgentService deployment shows no indicator"
    )
    assert sender.typing_calls[0] == "chat-42"

    # And no leaked keepalive tasks after the handler returned.
    pending = [
        t for t in asyncio.all_tasks() if t.get_name().startswith("typing-keepalive:")
    ]
    assert pending == [], f"leaked typing-keepalive tasks: {pending}"
