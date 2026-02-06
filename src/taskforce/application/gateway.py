"""Unified Communication Gateway.

Single entry point for all agent communication regardless of channel.
Handles inbound message processing, session/history management, agent
execution, outbound reply dispatch, and proactive push notifications.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog

from taskforce.application.executor import AgentExecutor
from taskforce.core.domain.enums import MessageRole
from taskforce.core.domain.gateway import (
    GatewayOptions,
    GatewayResponse,
    InboundMessage,
    NotificationRequest,
    NotificationResult,
)
from taskforce.core.domain.models import ExecutionResult
from taskforce.core.interfaces.gateway import (
    ConversationStoreProtocol,
    OutboundSenderProtocol,
    RecipientRegistryProtocol,
)


class CommunicationGateway:
    """Unified gateway for all agent communication channels.

    Consolidates session management, conversation history, agent execution,
    outbound reply dispatch, and proactive push notifications into a single
    orchestration point.

    Usage::

        gateway = CommunicationGateway(
            executor=executor,
            conversation_store=store,
            recipient_registry=registry,
            outbound_senders={"telegram": telegram_sender},
        )

        # Handle an inbound message (from any channel)
        response = await gateway.handle_message(inbound_msg, options)

        # Send a proactive push notification
        result = await gateway.send_notification(notification_req)
    """

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        conversation_store: ConversationStoreProtocol,
        recipient_registry: RecipientRegistryProtocol,
        outbound_senders: dict[str, OutboundSenderProtocol] | None = None,
    ) -> None:
        self._executor = executor
        self._conversation_store = conversation_store
        self._recipient_registry = recipient_registry
        self._outbound_senders = dict(outbound_senders or {})
        self._logger = structlog.get_logger()

    # ------------------------------------------------------------------
    # Inbound message handling
    # ------------------------------------------------------------------

    async def handle_message(
        self,
        message: InboundMessage,
        options: GatewayOptions | None = None,
    ) -> GatewayResponse:
        """Handle an inbound message from any channel.

        1. Resolve or create session ID.
        2. Load and append to conversation history.
        3. Auto-register sender as push-notification recipient.
        4. Execute agent.
        5. Append reply to history and persist.
        6. Send outbound reply via channel sender (if available).

        Args:
            message: Normalized inbound message.
            options: Execution options (profile, agent_id, etc.).

        Returns:
            GatewayResponse with session_id, status, reply, and history.
        """
        resolved_options = options or GatewayOptions()

        session_id = await self._resolve_session_id(
            channel=message.channel,
            conversation_id=message.conversation_id,
            explicit_session_id=resolved_options.session_id,
        )

        history = await self._conversation_store.load_history(
            message.channel, message.conversation_id
        )
        history_with_user = _append_message(history, MessageRole.USER.value, message.message)

        # Auto-register sender for future push notifications
        if message.sender_id:
            await self._recipient_registry.register(
                channel=message.channel,
                user_id=message.sender_id,
                reference={
                    "conversation_id": message.conversation_id,
                    "metadata": message.metadata,
                },
            )

        result = await self._execute_agent(
            message=message.message,
            session_id=session_id,
            conversation_history=history_with_user,
            options=resolved_options,
        )

        return await self._finalize_response(
            channel=message.channel,
            conversation_id=message.conversation_id,
            session_id=session_id,
            conversation_history=history_with_user,
            result=result,
        )

    # ------------------------------------------------------------------
    # Proactive push notifications
    # ------------------------------------------------------------------

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        """Send a proactive push notification to a recipient.

        Looks up the recipient's channel-specific reference via the
        RecipientRegistry and dispatches via the corresponding OutboundSender.

        Args:
            request: Notification request with channel, recipient, message.

        Returns:
            NotificationResult indicating success or failure.
        """
        sender = self._outbound_senders.get(request.channel)
        if not sender:
            return NotificationResult(
                success=False,
                channel=request.channel,
                recipient_id=request.recipient_id,
                error=f"No outbound sender configured for channel '{request.channel}'",
            )

        reference = await self._recipient_registry.resolve(
            channel=request.channel, user_id=request.recipient_id
        )
        if not reference:
            return NotificationResult(
                success=False,
                channel=request.channel,
                recipient_id=request.recipient_id,
                error=f"Recipient '{request.recipient_id}' not registered on '{request.channel}'",
            )

        # Use conversation_id from the stored reference as the send target
        target_id = reference.get("conversation_id", request.recipient_id)

        try:
            await sender.send(
                recipient_id=target_id,
                message=request.message,
                metadata=request.metadata,
            )
            self._logger.info(
                "gateway.notification.sent",
                channel=request.channel,
                recipient_id=request.recipient_id,
            )
            return NotificationResult(
                success=True,
                channel=request.channel,
                recipient_id=request.recipient_id,
            )
        except Exception as exc:
            self._logger.error(
                "gateway.notification.failed",
                channel=request.channel,
                recipient_id=request.recipient_id,
                error=str(exc),
            )
            return NotificationResult(
                success=False,
                channel=request.channel,
                recipient_id=request.recipient_id,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    async def broadcast(
        self,
        *,
        channel: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[NotificationResult]:
        """Send a message to all registered recipients on a channel.

        Args:
            channel: Target channel.
            message: Message text.
            metadata: Optional channel-specific formatting.

        Returns:
            List of NotificationResult, one per recipient.
        """
        recipients = await self._recipient_registry.list_recipients(channel)
        results: list[NotificationResult] = []
        for user_id in recipients:
            result = await self.send_notification(
                NotificationRequest(
                    channel=channel,
                    recipient_id=user_id,
                    message=message,
                    metadata=metadata or {},
                )
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def supported_channels(self) -> set[str]:
        """Return channels that have an outbound sender configured."""
        return set(self._outbound_senders.keys())

    def all_channels(self) -> set[str]:
        """Return all channels with any component (inbound or outbound)."""
        channels = set(self._outbound_senders.keys())
        return channels

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_session_id(
        self,
        *,
        channel: str,
        conversation_id: str,
        explicit_session_id: str | None,
    ) -> str:
        """Resolve or generate a session ID for this conversation."""
        if explicit_session_id:
            await self._conversation_store.set_session_id(
                channel, conversation_id, explicit_session_id
            )
            return explicit_session_id

        existing = await self._conversation_store.get_session_id(channel, conversation_id)
        if existing:
            return existing

        generated = str(uuid4())
        await self._conversation_store.set_session_id(channel, conversation_id, generated)
        return generated

    async def _execute_agent(
        self,
        *,
        message: str,
        session_id: str,
        conversation_history: list[dict[str, Any]],
        options: GatewayOptions,
    ) -> ExecutionResult:
        """Delegate to AgentExecutor."""
        return await self._executor.execute_mission(
            mission=message,
            profile=options.profile,
            session_id=session_id,
            conversation_history=conversation_history,
            user_context=options.user_context,
            agent_id=options.agent_id,
            planning_strategy=options.planning_strategy,
            planning_strategy_params=options.planning_strategy_params,
            plugin_path=options.plugin_path,
        )

    async def _finalize_response(
        self,
        *,
        channel: str,
        conversation_id: str,
        session_id: str,
        conversation_history: list[dict[str, Any]],
        result: ExecutionResult,
    ) -> GatewayResponse:
        """Append assistant reply, persist history, and send outbound."""
        final_history = _append_message(
            conversation_history,
            MessageRole.ASSISTANT.value,
            result.final_message,
        )
        await self._conversation_store.save_history(channel, conversation_id, final_history)

        # Send outbound reply if sender is configured for this channel
        sender = self._outbound_senders.get(channel)
        if sender:
            try:
                await sender.send(
                    recipient_id=conversation_id,
                    message=result.final_message,
                    metadata={"status": result.status},
                )
            except Exception as exc:
                self._logger.error(
                    "gateway.outbound.reply_failed",
                    channel=channel,
                    conversation_id=conversation_id,
                    error=str(exc),
                )

        return GatewayResponse(
            session_id=session_id,
            status=result.status,
            reply=result.final_message,
            history=final_history,
        )


def _append_message(history: list[dict[str, Any]], role: str, content: str) -> list[dict[str, Any]]:
    """Return a new history list with the message appended (immutable)."""
    return [*history, {"role": role, "content": content}]
