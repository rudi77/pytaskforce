"""Settings domain — section names + value object.

The settings store keeps each kind of runtime config in its own JSON
section. The named constants here are the catalogue used by the UI
and the API; arbitrary names are also allowed (so plugins can store
their own config without core-side changes), but framework code
should reference these constants instead of string literals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
