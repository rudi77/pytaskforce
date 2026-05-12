"""Tests for the channel-bot config domain model + legacy migration."""

from __future__ import annotations

import pytest

from taskforce.core.domain.settings import (
    BotConfig,
    BotOwnerKind,
    PairingMode,
    bots_to_section,
    parse_channels_section,
)


def test_bot_config_roundtrip() -> None:
    bot = BotConfig(
        id="rudi-butler",
        channel_type="telegram",
        bot_token="123:abc",
        owner_kind=BotOwnerKind.USER,
        owner_user_id="u1",
        default_agent="butler",
        pairing_mode=PairingMode.IMPLICIT,
        enabled=True,
    )
    assert BotConfig.from_dict(bot.to_dict()) == bot


def test_invalid_bot_id_rejected() -> None:
    for bad in ("Bad ID!", "x", "-leading", "ÄÖÜ", ""):
        with pytest.raises(ValueError):
            BotConfig.validate_id(bad)


def test_user_owned_requires_owner_user_id() -> None:
    with pytest.raises(ValueError):
        BotConfig.from_dict(
            {"id": "b1", "channel_type": "telegram", "owner_kind": "user"}
        )


def test_tenant_owner_clears_owner_user_id() -> None:
    bot = BotConfig.from_dict(
        {
            "id": "b1",
            "channel_type": "telegram",
            "owner_kind": "tenant",
            "owner_user_id": "stray-id-should-be-stripped",
        }
    )
    assert bot.owner_user_id is None


def test_pairing_mode_auto_default_for_user() -> None:
    bot = BotConfig.from_dict(
        {"id": "b1", "channel_type": "telegram", "owner_kind": "user", "owner_user_id": "u"}
    )
    assert bot.pairing_mode is PairingMode.IMPLICIT


def test_pairing_mode_auto_default_for_tenant() -> None:
    bot = BotConfig.from_dict(
        {"id": "b1", "channel_type": "telegram", "owner_kind": "tenant"}
    )
    assert bot.pairing_mode is PairingMode.PAIRED


def test_unknown_pairing_mode_falls_back_to_owner_default() -> None:
    bot = BotConfig.from_dict(
        {
            "id": "b1",
            "channel_type": "telegram",
            "owner_kind": "user",
            "owner_user_id": "u",
            "pairing_mode": "totally-bogus",
        }
    )
    assert bot.pairing_mode is PairingMode.IMPLICIT


def test_mask_token_short() -> None:
    bot = BotConfig(id="b1", channel_type="telegram", bot_token="short")
    masked = bot.mask_token()
    assert masked["bot_token"] == "…"
    assert bot.bot_token == "short"  # original unchanged


def test_mask_token_long() -> None:
    bot = BotConfig(id="b1", channel_type="telegram", bot_token="123456789012345")
    masked = bot.mask_token()
    assert masked["bot_token"] == "1234…2345"


def test_parse_legacy_telegram_shape() -> None:
    raw = {"telegram": {"bot_token": "old:token", "enabled": True}}
    bots = parse_channels_section(raw)
    assert len(bots) == 1
    assert bots[0].id == "legacy-telegram"
    assert bots[0].owner_kind is BotOwnerKind.TENANT
    assert bots[0].channel_type == "telegram"
    assert bots[0].bot_token == "old:token"


def test_parse_legacy_teams_shape() -> None:
    raw = {"teams": {"app_id": "x", "app_password": "y"}}
    bots = parse_channels_section(raw)
    assert len(bots) == 1
    assert bots[0].id == "legacy-teams"
    assert bots[0].channel_type == "teams"


def test_parse_new_shape() -> None:
    bot = BotConfig(
        id="b1",
        channel_type="telegram",
        bot_token="t",
        owner_kind=BotOwnerKind.USER,
        owner_user_id="u",
    )
    raw = bots_to_section([bot])
    parsed = parse_channels_section(raw)
    assert parsed == [bot]


def test_parse_skips_broken_rows() -> None:
    """One bad row shouldn't poison the whole section."""
    raw = {
        "bots": [
            {"id": "good", "channel_type": "telegram"},
            {"id": "BAD ID!", "channel_type": "telegram"},  # invalid id
            {"id": "also-good", "channel_type": "telegram"},
        ]
    }
    parsed = parse_channels_section(raw)
    ids = [b.id for b in parsed]
    assert ids == ["good", "also-good"]


def test_parse_empty_or_none() -> None:
    assert parse_channels_section(None) == []
    assert parse_channels_section({}) == []
    assert parse_channels_section({"bots": []}) == []
