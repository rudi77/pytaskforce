"""Settings domain — section names + value objects.

The settings store keeps each kind of runtime config in its own JSON
section. The named constants here are the catalogue used by the UI
and the API; arbitrary names are also allowed (so plugins can store
their own config without core-side changes), but framework code
should reference these constants instead of string literals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Section names
# ---------------------------------------------------------------------------

#: API keys + endpoints for LLM providers (openai, anthropic, azure, …).
#: Schema is provider-keyed dict; each value contains at least ``api_key``.
LLM_PROVIDERS = "llm_providers"

#: Communication-channel credentials (Telegram bot token, Teams app id/secret, …).
#: Schema is channel-keyed dict; each value contains channel-specific fields.
CHANNELS = "channels"

#: OAuth connection metadata (Gmail / Google Calendar / Drive). Token bytes
#: stay in the existing :class:`TokenStoreProtocol`; this section stores only
#: connection metadata + last-refresh timestamps.
OAUTH = "oauth"

#: Default-agent / default-profile selection per channel (e.g. which agent
#: handles incoming Telegram chat). Schema: ``{"<channel>": "<agent_id>"}``.
DEFAULT_AGENT = "default_agent"

#: Visibility overrides / additions on top of the deployment manifest
#: (used by the upcoming UI editor — see Phase A's deployment.yaml).
VISIBLE_AGENTS = "visible_agents"


KNOWN_SECTIONS: frozenset[str] = frozenset(
    {LLM_PROVIDERS, CHANNELS, OAUTH, DEFAULT_AGENT, VISIBLE_AGENTS}
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingsSection:
    """Snapshot of a single settings section.

    Used by the API layer to expose section content + metadata. The
    store itself only deals with the inner ``data`` mapping; this
    wrapper attaches the section name and its last-modified timestamp.
    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Channel bot configs (multi-bot per channel type)
# ---------------------------------------------------------------------------


class BotOwnerKind(str, Enum):
    """Who owns a bot config.

    - ``TENANT`` — bot is shared across every user in the tenant. Tenant
      admins manage it. User-level routing happens via the
      ``ChannelLinkRegistry`` ``/link`` pairing flow when
      ``pairing_mode=PAIRED``.
    - ``USER`` — bot is private to a single user; only that user (or a
      tenant admin override) can edit it.
    """

    TENANT = "tenant"
    USER = "user"


class PairingMode(str, Enum):
    """How a bot resolves incoming messages to a user.

    - ``IMPLICIT`` — the bot is owned by a single user. Every inbound
      message is routed to that owner. No ``/link`` needed. Default for
      user-owned bots.
    - ``PAIRED`` — each incoming Telegram chat must run ``/link <code>``
      once to claim its ``user_id``. Until paired, messages are stored
      in a pending bucket / rejected. Default for tenant-owned bots.
    - ``ANONYMOUS`` — no per-user routing. All messages go to
      ``default_agent`` without user context. Use case: public FAQ /
      support intake where no user-specific data is accessed.
    """

    IMPLICIT = "implicit"
    PAIRED = "paired"
    ANONYMOUS = "anonymous"


_BOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


@dataclass(frozen=True)
class BotConfig:
    """A single channel-bot configuration.

    A tenant's ``CHANNELS`` settings section holds a list of these. The
    gateway-registry builds one inbound adapter per ``BotConfig`` (i.e.
    one polling loop per Telegram token), keyed by ``id``.

    Fields:
        id: Tenant-unique stable identifier. ``[a-z0-9][a-z0-9_-]{1,63}``.
        channel_type: ``telegram`` / ``teams`` / ``slack`` / future channels.
        bot_token: Channel-specific credential. Telegram: bot API token.
            Teams: not used (Teams uses ``app_id`` + ``app_password``).
        owner_kind: ``tenant`` or ``user``.
        owner_user_id: When ``owner_kind=USER``, the owning user's id.
            ``None`` for tenant-owned bots.
        default_agent: Which agent answers messages on this bot when no
            explicit ``@agent`` prefix is used. Falls back to the
            tenant's default agent when empty.
        pairing_mode: See :class:`PairingMode`.
        enabled: If False, the gateway skips this bot (no polling loop).
    """

    id: str
    channel_type: str
    bot_token: str = ""
    owner_kind: BotOwnerKind = BotOwnerKind.TENANT
    owner_user_id: str | None = None
    default_agent: str | None = None
    pairing_mode: PairingMode = PairingMode.PAIRED
    enabled: bool = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_id(bot_id: str) -> None:
        """Raise ValueError when ``bot_id`` is not a safe slug."""
        if not isinstance(bot_id, str) or not _BOT_ID_RE.match(bot_id):
            raise ValueError(
                f"Invalid bot id {bot_id!r}: must match {_BOT_ID_RE.pattern} "
                "(lowercase, digits, underscore, hyphen; 2–64 chars)."
            )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BotConfig:
        """Parse a dict (from settings store) into a typed BotConfig.

        Defensive parser: unknown ``owner_kind`` / ``pairing_mode``
        values fall back to safe defaults rather than crashing the
        whole store. The legacy auto-pairing rule (USER → IMPLICIT,
        TENANT → PAIRED) only fires when ``pairing_mode`` is missing
        from the source dict.
        """
        bot_id = str(raw.get("id", "")).strip()
        cls.validate_id(bot_id)

        try:
            owner_kind = BotOwnerKind(raw.get("owner_kind", BotOwnerKind.TENANT.value))
        except ValueError:
            owner_kind = BotOwnerKind.TENANT

        owner_user_id = raw.get("owner_user_id")
        if owner_kind is BotOwnerKind.USER and not owner_user_id:
            raise ValueError(
                f"Bot {bot_id!r}: owner_kind=user requires non-empty owner_user_id"
            )
        if owner_kind is BotOwnerKind.TENANT:
            owner_user_id = None

        if "pairing_mode" in raw:
            try:
                pairing_mode = PairingMode(raw["pairing_mode"])
            except ValueError:
                pairing_mode = (
                    PairingMode.IMPLICIT
                    if owner_kind is BotOwnerKind.USER
                    else PairingMode.PAIRED
                )
        else:
            pairing_mode = (
                PairingMode.IMPLICIT
                if owner_kind is BotOwnerKind.USER
                else PairingMode.PAIRED
            )

        return cls(
            id=bot_id,
            channel_type=str(raw.get("channel_type", "")).strip(),
            bot_token=str(raw.get("bot_token", "")),
            owner_kind=owner_kind,
            owner_user_id=str(owner_user_id) if owner_user_id else None,
            default_agent=(
                str(raw["default_agent"]).strip()
                if raw.get("default_agent")
                else None
            ),
            pairing_mode=pairing_mode,
            enabled=bool(raw.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the dict shape stored in the settings store."""
        return {
            "id": self.id,
            "channel_type": self.channel_type,
            "bot_token": self.bot_token,
            "owner_kind": self.owner_kind.value,
            "owner_user_id": self.owner_user_id,
            "default_agent": self.default_agent,
            "pairing_mode": self.pairing_mode.value,
            "enabled": self.enabled,
        }

    def mask_token(self) -> dict[str, Any]:
        """Return ``to_dict()`` with the secret token masked.

        Used by the REST list endpoint when the caller is not the bot's
        owner (e.g. a tenant admin viewing a user's personal bot).
        """
        payload = self.to_dict()
        token = self.bot_token or ""
        if len(token) > 8:
            payload["bot_token"] = f"{token[:4]}…{token[-4:]}"
        elif token:
            payload["bot_token"] = "…"
        return payload


def parse_channels_section(raw: dict[str, Any] | None) -> list[BotConfig]:
    """Parse a settings-store ``CHANNELS`` section into ``BotConfig``s.

    Accepts both the new shape (``{"bots": [{...}, ...]}``) and the
    legacy flat shape (``{"telegram": {"bot_token": "..."}}``) so a
    deployment upgraded from before this feature keeps reading
    correctly without manual migration. Legacy entries surface as a
    single tenant-owned, paired bot per channel type with a
    deterministic id like ``legacy-telegram``.
    """
    raw = raw or {}
    bots_raw = raw.get("bots")
    if isinstance(bots_raw, list):
        # New shape — parse each entry, skip rows that fail to validate
        # so one broken row doesn't poison the whole section.
        result: list[BotConfig] = []
        for item in bots_raw:
            if not isinstance(item, dict):
                continue
            try:
                result.append(BotConfig.from_dict(item))
            except ValueError:
                continue
        return result

    # Legacy fallback: keys ``telegram``, ``teams``, … each holding a
    # single config dict. Synthesize one tenant-owned bot per key.
    legacy: list[BotConfig] = []
    for channel_type, cfg in raw.items():
        if channel_type == "bots" or not isinstance(cfg, dict):
            continue
        token = cfg.get("bot_token") or cfg.get("app_password") or ""
        if not token and not cfg.get("app_id"):
            continue
        legacy_id = f"legacy-{channel_type}"
        try:
            BotConfig.validate_id(legacy_id)
        except ValueError:
            continue
        legacy.append(
            BotConfig(
                id=legacy_id,
                channel_type=channel_type,
                bot_token=str(token),
                owner_kind=BotOwnerKind.TENANT,
                owner_user_id=None,
                default_agent=None,
                pairing_mode=PairingMode.PAIRED,
                enabled=bool(cfg.get("enabled", True)),
            )
        )
    return legacy


def bots_to_section(bots: list[BotConfig]) -> dict[str, Any]:
    """Serialize a list of bots back into the ``CHANNELS`` section shape."""
    return {"bots": [b.to_dict() for b in bots]}
