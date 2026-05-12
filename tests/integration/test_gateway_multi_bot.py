"""Integration tests for multi-bot gateway component wiring.

Pins the contract between :func:`build_gateway_components` and the
settings-store bot list:

- N bot configs produce N inbound adapters + N outbound senders
  keyed by ``bot_id`` in the ``*_by_bot_id`` maps.
- The legacy channel-name-keyed maps still resolve a default per
  channel type, so call sites that haven't migrated yet keep
  working.
- Env-var legacy mode still works when no bot configs are supplied.
"""

from __future__ import annotations

import pytest

from taskforce.core.domain.settings import BotConfig, BotOwnerKind, PairingMode
from taskforce.infrastructure.communication.gateway_registry import (
    build_gateway_components,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for v in ("TELEGRAM_BOT_TOKEN", "TEAMS_APP_ID", "TEAMS_APP_PASSWORD"):
        monkeypatch.delenv(v, raising=False)


def test_empty_returns_no_bots(tmp_path):
    components = build_gateway_components(work_dir=str(tmp_path))
    assert components.bots == []
    assert components.outbound_senders_by_bot_id == {}
    # The token-less stub Telegram adapter is still registered so the
    # webhook route can parse incoming payloads.
    assert "telegram" in components.inbound_adapters


def test_legacy_env_telegram_synthesises_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env:fake-token")
    components = build_gateway_components(work_dir=str(tmp_path))

    assert len(components.bots) == 1
    legacy = components.bots[0]
    assert legacy.id == "env:telegram"
    assert legacy.channel_type == "telegram"
    assert legacy.owner_kind is BotOwnerKind.TENANT

    # Both maps wired
    assert "env:telegram" in components.outbound_senders_by_bot_id
    assert "env:telegram" in components.inbound_adapters_by_bot_id
    # Legacy view falls back to the same sender for "telegram"
    assert components.outbound_senders["telegram"] is components.outbound_senders_by_bot_id["env:telegram"]


def test_multiple_telegram_bots_each_get_own_sender(tmp_path):
    rudi = BotConfig(
        id="rudi-butler",
        channel_type="telegram",
        bot_token="rudi-token",
        owner_kind=BotOwnerKind.USER,
        owner_user_id="user-rudi",
        pairing_mode=PairingMode.IMPLICIT,
    )
    anna = BotConfig(
        id="anna-bot",
        channel_type="telegram",
        bot_token="anna-token",
        owner_kind=BotOwnerKind.USER,
        owner_user_id="user-anna",
        pairing_mode=PairingMode.IMPLICIT,
    )
    support = BotConfig(
        id="support",
        channel_type="telegram",
        bot_token="support-token",
        owner_kind=BotOwnerKind.TENANT,
        pairing_mode=PairingMode.PAIRED,
    )

    components = build_gateway_components(
        work_dir=str(tmp_path),
        bot_configs=[rudi, anna, support],
    )

    assert {b.id for b in components.bots} == {"rudi-butler", "anna-bot", "support"}
    assert set(components.outbound_senders_by_bot_id) == {"rudi-butler", "anna-bot", "support"}
    assert set(components.inbound_adapters_by_bot_id) == {"rudi-butler", "anna-bot", "support"}

    # First enabled bot of the channel becomes the legacy default
    assert components.outbound_senders["telegram"] is components.outbound_senders_by_bot_id["rudi-butler"]


def test_disabled_bot_not_wired(tmp_path):
    enabled = BotConfig(id="b1", channel_type="telegram", bot_token="t1")
    disabled = BotConfig(id="b2", channel_type="telegram", bot_token="t2", enabled=False)

    components = build_gateway_components(
        work_dir=str(tmp_path),
        bot_configs=[enabled, disabled],
    )
    assert {b.id for b in components.bots} == {"b1"}
    assert "b2" not in components.outbound_senders_by_bot_id


def test_duplicate_bot_id_skipped(tmp_path):
    a = BotConfig(id="dup", channel_type="telegram", bot_token="a")
    b = BotConfig(id="dup", channel_type="telegram", bot_token="b")

    components = build_gateway_components(
        work_dir=str(tmp_path),
        bot_configs=[a, b],
    )
    assert len(components.bots) == 1
    # First wins
    assert components.outbound_senders_by_bot_id["dup"] is not None


def test_unsupported_channel_type_skipped(tmp_path):
    weird = BotConfig(id="weird", channel_type="iridium-uplink", bot_token="x")
    valid = BotConfig(id="real", channel_type="telegram", bot_token="t")

    components = build_gateway_components(
        work_dir=str(tmp_path),
        bot_configs=[weird, valid],
    )
    ids = [b.id for b in components.bots]
    assert "weird" not in ids
    assert "real" in ids


def test_settings_and_env_dont_double_wire(tmp_path, monkeypatch):
    """When a settings-store Telegram bot is configured, the env-var
    legacy fallback must NOT register a competing bot of the same
    channel type. Otherwise users would get phantom env:telegram bots
    showing up alongside their real ones."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token-should-be-ignored")
    real = BotConfig(id="real", channel_type="telegram", bot_token="real-token")

    components = build_gateway_components(
        work_dir=str(tmp_path),
        bot_configs=[real],
    )
    bot_ids = [b.id for b in components.bots]
    assert bot_ids == ["real"]
    assert "env:telegram" not in components.outbound_senders_by_bot_id
