"""Hot-reload manager for per-bot inbound pollers.

The settings store's ``CHANNELS`` section can hold N bot configs (see
:mod:`taskforce.core.domain.settings`). For Telegram each enabled bot
needs its own long-polling task — one ``getUpdates`` loop per token —
because the Telegram Bot API only delivers an update to a single
consumer at a time.

This manager owns one :class:`TelegramPoller` per ``bot_id`` and
reconciles the live set of pollers against the current bot list:

- Settings PUT/POST/DELETE on ``/settings/channels/bots`` clears the
  gateway-components cache and calls :meth:`reconcile`.
- :meth:`reconcile` diffs ``components.bots`` against ``self._pollers``
  and starts new ones / stops removed ones — no backend restart
  required.

Each poller's inbound callback is a per-bot closure that stamps
``bot_id`` onto the :class:`InboundMessage` before dispatching to the
gateway, so downstream routing knows which bot received the message
(see plan in ``docs/epics/multi-bot-channels.md`` §"Pairing modes
per bot").
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import structlog

from taskforce.core.domain.gateway import InboundMessage
from taskforce.core.interfaces.channel_ask import PendingChannelQuestionStoreProtocol
from taskforce.infrastructure.communication.telegram_poller import TelegramPoller

logger = structlog.get_logger(__name__)


# Type of the gateway-components provider — returns a fresh GatewayComponents
# on every call so the manager always sees the latest bot list.
ComponentsProvider = Callable[[], Any]

# Type of the gateway's message-handler entry point. We don't import the
# concrete class to avoid a layering cycle; the manager only needs to
# invoke ``handle_message(message)``.
GatewayLike = Any


class BotPollerManager:
    """Owns one TelegramPoller per enabled Telegram bot config."""

    def __init__(
        self,
        *,
        gateway: GatewayLike,
        components_provider: ComponentsProvider,
        pending_store: PendingChannelQuestionStoreProtocol,
    ) -> None:
        self._gateway = gateway
        self._components_provider = components_provider
        self._pending_store = pending_store
        self._pollers: dict[str, TelegramPoller] = {}
        # Lock serialises reconcile so two concurrent settings PUTs don't
        # race each other into half-started state.
        self._reconcile_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initial reconcile after startup — starts pollers for all enabled bots."""
        await self.reconcile()

    async def stop(self) -> None:
        """Stop every poller (called from the FastAPI lifespan teardown)."""
        async with self._reconcile_lock:
            await self._stop_all_unlocked()

    async def _stop_all_unlocked(self) -> None:
        for bot_id, poller in list(self._pollers.items()):
            try:
                await poller.stop()
            except Exception:  # noqa: BLE001 — bad poller mustn't block shutdown
                logger.warning("bot_poller.stop_failed", bot_id=bot_id, exc_info=True)
        self._pollers.clear()

    # ------------------------------------------------------------------
    # Reconcile
    # ------------------------------------------------------------------

    async def reconcile(self) -> dict[str, list[str]]:
        """Diff the current bot list against running pollers, start/stop.

        Returns a dict ``{"started": [bot_id, …], "stopped": [bot_id, …]}``
        for logging / route response so the UI can confirm the action
        actually took effect.
        """
        async with self._reconcile_lock:
            components = self._components_provider()
            target: dict[str, Any] = {}
            for bot in getattr(components, "bots", []) or []:
                if bot.channel_type != "telegram":
                    continue
                if not bot.enabled or not bot.bot_token:
                    continue
                target[bot.id] = bot

            running = set(self._pollers)
            wanted = set(target)

            stopped: list[str] = []
            started: list[str] = []

            # Stop removed / disabled bots
            for bot_id in running - wanted:
                try:
                    await self._pollers[bot_id].stop()
                    stopped.append(bot_id)
                    logger.info("bot_poller.reconcile.stopped", bot_id=bot_id)
                except Exception:  # noqa: BLE001
                    logger.warning("bot_poller.reconcile.stop_failed", bot_id=bot_id, exc_info=True)
                finally:
                    self._pollers.pop(bot_id, None)

            # Start newly added bots
            for bot_id in wanted - running:
                bot = target[bot_id]
                sender = None
                # Outbound sender may not exist yet if the components map hasn't
                # caught up; harmless — TelegramPoller treats it as optional.
                senders_map = getattr(components, "outbound_senders_by_bot_id", {}) or {}
                sender = senders_map.get(bot_id)

                poller = TelegramPoller(
                    bot_token=bot.bot_token,
                    pending_store=self._pending_store,
                    outbound_sender=sender,
                    recipient_registry=getattr(components, "recipient_registry", None),
                    inbound_message_handler=self._make_inbound_handler(bot_id),
                )
                try:
                    await poller.start()
                    self._pollers[bot_id] = poller
                    started.append(bot_id)
                    logger.info("bot_poller.reconcile.started", bot_id=bot_id)
                except Exception as exc:  # noqa: BLE001
                    # Bad token / network issue mustn't poison the reconcile loop.
                    logger.warning(
                        "bot_poller.reconcile.start_failed",
                        bot_id=bot_id,
                        error=str(exc),
                    )
                    # Drain the half-built poller's session, otherwise aiohttp
                    # whines about an unclosed connector at GC time.
                    try:
                        await poller.stop()
                    except Exception:  # noqa: BLE001
                        pass

            logger.info(
                "bot_poller.reconcile.done",
                started=started,
                stopped=stopped,
                running=sorted(self._pollers),
            )
            return {"started": started, "stopped": stopped}

    # ------------------------------------------------------------------
    # Status (for tests + /api/v1/admin/bot-pollers)
    # ------------------------------------------------------------------

    def running_bot_ids(self) -> list[str]:
        """Return the ids of currently running pollers (sorted)."""
        return sorted(self._pollers)

    # ------------------------------------------------------------------
    # Inbound handler factory
    # ------------------------------------------------------------------

    def _make_inbound_handler(self, bot_id: str):
        """Build the per-bot closure that TelegramPoller invokes for new messages.

        The closure tags every :class:`InboundMessage` with the receiving
        ``bot_id`` so the gateway can route by owner (implicit/paired/
        anonymous) — see ``docs/epics/multi-bot-channels.md``.
        """

        async def _handler(
            conversation_id: str,
            sender_id: str,
            text: str,
            attachments: list[dict[str, Any]] | None,
        ) -> None:
            metadata: dict[str, Any] = {}
            if attachments:
                metadata["attachments"] = attachments
            message = InboundMessage(
                channel="telegram",
                conversation_id=conversation_id,
                message=text,
                sender_id=sender_id,
                metadata=metadata,
                bot_id=bot_id,
            )
            try:
                await self._gateway.handle_message(message)
            except Exception:  # noqa: BLE001 — one bad turn must not kill the poller
                logger.warning(
                    "bot_poller.inbound_dispatch_failed",
                    bot_id=bot_id,
                    sender_id=sender_id,
                    exc_info=True,
                )

        return _handler


__all__ = ["BotPollerManager"]
