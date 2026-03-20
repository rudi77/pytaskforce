"""Unified Communication Gateway.

Single entry point for all agent communication regardless of channel.
Handles inbound message processing, session/history management, agent
execution, outbound reply dispatch, proactive push notifications,
and pending channel question resolution.

When a ``ConversationManager`` is provided (ADR-016), the gateway delegates
history management and conversation lifecycle to it instead of using the
legacy ``ConversationStoreProtocol`` directly. This enables persistent,
cross-session conversations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
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
from taskforce.core.interfaces.channel_ask import PendingChannelQuestionStoreProtocol
from taskforce.core.interfaces.gateway import (
    ConversationStoreProtocol,
    OutboundSenderProtocol,
    RecipientRegistryProtocol,
)

if TYPE_CHECKING:
    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.application.request_queue import RequestQueue


class CommunicationGateway:
    """Unified gateway for all agent communication channels.

    Consolidates session management, conversation history, agent execution,
    outbound reply dispatch, proactive push notifications, and cross-channel
    question resolution into a single orchestration point.

    When ``conversation_manager`` is provided, the gateway uses it for
    message history and conversation lifecycle instead of the legacy
    ``conversation_store``.

    When ``request_queue`` is provided, inbound messages are routed through
    the central ``RequestQueue`` for sequential processing instead of
    direct executor calls.

    Usage::

        gateway = CommunicationGateway(
            executor=executor,
            conversation_store=store,
            recipient_registry=registry,
            outbound_senders={"telegram": telegram_sender},
            conversation_manager=conv_manager,  # ADR-016
            request_queue=queue,                # ADR-016 Phase 4
        )

        # Handle an inbound message (from any channel)
        response = await gateway.handle_message(inbound_msg, options)

        # Send a proactive push notification
        result = await gateway.send_notification(notification_req)
    """

    # Commands that reset the conversation (Telegram /start, etc.).
    RESET_COMMANDS = frozenset({"/start", "/new", "/reset"})

    # Default welcome message sent after a conversation reset.
    _WELCOME_MESSAGE = (
        "👋 Willkommen! Die Konversation wurde zurückgesetzt. "
        "Wie kann ich Ihnen helfen?"
    )

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        conversation_store: ConversationStoreProtocol,
        recipient_registry: RecipientRegistryProtocol,
        outbound_senders: dict[str, OutboundSenderProtocol] | None = None,
        pending_channel_store: PendingChannelQuestionStoreProtocol | None = None,
        conversation_manager: ConversationManager | None = None,
        request_queue: RequestQueue | None = None,
        max_conversation_history: int = 30,
    ) -> None:
        self._executor = executor
        self._conversation_store = conversation_store
        self._recipient_registry = recipient_registry
        self._outbound_senders = dict(outbound_senders or {})
        self._pending_channel_store = pending_channel_store
        self._conversation_manager = conversation_manager
        self._request_queue = request_queue
        self._max_conversation_history = max_conversation_history
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

        Before starting a new agent execution the method checks whether
        this message is a **response** to a pending channel question.  If
        so the response is stored and the paused session is notified —
        no new agent execution is started.

        Normal flow:

        1. Check for pending channel question (resolve if matched).
        2. Resolve or create session ID.
        3. Load and append to conversation history.
        4. Auto-register sender as push-notification recipient.
        5. Execute agent.
        6. Append reply to history and persist.
        7. Send outbound reply via channel sender (if available).

        Args:
            message: Normalized inbound message.
            options: Execution options (profile, agent_id, etc.).

        Returns:
            GatewayResponse with session_id, status, reply, and history.
        """
        # ------- Check for pending channel question -------
        if message.sender_id and self._pending_channel_store:
            resolved_session = await self._pending_channel_store.resolve(
                channel=message.channel,
                sender_id=message.sender_id,
                response=message.message,
            )
            if resolved_session:
                self._logger.info(
                    "gateway.pending_question.resolved",
                    channel=message.channel,
                    sender_id=message.sender_id,
                    session_id=resolved_session,
                )
                # Send acknowledgment back to the channel
                sender = self._outbound_senders.get(message.channel)
                if sender:
                    try:
                        await sender.send(
                            recipient_id=message.conversation_id,
                            message="✅ Danke, Ihre Antwort wurde weitergeleitet.",
                        )
                    except Exception:
                        pass  # Best-effort acknowledgment
                return GatewayResponse(
                    session_id=resolved_session,
                    status="channel_response_received",
                    reply="Antwort an den Agenten weitergeleitet.",
                    history=[],
                )

        # ------- Reset commands (/start, /new, /reset) -------
        stripped = message.message.strip().lower()
        if stripped in self.RESET_COMMANDS:
            return await self._handle_reset(message)

        # ------- Normal inbound message flow -------
        resolved_options = options or GatewayOptions()

        session_id = await self._resolve_session_id(
            channel=message.channel,
            conversation_id=message.conversation_id,
            explicit_session_id=resolved_options.session_id,
        )

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

        # --- ADR-016 Phase 4: queue-based routing ---
        if self._request_queue and self._conversation_manager:
            return await self._handle_via_queue(
                message=message,
                session_id=session_id,
                options=resolved_options,
            )

        # --- ADR-016 Phase 3: conversation-managed history ---
        if self._conversation_manager:
            return await self._handle_with_conversation_manager(
                message=message,
                session_id=session_id,
                options=resolved_options,
            )

        # --- Legacy: channel-keyed conversation store ---
        history = await self._conversation_store.load_history(
            message.channel, message.conversation_id
        )
        user_content = _build_multimodal_content(
            message.message, message.metadata.get("attachments")
        )
        history_with_user = _append_message(history, MessageRole.USER.value, user_content)

        result = await self._execute_agent(
            message=message.message,
            session_id=session_id,
            conversation_history=self._trim_history(history_with_user),
            options=resolved_options,
            source_channel=message.channel,
            source_conversation_id=message.conversation_id,
        )

        return await self._finalize_response(
            channel=message.channel,
            conversation_id=message.conversation_id,
            session_id=session_id,
            conversation_history=history_with_user,
            result=result,
        )

    # ------------------------------------------------------------------
    # Channel-targeted question support
    # ------------------------------------------------------------------

    async def send_channel_question(
        self,
        *,
        session_id: str,
        channel: str,
        recipient_id: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a question to a channel recipient and register it as pending.

        This is called when the agent uses ``ask_user(channel=..., recipient_id=...)``
        and the frontend (CLI, API) needs to deliver the question.

        Args:
            session_id: The paused agent session.
            channel: Target channel (e.g. 'telegram').
            recipient_id: Recipient user ID on that channel.
            question: The question text.
            metadata: Optional extra data.

        Returns:
            True if the question was sent and registered successfully.
        """
        effective_recipient_id = recipient_id

        # Send the question via notification
        result = await self.send_notification(
            NotificationRequest(
                channel=channel,
                recipient_id=effective_recipient_id,
                message=question,
                metadata=metadata or {},
            )
        )
        if not result.success:
            fallback_recipient_id = await self._resolve_fallback_recipient_id(
                channel=channel,
                recipient_id=recipient_id,
            )
            if fallback_recipient_id and fallback_recipient_id != recipient_id:
                self._logger.warning(
                    "gateway.channel_question.recipient_fallback",
                    session_id=session_id,
                    channel=channel,
                    requested_recipient_id=recipient_id,
                    fallback_recipient_id=fallback_recipient_id,
                )
                effective_recipient_id = fallback_recipient_id
                result = await self.send_notification(
                    NotificationRequest(
                        channel=channel,
                        recipient_id=effective_recipient_id,
                        message=question,
                        metadata=metadata or {},
                    )
                )

        if not result.success:
            self._logger.error(
                "gateway.channel_question.send_failed",
                session_id=session_id,
                channel=channel,
                recipient_id=effective_recipient_id,
                requested_recipient_id=recipient_id,
                error=result.error,
            )
            return False

        # Register as pending question
        if self._pending_channel_store:
            await self._pending_channel_store.register(
                session_id=session_id,
                channel=channel,
                recipient_id=effective_recipient_id,
                question=question,
                metadata=metadata,
            )

        self._logger.info(
            "gateway.channel_question.sent",
            session_id=session_id,
            channel=channel,
            recipient_id=effective_recipient_id,
            requested_recipient_id=recipient_id,
        )
        return True

    async def poll_channel_response(self, *, session_id: str) -> str | None:
        """Poll for a response to a pending channel question.

        Returns the response text if available, or None if still waiting.

        Args:
            session_id: The paused agent session to check.

        Returns:
            Response text or None.
        """
        if not self._pending_channel_store:
            return None
        return await self._pending_channel_store.get_response(session_id=session_id)

    async def clear_channel_question(self, *, session_id: str) -> None:
        """Remove a pending channel question after the agent has resumed.

        Args:
            session_id: The agent session whose question to clear.
        """
        if self._pending_channel_store:
            await self._pending_channel_store.remove(session_id=session_id)

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _handle_reset(self, message: InboundMessage) -> GatewayResponse:
        """Clear conversation history and send a welcome message.

        Handles ``/start``, ``/new``, and ``/reset`` commands by wiping the
        conversation history in both the legacy store and the conversation
        manager (ADR-016), then sending a welcome reply via the outbound
        sender.
        """
        self._logger.info(
            "gateway.conversation_reset",
            channel=message.channel,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
        )

        # Delete the entire conversation record (history + session mapping)
        # so that the next message gets a fresh session ID.
        await self._conversation_store.delete_conversation(
            message.channel, message.conversation_id
        )

        # Archive current conversation and start fresh (ADR-016).
        conv_id: str | None = None
        if self._conversation_manager and message.sender_id:
            conv_id = await self._conversation_manager.create_new(
                message.channel, message.sender_id
            )

        # Send welcome message via outbound sender.
        sender = self._outbound_senders.get(message.channel)
        if sender:
            try:
                await sender.send(
                    recipient_id=message.conversation_id,
                    message=self._WELCOME_MESSAGE,
                )
            except Exception as exc:
                self._logger.warning(
                    "gateway.reset.welcome_send_failed",
                    channel=message.channel,
                    error=str(exc),
                )

        return GatewayResponse(
            session_id="",
            status="conversation_reset",
            reply=self._WELCOME_MESSAGE,
            history=[],
            conversation_id=conv_id,
        )

    def _trim_history(
        self, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Trim conversation history to the last N messages."""
        if len(history) <= self._max_conversation_history:
            return history
        return history[-self._max_conversation_history :]

    async def _handle_via_queue(
        self,
        *,
        message: InboundMessage,
        session_id: str,
        options: GatewayOptions,
    ) -> GatewayResponse:
        """Handle message by routing through the RequestQueue (ADR-016 Phase 4).

        Creates a conversation via ``ConversationManager``, wraps the message
        in an ``AgentRequest``, enqueues it, and awaits the result Future.

        A ``RequestProcessor`` (or ``PersistentAgentService``) **must** be
        consuming the queue before this method is called — otherwise the
        ``await future`` below will block indefinitely.

        Raises:
            RuntimeError: If no consumer is active on the queue.
        """
        from taskforce.core.domain.request import AgentRequest

        assert self._request_queue is not None
        assert self._conversation_manager is not None

        if not self._request_queue.is_running:
            raise RuntimeError(
                "RequestQueue has no active consumer. Start a RequestProcessor "
                "or PersistentAgentService before routing messages through the queue."
            )

        conv_id = await self._conversation_manager.get_or_create(
            message.channel, message.sender_id
        )

        # Build multimodal content for the queue metadata so the processor
        # can pass it through to the conversation history.
        attachments = message.metadata.get("attachments")
        queue_metadata: dict[str, Any] = {
            **message.metadata,
            "profile": options.profile or "dev",
            "channel_conversation_id": message.conversation_id,
            "user_context": options.user_context,
            "agent_id": options.agent_id,
            "planning_strategy": options.planning_strategy,
            "planning_strategy_params": options.planning_strategy_params,
            "plugin_path": options.plugin_path,
        }
        if attachments:
            queue_metadata["multimodal_content"] = _build_multimodal_content(
                message.message, attachments
            )

        request = AgentRequest(
            channel=message.channel,
            message=message.message,
            conversation_id=conv_id,
            sender_id=message.sender_id,
            session_id=session_id,
            metadata=queue_metadata,
        )

        future = await self._request_queue.enqueue(request)
        result = await future

        # Sync to legacy store for backward compatibility.
        final_history = await self._conversation_manager.get_messages(conv_id)
        await self._conversation_store.save_history(
            message.channel, message.conversation_id, final_history
        )

        # Send outbound reply.
        reply = result.reply or ""
        await self._send_outbound_reply(
            channel=message.channel,
            conversation_id=message.conversation_id,
            reply=reply,
            status=result.status,
        )

        return GatewayResponse(
            session_id=session_id,
            status=result.status,
            reply=reply,
            history=final_history,
            conversation_id=conv_id,
        )

    async def _handle_with_conversation_manager(
        self,
        *,
        message: InboundMessage,
        session_id: str,
        options: GatewayOptions,
    ) -> GatewayResponse:
        """Handle message using ConversationManager (ADR-016 path).

        Uses ``ConversationManager`` for history storage and conversation
        lifecycle instead of the legacy ``ConversationStoreProtocol``.
        """
        assert self._conversation_manager is not None  # guarded by caller

        conv_id = await self._conversation_manager.get_or_create(
            message.channel, message.sender_id
        )

        # Append user message to conversation.
        user_content = _build_multimodal_content(
            message.message, message.metadata.get("attachments")
        )
        await self._conversation_manager.append_message(
            conv_id,
            {"role": MessageRole.USER.value, "content": user_content},
        )

        # Load history for agent context (trimmed to limit).
        history = await self._conversation_manager.get_messages(conv_id)

        result = await self._execute_agent(
            message=message.message,
            session_id=session_id,
            conversation_history=self._trim_history(history),
            options=options,
            source_channel=message.channel,
            source_conversation_id=message.conversation_id,
        )

        # Append assistant reply.
        await self._conversation_manager.append_message(
            conv_id,
            {"role": MessageRole.ASSISTANT.value, "content": result.final_message},
        )

        # Also persist to legacy store for backward compatibility.
        final_history = await self._conversation_manager.get_messages(conv_id)
        await self._conversation_store.save_history(
            message.channel, message.conversation_id, final_history
        )

        # Send outbound reply.
        await self._send_outbound_reply(
            channel=message.channel,
            conversation_id=message.conversation_id,
            reply=result.final_message,
            status=result.status,
        )

        return GatewayResponse(
            session_id=session_id,
            status=result.status,
            reply=result.final_message,
            history=final_history,
            conversation_id=conv_id,
        )

    async def _send_outbound_reply(
        self,
        *,
        channel: str,
        conversation_id: str,
        reply: str,
        status: str | Any,
    ) -> None:
        """Send outbound reply if a sender is configured for the channel."""
        sender = self._outbound_senders.get(channel)
        if sender:
            try:
                await sender.send(
                    recipient_id=conversation_id,
                    message=reply,
                    metadata={"status": status},
                )
            except Exception as exc:
                self._logger.error(
                    "gateway.outbound.reply_failed",
                    channel=channel,
                    conversation_id=conversation_id,
                    error=str(exc),
                )

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

    async def _resolve_fallback_recipient_id(
        self,
        *,
        channel: str,
        recipient_id: str,
    ) -> str | None:
        """Resolve a robust fallback user_id when model picked a bad recipient_id.

        Fallback strategy:
        1. Match by stored conversation_id value.
        2. If exactly one recipient is registered on this channel, use it.
        """
        recipients = await self._recipient_registry.list_recipients(channel)
        if not recipients:
            return None

        for user_id in recipients:
            reference = await self._recipient_registry.resolve(
                channel=channel, user_id=user_id
            )
            conversation_id = str((reference or {}).get("conversation_id", ""))
            if conversation_id and conversation_id == recipient_id:
                return user_id

        if len(recipients) == 1:
            return recipients[0]

        return None

    async def _execute_agent(
        self,
        *,
        message: str,
        session_id: str,
        conversation_history: list[dict[str, Any]],
        options: GatewayOptions,
        source_channel: str | None = None,
        source_conversation_id: str | None = None,
    ) -> ExecutionResult:
        """Delegate to AgentExecutor.

        When *source_channel* is provided, it is injected into the user
        context so that the executor can automatically route non-channel-
        targeted ``ask_user`` calls back to the originating channel.
        """
        user_context = dict(options.user_context) if options.user_context else {}
        if source_channel:
            user_context.setdefault("source_channel", source_channel)
        if source_conversation_id:
            user_context.setdefault("source_conversation_id", source_conversation_id)

        return await self._executor.execute_mission(
            mission=message,
            profile=options.profile,
            session_id=session_id,
            conversation_history=conversation_history,
            user_context=user_context or None,
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


def _append_message(
    history: list[dict[str, Any]],
    role: str,
    content: str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a new history list with the message appended (immutable)."""
    return [*history, {"role": role, "content": content}]


def _build_multimodal_content(
    text: str,
    attachments: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    """Build OpenAI-compatible content from text and optional attachments.

    If there are no attachments, returns plain ``text`` (preserving existing
    behavior). For image attachments, returns a content array with text and
    ``image_url`` blocks. For document attachments, appends file path
    references to the text so the agent can use file tools.

    Args:
        text: The user's message text.
        attachments: Optional list of attachment dicts from the poller/webhook.

    Returns:
        Plain string or OpenAI vision-format content array.
    """
    if not attachments:
        return text

    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    doc_references: list[str] = []

    for att in attachments:
        if att.get("type") == "image" and att.get("data_url"):
            parts.append(
                {"type": "image_url", "image_url": {"url": att["data_url"]}}
            )
        elif att.get("type") == "document":
            file_path = att.get("file_path", "")
            file_name = att.get("file_name", "document")
            mime_type = att.get("mime_type", "")
            doc_references.append(
                f"[Attached file: {file_name} ({mime_type}) saved at: {file_path}]"
            )

    # If only document references (no images), return enriched text string.
    if doc_references and len(parts) == 1:
        return text + "\n\n" + "\n".join(doc_references)

    # If we have images, append any doc references as text too.
    if doc_references:
        parts.append({"type": "text", "text": "\n".join(doc_references)})

    return parts
