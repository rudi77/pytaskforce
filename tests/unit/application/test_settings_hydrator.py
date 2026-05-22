"""Tests for the settings-store → env hydrator."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from taskforce.application.settings_hydrator import (
    hydrate_all,
    hydrate_channels_env,
    hydrate_llm_providers_env,
)
from taskforce.core.domain.settings import CHANNELS, LLM_PROVIDERS
from taskforce.infrastructure.persistence.file_settings_store import (
    FileSettingsStore,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip settings-managed env vars so each test starts clean."""
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_API_KEY",
        "AZURE_API_BASE",
        "AZURE_API_VERSION",
        "OLLAMA_API_BASE",
        "TELEGRAM_BOT_TOKEN",
        "TEAMS_APP_ID",
        "TEAMS_APP_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def _store(tmp_path):
    return FileSettingsStore(work_dir=tmp_path, key=Fernet.generate_key())


@pytest.mark.spec("settings-store.put_llm_providers_hydrates_env")
def test_hydrate_llm_providers_writes_env(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    store.put(
        LLM_PROVIDERS,
        {
            "openai": {"api_key": "sk-openai"},
            "anthropic": {"api_key": "sk-ant"},
            "azure": {
                "api_key": "az-key",
                "api_base": "https://az.example.com/",
                "api_version": "2024-12-01",
            },
        },
    )

    written = hydrate_llm_providers_env(store)

    assert "OPENAI_API_KEY" in written
    assert "ANTHROPIC_API_KEY" in written
    assert {"AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"}.issubset(set(written))

    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-openai"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant"
    assert os.environ["AZURE_API_BASE"] == "https://az.example.com/"


def test_hydrate_skips_blank_values(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(LLM_PROVIDERS, {"openai": {"api_key": ""}})

    assert hydrate_llm_providers_env(store) == []
    import os

    assert "OPENAI_API_KEY" not in os.environ


@pytest.mark.spec("settings-store.hydration_does_not_clear_external_env_vars")
def test_hydration_does_not_clear_external_env_vars(tmp_path, monkeypatch) -> None:
    """Hydration is additive — an externally-set env var is never cleared
    just because the settings store has no value for it."""
    import os

    # Operator sets a key directly in the environment …
    monkeypatch.setenv("OPENAI_API_KEY", "externally-set-key")

    # … and the settings store has no openai section at all.
    store = _store(tmp_path)
    store.put(LLM_PROVIDERS, {"anthropic": {"api_key": "sk-ant"}})

    hydrate_llm_providers_env(store)

    # The externally-set var survives; the store value is layered on top.
    assert os.environ["OPENAI_API_KEY"] == "externally-set-key"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant"


def test_hydrate_unknown_provider_is_ignored(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(LLM_PROVIDERS, {"madeup": {"api_key": "x"}, "openai": {"api_key": "ok"}})

    written = hydrate_llm_providers_env(store)
    assert written == ["OPENAI_API_KEY"]


def test_hydrate_channels_writes_env(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(
        CHANNELS,
        {
            "telegram": {"bot_token": "tg-token", "enabled": True},
            "teams": {"app_id": "app-id", "app_password": "app-pw"},
        },
    )

    written = hydrate_channels_env(store)

    import os

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "tg-token"
    assert os.environ["TEAMS_APP_ID"] == "app-id"
    assert os.environ["TEAMS_APP_PASSWORD"] == "app-pw"
    assert {"TELEGRAM_BOT_TOKEN", "TEAMS_APP_ID", "TEAMS_APP_PASSWORD"}.issubset(set(written))


def test_disabled_channel_is_skipped(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(
        CHANNELS,
        {"telegram": {"bot_token": "tg-token", "enabled": False}},
    )
    assert hydrate_channels_env(store) == []
    import os

    assert "TELEGRAM_BOT_TOKEN" not in os.environ


@pytest.mark.spec("api.settings_hydration_runs_before_first_request")
def test_hydrate_all_runs_both_sections(tmp_path) -> None:
    store = _store(tmp_path)
    store.put(LLM_PROVIDERS, {"openai": {"api_key": "k"}})
    store.put(CHANNELS, {"telegram": {"bot_token": "t"}})

    summary = hydrate_all(store)
    assert "OPENAI_API_KEY" in summary["llm_providers"]
    assert "TELEGRAM_BOT_TOKEN" in summary["channels"]
