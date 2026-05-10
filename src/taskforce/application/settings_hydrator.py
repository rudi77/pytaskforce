"""Hydrate runtime config from the settings store into environment / state.

The settings store holds the *user-supplied* values for things that other
parts of the framework consume via process-wide state (env vars, lazy-built
singletons). This module is the single seam that translates settings
sections into the right side-effects:

- ``hydrate_llm_providers_env`` writes ``OPENAI_API_KEY`` /
  ``ANTHROPIC_API_KEY`` / ``AZURE_API_*`` / ``GEMINI_API_KEY`` from
  ``settings["llm_providers"]`` so LiteLLM picks them up at next call.
- ``hydrate_channels_env`` writes ``TELEGRAM_BOT_TOKEN`` /
  ``TEAMS_APP_ID`` / ``TEAMS_APP_PASSWORD`` so the gateway registry
  picks them up on rebuild.

Hydration is idempotent and additive: it only sets a value when the
settings store has one, never clears env vars the operator set
externally. Settings *override* env vars when both are present
(otherwise the UI would be useless).

Callers:

- ``api/server.py`` lifespan — once at startup so the first request
  already sees the settings-store values.
- ``api/routes/settings.py`` — after every PUT/DELETE on the relevant
  section, so changes take effect without a restart.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from taskforce.core.domain.settings import CHANNELS, LLM_PROVIDERS

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------

#: Mapping of provider id (matches the settings section keys) to the env
#: variables the provider consumes. Each entry maps a settings field name
#: to the env var name that LiteLLM (or the provider SDK) reads.
_LLM_PROVIDER_ENV_MAP: dict[str, dict[str, str]] = {
    "openai": {"api_key": "OPENAI_API_KEY", "api_base": "OPENAI_API_BASE"},
    "anthropic": {"api_key": "ANTHROPIC_API_KEY"},
    "google": {"api_key": "GEMINI_API_KEY"},
    "azure": {
        "api_key": "AZURE_API_KEY",
        "api_base": "AZURE_API_BASE",
        "api_version": "AZURE_API_VERSION",
    },
    "ollama": {"api_base": "OLLAMA_API_BASE"},
}


def hydrate_llm_providers_env(store: Any) -> list[str]:
    """Apply the ``llm_providers`` settings section to ``os.environ``.

    Returns a list of env var names that were written, useful for logging.

    The settings section schema is provider-keyed::

        {
          "openai": {"api_key": "sk-..."},
          "anthropic": {"api_key": "sk-ant-..."},
          "azure": {"api_key": "...", "api_base": "https://...", "api_version": "2024-..."},
          ...
        }
    """
    section = store.get(LLM_PROVIDERS) or {}
    written: list[str] = []
    for provider, config in section.items():
        env_map = _LLM_PROVIDER_ENV_MAP.get(provider)
        if env_map is None or not isinstance(config, dict):
            continue
        for field_name, env_name in env_map.items():
            value = config.get(field_name)
            if value is None or value == "":
                continue
            os.environ[env_name] = str(value)
            written.append(env_name)
    if written:
        logger.info("settings.hydrate.llm_providers", env_keys=written)
    return written


# ---------------------------------------------------------------------------
# Communication channels
# ---------------------------------------------------------------------------

#: Mapping of channel id to env vars consumed by the gateway registry.
_CHANNEL_ENV_MAP: dict[str, dict[str, str]] = {
    "telegram": {"bot_token": "TELEGRAM_BOT_TOKEN"},
    "teams": {"app_id": "TEAMS_APP_ID", "app_password": "TEAMS_APP_PASSWORD"},
}


def hydrate_channels_env(store: Any) -> list[str]:
    """Apply the ``channels`` settings section to ``os.environ``.

    Returns a list of env var names that were written.
    """
    section = store.get(CHANNELS) or {}
    written: list[str] = []
    for channel, config in section.items():
        env_map = _CHANNEL_ENV_MAP.get(channel)
        if env_map is None or not isinstance(config, dict):
            continue
        if config.get("enabled") is False:
            continue
        for field_name, env_name in env_map.items():
            value = config.get(field_name)
            if value is None or value == "":
                continue
            os.environ[env_name] = str(value)
            written.append(env_name)
    if written:
        logger.info("settings.hydrate.channels", env_keys=written)
    return written


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def hydrate_all(store: Any) -> dict[str, list[str]]:
    """Apply every supported section. Returns a per-section summary."""
    return {
        "llm_providers": hydrate_llm_providers_env(store),
        "channels": hydrate_channels_env(store),
    }
