"""Gateway registry builder for communication channel adapters.

Creates and wires all channel components (inbound adapters, outbound senders,
conversation store, recipient registry) from environment configuration AND
the UI-managed settings store (multi-bot channel configs).

Per-bot map ("\\*_by_bot_id" fields on GatewayComponents) coexists with the
legacy channel-name-keyed maps so call sites that still resolve by channel
name keep working — they receive the *first* enabled bot of that channel
type as the implicit default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

from taskforce.core.domain.settings import BotConfig, BotOwnerKind
from taskforce.core.interfaces.gateway import (
    ConversationStoreProtocol,
    InboundAdapterProtocol,
    OutboundSenderProtocol,
    RecipientRegistryProtocol,
)
from taskforce.infrastructure.communication.gateway_conversation_store import (
    GatewayConversationStore,
)
from taskforce.infrastructure.communication.inbound_adapters import (
    TeamsInboundAdapter,
    TelegramInboundAdapter,
)
from taskforce.infrastructure.communication.outbound_senders import (
    TeamsOutboundSender,
    TelegramOutboundSender,
)
from taskforce.infrastructure.communication.recipient_registry import (
    FileRecipientRegistry,
)

_LEGACY_TELEGRAM_BOT_ID = "env:telegram"
_LEGACY_TEAMS_BOT_ID = "env:teams"


@dataclass
class GatewayComponents:
    """All wired components needed by CommunicationGateway.

    Attributes:
        conversation_store: Shared conversation persistence.
        recipient_registry: Push notification recipient persistence.
        outbound_senders: Channel name -> sender mapping (single-bot
            legacy view; multi-bot uses ``outbound_senders_by_bot_id``).
        inbound_adapters: Channel name -> adapter mapping (legacy view).
        outbound_senders_by_bot_id: ``bot_id -> sender`` for multi-bot
            deployments. Always populated; for the single-bot legacy
            path the bot_id is synthetic (``env:telegram``, etc.).
        inbound_adapters_by_bot_id: ``bot_id -> adapter`` for multi-bot.
        bots: All configured ``BotConfig`` entries (settings + legacy
            env-var-derived). Carries owner/pairing metadata the gateway
            needs to route inbound messages per bot.
    """

    conversation_store: ConversationStoreProtocol
    recipient_registry: RecipientRegistryProtocol
    outbound_senders: dict[str, OutboundSenderProtocol] = field(default_factory=dict)
    inbound_adapters: dict[str, InboundAdapterProtocol] = field(default_factory=dict)
    outbound_senders_by_bot_id: dict[str, OutboundSenderProtocol] = field(default_factory=dict)
    inbound_adapters_by_bot_id: dict[str, InboundAdapterProtocol] = field(default_factory=dict)
    bots: list[BotConfig] = field(default_factory=list)


def _build_sender_for_bot(bot: BotConfig) -> OutboundSenderProtocol | None:
    if bot.channel_type == "telegram" and bot.bot_token:
        return TelegramOutboundSender(bot.bot_token)
    if bot.channel_type == "teams" and bot.bot_token:
        # Teams stores app_id + app_password in a structured way; for now
        # bot_token holds the app_password and metadata sits in env vars.
        # A proper Teams multi-bot config is a follow-up.
        return None
    return None


def _build_adapter_for_bot(bot: BotConfig) -> InboundAdapterProtocol | None:
    if bot.channel_type == "telegram":
        return TelegramInboundAdapter(bot.bot_token or None)
    if bot.channel_type == "teams":
        return TeamsInboundAdapter()
    return None


def _load_bot_configs_from_settings(work_dir: str) -> list[BotConfig]:
    """Read ``CHANNELS.bots`` from the settings store rooted at ``work_dir``.

    Returns ``[]`` on any failure so the gateway-build path stays robust
    when the store is missing, locked, or corrupt — env-var fallback then
    takes over.
    """
    try:
        from taskforce.core.domain.settings import CHANNELS, parse_channels_section
        from taskforce.infrastructure.persistence.file_settings_store import (
            FileSettingsStore,
        )

        store = FileSettingsStore(work_dir=work_dir)
        return parse_channels_section(store.get(CHANNELS))
    except Exception:  # noqa: BLE001 — defensive: store unavailable shouldn't block gateway
        return []


def build_gateway_components(
    *,
    work_dir: str = ".taskforce",
    extra_senders: dict[str, OutboundSenderProtocol] | None = None,
    extra_adapters: dict[str, InboundAdapterProtocol] | None = None,
    bot_configs: list[BotConfig] | None = None,
) -> GatewayComponents:
    """Build all gateway infrastructure components.

    Bot configs come from two sources, merged:

    1. ``bot_configs`` argument — typically loaded from the settings
       store's ``channels.bots`` list by the caller. When ``None``, the
       function *auto-reads* from ``<work_dir>/settings.json.enc`` so
       callers that don't know about multi-bot config (notably plugin
       gateway-component overrides) still pick up the per-(tenant) bot
       list. Each enabled entry produces one inbound adapter + one
       outbound sender keyed by its ``id``.
    2. Legacy env vars (``TELEGRAM_BOT_TOKEN``, ``TEAMS_APP_ID`` /
       ``TEAMS_APP_PASSWORD``) — synthesized into a single tenant-owned
       paired bot with id ``env:<channel>`` when no equivalent bot
       config was supplied. Keeps single-bot deployments working
       without migration.

    The legacy channel-keyed maps (``outbound_senders``,
    ``inbound_adapters``) are populated with the *first* enabled bot of
    each channel type so call sites that still address by channel name
    pick up a sensible default.

    Args:
        work_dir: Base directory for file-based stores. When
            ``bot_configs is None``, also the directory the settings
            store is read from.
        extra_senders: Additional outbound senders to register
            (channel-name keyed; legacy injection point for tests).
        extra_adapters: Additional inbound adapters to register.
        bot_configs: Bot configs from the settings store. Pass
            ``None`` to let this function auto-read them; pass an
            empty list to suppress reading and run env-var only.

    Returns:
        Fully wired :class:`GatewayComponents`.
    """
    logger = structlog.get_logger()

    if bot_configs is None:
        bot_configs = _load_bot_configs_from_settings(work_dir)

    conversation_store = GatewayConversationStore(work_dir=work_dir)
    recipient_registry = FileRecipientRegistry(work_dir=work_dir)

    senders: dict[str, OutboundSenderProtocol] = dict(extra_senders or {})
    adapters: dict[str, InboundAdapterProtocol] = dict(extra_adapters or {})
    senders_by_bot: dict[str, OutboundSenderProtocol] = {}
    adapters_by_bot: dict[str, InboundAdapterProtocol] = {}
    bots: list[BotConfig] = []
    seen_channel_types: set[str] = set()

    # --- Settings-store bots first -----------------------------------
    for bot in bot_configs or []:
        if not bot.enabled:
            continue
        if bot.id in senders_by_bot or bot.id in adapters_by_bot:
            logger.warning("gateway.bot.duplicate_id_skipped", bot_id=bot.id)
            continue
        sender = _build_sender_for_bot(bot)
        adapter = _build_adapter_for_bot(bot)
        if sender is None and adapter is None:
            logger.warning(
                "gateway.bot.unsupported_channel_type",
                bot_id=bot.id,
                channel_type=bot.channel_type,
            )
            continue
        if sender is not None:
            senders_by_bot[bot.id] = sender
        if adapter is not None:
            adapters_by_bot[bot.id] = adapter
        bots.append(bot)
        # First enabled bot per channel_type becomes the legacy default.
        if bot.channel_type not in seen_channel_types:
            seen_channel_types.add(bot.channel_type)
            if sender is not None and bot.channel_type not in senders:
                senders[bot.channel_type] = sender
            if adapter is not None and bot.channel_type not in adapters:
                adapters[bot.channel_type] = adapter
            logger.info(
                "gateway.bot.configured",
                bot_id=bot.id,
                channel_type=bot.channel_type,
                owner_kind=bot.owner_kind.value,
                owner_user_id=bot.owner_user_id,
                pairing_mode=bot.pairing_mode.value,
            )

    # --- Telegram env-var fallback -----------------------------------
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token and "telegram" not in seen_channel_types:
        env_bot = BotConfig(
            id=_LEGACY_TELEGRAM_BOT_ID,
            channel_type="telegram",
            bot_token=telegram_token,
            owner_kind=BotOwnerKind.TENANT,
        )
        senders_by_bot[env_bot.id] = TelegramOutboundSender(telegram_token)
        adapters_by_bot[env_bot.id] = TelegramInboundAdapter(telegram_token)
        bots.append(env_bot)
        senders.setdefault("telegram", senders_by_bot[env_bot.id])
        adapters.setdefault("telegram", adapters_by_bot[env_bot.id])
        logger.info("gateway.telegram.legacy_env_configured")
    if "telegram" not in adapters:
        # No token at all — register a token-less stub adapter so the
        # webhook endpoint can still parse incoming payloads.
        adapters["telegram"] = TelegramInboundAdapter()

    # --- Teams env-var fallback --------------------------------------
    teams_app_id = os.getenv("TEAMS_APP_ID", "")
    teams_app_password = os.getenv("TEAMS_APP_PASSWORD", "")
    if teams_app_id and "teams" not in seen_channel_types:
        env_bot = BotConfig(
            id=_LEGACY_TEAMS_BOT_ID,
            channel_type="teams",
            bot_token=teams_app_password,
            owner_kind=BotOwnerKind.TENANT,
        )
        senders_by_bot[env_bot.id] = TeamsOutboundSender(teams_app_id, teams_app_password)
        bots.append(env_bot)
        senders.setdefault("teams", senders_by_bot[env_bot.id])
        logger.info("gateway.teams.legacy_env_configured")
    if "teams" not in adapters:
        adapters["teams"] = TeamsInboundAdapter()

    return GatewayComponents(
        conversation_store=conversation_store,
        recipient_registry=recipient_registry,
        outbound_senders=senders,
        inbound_adapters=adapters,
        outbound_senders_by_bot_id=senders_by_bot,
        inbound_adapters_by_bot_id=adapters_by_bot,
        bots=bots,
    )
