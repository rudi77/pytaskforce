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

from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from taskforce.application.executor import AgentExecutor, ProgressUpdate
from taskforce.core.domain.action_log import (
    ActionLog,
    TurnRecorder,
    format_action_log,
    format_footer,
)
from taskforce.core.domain.enums import EventType, MessageRole
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
    AgentLookupProtocol,
    ConversationStoreProtocol,
    OutboundSenderProtocol,
    RecipientInfo,
    RecipientRegistryProtocol,
    RecipientResolverProtocol,
    WorkflowLookupProtocol,
)

if TYPE_CHECKING:
    from taskforce.application.conversation_manager import ConversationManager
    from taskforce.application.request_queue import RequestQueue

import re

# ADR-022 §4: leading "@name" mention to route a chat message to a specific
# agent owned by the recipient. The name must start with a letter (or "_")
# and is followed by at least one whitespace character — so addresses like
# "@gmail.com" embedded in a sentence are not misinterpreted as routing.
_AGENT_MENTION_RE = re.compile(r"^\s*@([A-Za-z_][A-Za-z0-9_-]*)\s+(.*)", re.DOTALL)


def _extract_agent_mention(text: str) -> tuple[str | None, str]:
    """Return ``(agent_name, remainder)`` if the message starts with an
    ``@name`` mention, else ``(None, text)``.

    The mention is stripped from the returned remainder so the agent
    sees the request without the routing prefix. Whitespace surrounding
    the mention is consumed.
    """
    match = _AGENT_MENTION_RE.match(text)
    if match is None:
        return (None, text)
    return (match.group(1), match.group(2))


# Patterns that indicate a status-string response rather than a real answer.
# These should never be sent to users as the final reply.
_STATUS_PATTERNS = [
    re.compile(r"^Execution completed\.?\s*Status:", re.IGNORECASE),
    re.compile(r"^Status:\s*(completed|failed|error|unknown)", re.IGNORECASE),
    re.compile(r"^Exceeded max steps", re.IGNORECASE),
]

_FALLBACK_MESSAGES = {
    "completed": (
        "Ich habe die Aufgabe bearbeitet, konnte aber keine klare Antwort formulieren. "
        "Kannst du deine Frage noch einmal anders stellen?"
    ),
    "failed": (
        "Bei der Bearbeitung ist leider ein Problem aufgetreten. "
        "Bitte versuche es noch einmal oder formuliere die Anfrage anders."
    ),
}


class _PassthroughRecipientResolver:
    """Default resolver: treats ``channel_identity['sender_id']`` as the recipient.

    Preserves the gateway's pre-resolver behaviour exactly — every
    inbound message resolves to a recipient with ``recipient_id``
    derived from (in order) ``sender_id``, ``conversation_id``, or
    the literal ``"anonymous"``. The pass-through never produces a
    ``None`` result, so legacy callers never see the gateway's
    deny path.

    Custom resolvers replace this implementation and may return
    ``None`` to refuse a message.
    """

    async def resolve(
        self,
        channel: str,
        channel_identity: dict[str, Any],
    ) -> RecipientInfo | None:
        sender_id = (
            channel_identity.get("sender_id")
            or channel_identity.get("conversation_id")
            or "anonymous"
        )
        return RecipientInfo(recipient_id=str(sender_id))


def _sanitize_reply(reply: str, status: str | Any) -> str:
    """Ensure the reply sent to users is a substantive answer, not a status string."""
    if not reply or not reply.strip():
        status_str = status.value if hasattr(status, "value") else str(status)
        return _FALLBACK_MESSAGES.get(status_str, _FALLBACK_MESSAGES["failed"])

    stripped = reply.strip()
    for pattern in _STATUS_PATTERNS:
        if pattern.match(stripped):
            status_str = status.value if hasattr(status, "value") else str(status)
            return _FALLBACK_MESSAGES.get(status_str, _FALLBACK_MESSAGES["failed"])

    return reply


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

    # Slash command that returns the tool-call summary for the previous turn
    # (issue #157).  Always available, regardless of ``actions_summary_mode``.
    ACTIONS_COMMAND = "/actions"

    # Allowed values for ``actions_summary_mode``.
    ACTIONS_SUMMARY_DISABLED = "disabled"
    ACTIONS_SUMMARY_FOOTER = "footer"

    # Default welcome message sent after a conversation reset.
    _WELCOME_MESSAGE = (
        "👋 Willkommen! Die Konversation wurde zurückgesetzt. " "Wie kann ich Ihnen helfen?"
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
        conversation_manager_provider: Callable[[], ConversationManager | None] | None = None,
        request_queue: RequestQueue | None = None,
        max_conversation_history: int = 30,
        recipient_resolver: RecipientResolverProtocol | None = None,
        agent_lookup: AgentLookupProtocol | None = None,
        workflow_lookup: WorkflowLookupProtocol | None = None,
        workflow_runner: Callable[[str, str | None], Awaitable[list[dict[str, Any]]]] | None = None,
        components_provider: Callable[[], Any] | None = None,
        actions_summary_mode: str = "disabled",
        max_action_logs: int = 10,
    ) -> None:
        self._executor = executor
        self._conversation_store = conversation_store
        self._recipient_registry = recipient_registry
        self._outbound_senders = dict(outbound_senders or {})
        self._pending_channel_store = pending_channel_store
        self._conversation_manager = conversation_manager
        self._conversation_manager_provider = conversation_manager_provider
        self._request_queue = request_queue
        self._max_conversation_history = max_conversation_history
        self._recipient_resolver: RecipientResolverProtocol = (
            recipient_resolver or _PassthroughRecipientResolver()
        )
        self._agent_lookup: AgentLookupProtocol | None = agent_lookup
        self._workflow_lookup: WorkflowLookupProtocol | None = workflow_lookup
        self._workflow_runner = workflow_runner
        # ADR-022 §4 / G1: optional components provider so the gateway
        # singleton can serve different tenants by re-reading components
        # per-call. None ⇒ constructor-provided defaults are sticky
        # (single-tenant behaviour, bit-for-bit unchanged).
        self._components_provider: Callable[[], Any] | None = components_provider
        # --- Action transparency (issue #157) -----------------------------
        # ``actions_summary_mode`` controls the always-on footer behaviour;
        # ``/actions`` itself works in every mode.  ``max_action_logs`` caps
        # the per-conversation history so the in-memory store stays bounded.
        if actions_summary_mode not in (
            self.ACTIONS_SUMMARY_DISABLED,
            self.ACTIONS_SUMMARY_FOOTER,
        ):
            raise ValueError(
                f"actions_summary_mode must be 'disabled' or 'footer', got "
                f"{actions_summary_mode!r}"
            )
        self._actions_summary_mode = actions_summary_mode
        self._max_action_logs = max(1, int(max_action_logs))
        # Per-conversation rolling action-log storage.  Keyed by
        # ``(channel, conversation_id)`` so different chats don't collide.
        self._action_logs: dict[tuple[str, str], deque[ActionLog]] = {}
        # Counter for assigning monotonically-increasing turn indices per
        # conversation, independent of how many logs we keep on disk.
        self._turn_counters: dict[tuple[str, str], int] = {}
        self._logger = structlog.get_logger()

    def _resolve_recipient_registry(self) -> RecipientRegistryProtocol:
        """Return the recipient registry for the current request."""
        if self._components_provider is None:
            return self._recipient_registry
        try:
            components = self._components_provider()
        except Exception as exc:  # pragma: no cover — defensive
            self._logger.warning(
                "gateway.components_provider_failed",
                error=str(exc),
            )
            return self._recipient_registry
        return getattr(components, "recipient_registry", self._recipient_registry)

    def _resolve_outbound_senders(self) -> dict[str, OutboundSenderProtocol]:
        """Return outbound senders for the current request."""
        if self._components_provider is None:
            return self._outbound_senders
        try:
            components = self._components_provider()
        except Exception as exc:  # pragma: no cover — defensive
            self._logger.warning(
                "gateway.components_provider_failed",
                error=str(exc),
            )
            return self._outbound_senders
        senders = getattr(components, "outbound_senders", None)
        if not senders:
            return self._outbound_senders
        return dict(senders)

    def _resolve_conversation_store(self) -> ConversationStoreProtocol:
        """Return the channel conversation store for the current request."""
        if self._components_provider is None:
            return self._conversation_store
        try:
            components = self._components_provider()
        except Exception as exc:  # pragma: no cover — defensive
            self._logger.warning(
                "gateway.components_provider_failed",
                error=str(exc),
            )
            return self._conversation_store
        return getattr(components, "conversation_store", self._conversation_store)

    def _resolve_conversation_manager(self) -> ConversationManager | None:
        """Return the persistent conversation manager for the current request."""
        if self._conversation_manager_provider is None:
            return self._conversation_manager
        try:
            return self._conversation_manager_provider()
        except Exception as exc:  # pragma: no cover — defensive
            self._logger.warning(
                "gateway.conversation_manager_provider_failed",
                error=str(exc),
            )
            return self._conversation_manager

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
                sender = self._resolve_outbound_senders().get(message.channel)
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

        # ------- /actions slash command (issue #157) -------
        # Handled before reset so /actions never accidentally clears the
        # conversation history.  We accept either the bare command or the
        # command with trailing whitespace/arguments (currently ignored).
        stripped = message.message.strip().lower()
        first_token = stripped.split(maxsplit=1)[0] if stripped else ""
        if first_token == self.ACTIONS_COMMAND:
            return await self._handle_actions_command(message)

        # ------- Reset commands (/start, /new, /reset) -------
        if stripped in self.RESET_COMMANDS:
            return await self._handle_reset(message)

        # ------- Resolve recipient via injected resolver -------
        # Custom resolvers may refuse a message by returning ``None``;
        # the default pass-through always succeeds so legacy callers
        # never reach this branch.
        recipient = await self._recipient_resolver.resolve(
            message.channel,
            {
                "sender_id": message.sender_id,
                "conversation_id": message.conversation_id,
                "metadata": message.metadata,
            },
        )
        if recipient is None:
            self._logger.info(
                "gateway.recipient.unresolved",
                channel=message.channel,
                conversation_id=message.conversation_id,
                sender_id=message.sender_id,
            )
            return GatewayResponse(
                session_id="",
                status="recipient_unresolved",
                reply="",
                history=[],
            )

        # ------- Normal inbound message flow -------
        resolved_options = options or GatewayOptions()
        from dataclasses import replace

        # ADR-022 §4 / §7 / G5: @<name> routing within the recipient's
        # tenant. The gateway tries an agent lookup first, then a
        # workflow lookup (chat-triggered workflows). Both lookups are
        # tenant-scoped by their implementations, so a cross-tenant
        # mention can never resolve. With neither lookup installed the
        # mention is treated as "no agent by that name" (audited deny).
        mention, stripped_text = _extract_agent_mention(message.message)
        if mention is not None:
            resolved_agent_id: str | None = None
            if self._agent_lookup is not None:
                resolved_agent_id = await self._agent_lookup.find_by_name(recipient, mention)

            if resolved_agent_id is None and self._workflow_lookup is not None:
                workflow_id = await self._workflow_lookup.find_by_name(recipient, mention)
                if workflow_id is not None:
                    self._logger.info(
                        "gateway.workflow_mention.resolved",
                        channel=message.channel,
                        sender_id=message.sender_id,
                        mention=mention,
                        workflow_id=workflow_id,
                    )
                    return await self._dispatch_workflow(
                        workflow_id=workflow_id,
                        message=replace(message, message=stripped_text),
                        options=resolved_options,
                    )

            if resolved_agent_id is None:
                self._logger.info(
                    "gateway.agent_mention.unresolved",
                    channel=message.channel,
                    sender_id=message.sender_id,
                    mention=mention,
                )
                return GatewayResponse(
                    session_id="",
                    status="agent_unresolved",
                    reply="",
                    history=[],
                )

            self._logger.info(
                "gateway.agent_mention.resolved",
                channel=message.channel,
                sender_id=message.sender_id,
                mention=mention,
                agent_id=resolved_agent_id,
            )
            resolved_options = replace(resolved_options, agent_id=resolved_agent_id)
            # Strip the routing prefix so the agent sees a clean request.
            message = replace(message, message=stripped_text)

        # Use resolver-provided default agent when no explicit override is given.
        if resolved_options.agent_id is None and recipient.default_agent_id is not None:
            resolved_options = replace(resolved_options, agent_id=recipient.default_agent_id)

        session_id = await self._resolve_session_id(
            channel=message.channel,
            conversation_id=message.conversation_id,
            explicit_session_id=resolved_options.session_id,
        )

        # Auto-register sender for future push notifications
        if message.sender_id:
            await self._resolve_recipient_registry().register(
                channel=message.channel,
                user_id=message.sender_id,
                reference={
                    "conversation_id": message.conversation_id,
                    "metadata": message.metadata,
                },
            )

        # --- ADR-016 Phase 4: queue-based routing ---
        conversation_manager = self._resolve_conversation_manager()
        if self._request_queue and conversation_manager:
            return await self._handle_via_queue(
                message=message,
                session_id=session_id,
                options=resolved_options,
                conversation_manager=conversation_manager,
            )

        # --- ADR-016 Phase 3: conversation-managed history ---
        if conversation_manager:
            return await self._handle_with_conversation_manager(
                message=message,
                session_id=session_id,
                options=resolved_options,
                conversation_manager=conversation_manager,
            )

        # --- Legacy: channel-keyed conversation store ---
        store = self._resolve_conversation_store()
        history = await store.load_history(message.channel, message.conversation_id)
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
        senders = self._resolve_outbound_senders()
        registry = self._resolve_recipient_registry()
        sender = senders.get(request.channel)
        if not sender:
            return NotificationResult(
                success=False,
                channel=request.channel,
                recipient_id=request.recipient_id,
                tenant_id=request.tenant_id,
                error=f"No outbound sender configured for channel '{request.channel}'",
            )

        reference = await registry.resolve(channel=request.channel, user_id=request.recipient_id)
        if not reference:
            return NotificationResult(
                success=False,
                channel=request.channel,
                recipient_id=request.recipient_id,
                tenant_id=request.tenant_id,
                error=f"Recipient '{request.recipient_id}' not registered on '{request.channel}'",
            )

        # Use conversation_id from the stored reference as the send target
        target_id = reference.get("conversation_id", request.recipient_id)

        # Attachment_type override for the whole request (applies to every
        # attachment). Individual per-file overrides would require a richer
        # request model; keep it simple for now.
        attachment_type = (request.metadata or {}).get("attachment_type", "auto")

        try:
            if request.attachments:
                # First file carries the message as caption; subsequent
                # files go without caption to avoid duplication.
                for idx, file_path in enumerate(request.attachments):
                    await sender.send_file(
                        recipient_id=target_id,
                        file_path=file_path,
                        caption=request.message if idx == 0 else None,
                        attachment_type=attachment_type,
                        metadata=request.metadata,
                    )
            else:
                await sender.send(
                    recipient_id=target_id,
                    message=request.message,
                    metadata=request.metadata,
                )
            self._logger.info(
                "gateway.notification.sent",
                channel=request.channel,
                recipient_id=request.recipient_id,
                tenant_id=request.tenant_id,
                attachments=len(request.attachments),
            )
            return NotificationResult(
                success=True,
                channel=request.channel,
                recipient_id=request.recipient_id,
                tenant_id=request.tenant_id,
            )
        except Exception as exc:
            self._logger.error(
                "gateway.notification.failed",
                channel=request.channel,
                recipient_id=request.recipient_id,
                tenant_id=request.tenant_id,
                error=str(exc),
            )
            return NotificationResult(
                success=False,
                channel=request.channel,
                recipient_id=request.recipient_id,
                tenant_id=request.tenant_id,
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
        tenant_id: str | None = None,
    ) -> list[NotificationResult]:
        """Send a message to all registered recipients on a channel.

        ADR-022 §4: when ``tenant_id`` is supplied the broadcast is
        filtered to recipients whose stored reference carries the
        matching ``tenant_id``. With ``tenant_id=None`` the legacy
        single-tenant behaviour applies (every registered recipient
        receives the message). Each :class:`NotificationResult` carries
        the originating tenant id so audit logs can group deliveries.

        Args:
            channel: Target channel.
            message: Message text.
            metadata: Optional channel-specific formatting.
            tenant_id: When provided, only recipients registered with a
                matching ``tenant_id`` field on their reference receive
                the broadcast.

        Returns:
            List of NotificationResult, one per recipient.
        """
        scope_tenant_id = tenant_id or "default"
        registry = self._resolve_recipient_registry()
        recipients = await registry.list_recipients(channel)
        results: list[NotificationResult] = []
        for user_id in recipients:
            if tenant_id is not None:
                reference = await registry.resolve(channel=channel, user_id=user_id)
                ref_tenant = (reference or {}).get("tenant_id", "default")
                if ref_tenant != tenant_id:
                    continue
            result = await self.send_notification(
                NotificationRequest(
                    channel=channel,
                    recipient_id=user_id,
                    message=message,
                    metadata=metadata or {},
                    tenant_id=scope_tenant_id,
                )
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def supported_channels(self) -> set[str]:
        """Return channels that have an outbound sender configured."""
        return set(self._resolve_outbound_senders().keys())

    # ------------------------------------------------------------------
    # Action transparency (issue #157)
    # ------------------------------------------------------------------

    @property
    def actions_summary_mode(self) -> str:
        """Return the configured outbound-footer mode (`disabled` or `footer`)."""
        return self._actions_summary_mode

    def get_action_logs(self, channel: str, conversation_id: str) -> list[ActionLog]:
        """Return the stored action logs for a conversation (oldest first).

        Used by tests and tooling — the gateway itself drives the
        ``/actions`` command via :meth:`_format_actions_reply`.
        """
        return list(self._action_logs.get((channel, conversation_id), ()))

    def _store_action_log(self, *, channel: str, conversation_id: str, log: ActionLog) -> None:
        """Append ``log`` to the rolling per-conversation deque."""
        key = (channel, conversation_id)
        bucket = self._action_logs.get(key)
        if bucket is None:
            bucket = deque(maxlen=self._max_action_logs)
            self._action_logs[key] = bucket
        bucket.append(log)

    def _next_turn_index(self, *, channel: str, conversation_id: str) -> int:
        """Return + bump the next turn index for this conversation."""
        key = (channel, conversation_id)
        idx = self._turn_counters.get(key, 0)
        self._turn_counters[key] = idx + 1
        return idx

    def _build_recorder(
        self, *, channel: str, conversation_id: str, user_message: str
    ) -> TurnRecorder:
        """Construct a fresh :class:`TurnRecorder` for one user turn."""
        return TurnRecorder(
            turn_index=self._next_turn_index(channel=channel, conversation_id=conversation_id),
            user_message=user_message,
        )

    def _format_actions_reply(self, channel: str, conversation_id: str) -> str:
        """Render the most recent action log for the ``/actions`` command."""
        logs = self._action_logs.get((channel, conversation_id))
        latest: ActionLog | None = logs[-1] if logs else None
        return format_action_log(latest)

    def _maybe_append_footer(self, reply: str, channel: str, conversation_id: str) -> str:
        """Append the actions-summary footer when footer mode is active.

        Always returns the (possibly modified) reply string. Has no
        effect when ``actions_summary_mode`` is ``"disabled"`` or no
        action log was recorded for the latest turn.
        """
        if self._actions_summary_mode != self.ACTIONS_SUMMARY_FOOTER:
            return reply
        logs = self._action_logs.get((channel, conversation_id))
        if not logs:
            return reply
        return reply + format_footer(logs[-1])

    async def _handle_actions_command(self, message: InboundMessage) -> GatewayResponse:
        """Handle a ``/actions`` slash command without invoking the agent."""
        reply = self._format_actions_reply(message.channel, message.conversation_id)
        sender = self._resolve_outbound_senders().get(message.channel)
        if sender:
            try:
                await sender.send(
                    recipient_id=message.conversation_id,
                    message=reply,
                    metadata={"status": "actions_summary"},
                )
            except Exception as exc:
                self._logger.warning(
                    "gateway.actions_command.send_failed",
                    channel=message.channel,
                    error=str(exc),
                )
        self._logger.info(
            "gateway.actions_command",
            channel=message.channel,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
        )
        return GatewayResponse(
            session_id="",
            status="actions_summary",
            reply=reply,
            history=[],
        )

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
        await self._resolve_conversation_store().delete_conversation(
            message.channel, message.conversation_id
        )

        # Archive current conversation and start fresh (ADR-016).
        conv_id: str | None = None
        conversation_manager = self._resolve_conversation_manager()
        if conversation_manager and message.sender_id:
            conv_id = await conversation_manager.create_new(message.channel, message.sender_id)

        # Send welcome message via outbound sender.
        sender = self._resolve_outbound_senders().get(message.channel)
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

    def _trim_history(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        conversation_manager: ConversationManager,
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

        if not self._request_queue.is_running:
            raise RuntimeError(
                "RequestQueue has no active consumer. Start a RequestProcessor "
                "or PersistentAgentService before routing messages through the queue."
            )

        conv_id = await conversation_manager.get_or_create(message.channel, message.sender_id)

        # Build multimodal content for the queue metadata so the processor
        # can pass it through to the conversation history.
        attachments = message.metadata.get("attachments")
        queue_metadata: dict[str, Any] = {
            **message.metadata,
            "profile": options.profile or "butler",
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
        final_history = await conversation_manager.get_messages(conv_id)
        await self._resolve_conversation_store().save_history(
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
        conversation_manager: ConversationManager,
    ) -> GatewayResponse:
        """Handle message using ConversationManager (ADR-016 path).

        Uses ``ConversationManager`` for history storage and conversation
        lifecycle instead of the legacy ``ConversationStoreProtocol``.
        """
        conv_id = await conversation_manager.get_or_create(message.channel, message.sender_id)

        # Append user message to conversation.
        user_content = _build_multimodal_content(
            message.message, message.metadata.get("attachments")
        )
        await conversation_manager.append_message(
            conv_id,
            {"role": MessageRole.USER.value, "content": user_content},
        )

        # Load history for agent context (trimmed to limit).
        history = await conversation_manager.get_messages(conv_id)

        result = await self._execute_agent(
            message=message.message,
            session_id=session_id,
            conversation_history=self._trim_history(history),
            options=options,
            source_channel=message.channel,
            source_conversation_id=message.conversation_id,
        )

        # Append assistant reply.
        await conversation_manager.append_message(
            conv_id,
            {"role": MessageRole.ASSISTANT.value, "content": result.final_message},
        )

        # Also persist to legacy store for backward compatibility.
        final_history = await conversation_manager.get_messages(conv_id)
        await self._resolve_conversation_store().save_history(
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
        """Send outbound reply if a sender is configured for the channel.

        When ``actions_summary_mode`` is ``"footer"``, a one-line summary
        of the last turn's tool-call activity is appended to the reply
        before dispatch (issue #157).
        """
        sender = self._resolve_outbound_senders().get(channel)
        if sender:
            sanitized = _sanitize_reply(reply, status)
            sanitized = self._maybe_append_footer(sanitized, channel, conversation_id)
            try:
                await sender.send(
                    recipient_id=conversation_id,
                    message=sanitized,
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
            await self._resolve_conversation_store().set_session_id(
                channel, conversation_id, explicit_session_id
            )
            return explicit_session_id

        store = self._resolve_conversation_store()
        existing = await store.get_session_id(channel, conversation_id)
        if existing:
            return existing

        generated = str(uuid4())
        await store.set_session_id(channel, conversation_id, generated)
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
        registry = self._resolve_recipient_registry()
        recipients = await registry.list_recipients(channel)
        if not recipients:
            return None

        for user_id in recipients:
            reference = await registry.resolve(channel=channel, user_id=user_id)
            conversation_id = str((reference or {}).get("conversation_id", ""))
            if conversation_id and conversation_id == recipient_id:
                return user_id

        if len(recipients) == 1:
            return recipients[0]

        return None

    async def _dispatch_workflow(
        self,
        *,
        workflow_id: str,
        message: InboundMessage,
        options: GatewayOptions,
    ) -> GatewayResponse:
        """Run a chat-triggered workflow and return/send its final reply."""
        metadata = {
            "workflow_id": workflow_id,
            "stripped_message": message.message,
        }
        if self._workflow_runner is None:
            return GatewayResponse(
                session_id="",
                status="workflow_dispatched",
                reply="",
                history=[],
                conversation_id=None,
                metadata=metadata,
            )

        session_id = await self._resolve_session_id(
            channel=message.channel,
            conversation_id=message.conversation_id,
            explicit_session_id=options.session_id,
        )
        if message.sender_id:
            await self._resolve_recipient_registry().register(
                channel=message.channel,
                user_id=message.sender_id,
                reference={
                    "conversation_id": message.conversation_id,
                    "metadata": message.metadata,
                },
            )

        store = self._resolve_conversation_store()
        history = await store.load_history(message.channel, message.conversation_id)
        history_with_user = _append_message(
            history,
            MessageRole.USER.value,
            _build_multimodal_content(message.message, message.metadata.get("attachments")),
        )
        step_results = await self._workflow_runner(workflow_id, session_id)
        final_step = step_results[-1] if step_results else {}
        reply = str(final_step.get("final_message") or "")
        status = str(final_step.get("status") or "completed")

        final_history = _append_message(history_with_user, MessageRole.ASSISTANT.value, reply)
        await store.save_history(message.channel, message.conversation_id, final_history)
        await self._send_outbound_reply(
            channel=message.channel,
            conversation_id=message.conversation_id,
            reply=reply,
            status=status,
        )
        return GatewayResponse(
            session_id=session_id,
            status=status,
            reply=reply,
            history=final_history,
            conversation_id=None,
            metadata={**metadata, "steps": step_results},
        )

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

        Issue #157: if ``source_channel`` and ``source_conversation_id``
        are both provided, a :class:`TurnRecorder` is wired into the
        ``progress_callback`` of ``execute_mission`` so each turn's
        tool-call activity is captured into ``self._action_logs``.
        """
        user_context = dict(options.user_context) if options.user_context else {}
        if source_channel:
            user_context.setdefault("source_channel", source_channel)
        if source_conversation_id:
            user_context.setdefault("source_conversation_id", source_conversation_id)

        recorder: TurnRecorder | None = None
        progress_callback: Callable[[ProgressUpdate], None] | None = None
        if source_channel and source_conversation_id:
            recorder = self._build_recorder(
                channel=source_channel,
                conversation_id=source_conversation_id,
                user_message=message,
            )
            progress_callback = _make_recorder_callback(recorder)

        try:
            return await self._executor.execute_mission(
                mission=message,
                profile=options.profile,
                session_id=session_id,
                conversation_history=conversation_history,
                progress_callback=progress_callback,
                user_context=user_context or None,
                agent_id=options.agent_id,
                planning_strategy=options.planning_strategy,
                planning_strategy_params=options.planning_strategy_params,
                plugin_path=options.plugin_path,
            )
        finally:
            if recorder is not None and source_channel and source_conversation_id:
                self._store_action_log(
                    channel=source_channel,
                    conversation_id=source_conversation_id,
                    log=recorder.finalize(),
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
        await self._resolve_conversation_store().save_history(
            channel, conversation_id, final_history
        )

        await self._send_outbound_reply(
            channel=channel,
            conversation_id=conversation_id,
            reply=result.final_message,
            status=result.status,
        )

        return GatewayResponse(
            session_id=session_id,
            status=result.status,
            reply=result.final_message,
            history=final_history,
        )


def _make_recorder_callback(
    recorder: TurnRecorder,
) -> Callable[[ProgressUpdate], None]:
    """Build a synchronous progress callback that drives ``recorder``.

    The callback only forwards ``tool_call`` and ``tool_result`` events
    to the recorder; other event types are ignored.  Exceptions raised
    by the recorder are swallowed so a buggy log entry can never abort
    a live agent execution.
    """

    interesting = {EventType.TOOL_CALL.value, EventType.TOOL_RESULT.value}

    def _on_progress(update: ProgressUpdate) -> None:
        evt = update.event_type
        evt_str = evt.value if hasattr(evt, "value") else str(evt)
        if evt_str not in interesting:
            return
        try:
            recorder.observe(evt_str, update.details)
        except Exception:  # noqa: BLE001 — recorder must never crash a run
            pass

    return _on_progress


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
            parts.append({"type": "image_url", "image_url": {"url": att["data_url"]}})
            # If the image was also saved to disk, add a file reference so
            # sub-agents (which cannot see inline images) can access the file.
            if att.get("file_path"):
                file_path = att["file_path"]
                file_name = att.get("file_name", "photo.jpg")
                doc_references.append(f"[Attached file: {file_name} (image) saved at: {file_path}]")
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
