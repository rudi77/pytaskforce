"""Regression: ``build_gateway_components`` auto-reads bot configs.

Issue #231: when a plugin (e.g. ``taskforce-enterprise``) overrides
``gateway_components_for_current_tenant``, it calls
:func:`build_gateway_components` directly — without passing
``bot_configs``. The framework's bot-config-from-settings reading
must be inside ``build_gateway_components`` itself so this path
picks them up. Otherwise the multi-bot feature shipped in #228 is
silently disabled in any deployment that wraps the gateway builder.
"""

from __future__ import annotations

import pytest

from taskforce.core.domain.settings import (
    CHANNELS,
    BotConfig,
    BotOwnerKind,
    PairingMode,
    bots_to_section,
)
from taskforce.infrastructure.communication.gateway_registry import (
    build_gateway_components,
)
from taskforce.infrastructure.persistence.file_settings_store import (
    FileSettingsStore,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for v in ("TELEGRAM_BOT_TOKEN", "TEAMS_APP_ID", "TEAMS_APP_PASSWORD", "TASKFORCE_SECRETS_KEY"):
        monkeypatch.delenv(v, raising=False)


def _seed_bots(work_dir, bots: list[BotConfig]) -> None:
    """Write ``bots`` into the FileSettingsStore at ``work_dir``.

    Uses no explicit key so the store auto-generates one in
    ``<work_dir>/.secrets.key`` — the subsequent read inside
    ``build_gateway_components`` constructs a fresh FileSettingsStore
    at the same ``work_dir`` and picks up that same key file. Mimics
    the production flow.
    """
    store = FileSettingsStore(work_dir=work_dir)
    store.put(CHANNELS, bots_to_section(bots))


def test_auto_reads_bots_when_bot_configs_omitted(tmp_path):
    """Without an explicit bot_configs arg, the function reads them itself."""
    bot = BotConfig(
        id="rudi-butler",
        channel_type="telegram",
        bot_token="rudi-token",
        owner_kind=BotOwnerKind.USER,
        owner_user_id="u1",
        pairing_mode=PairingMode.IMPLICIT,
    )
    _seed_bots(tmp_path, [bot])

    components = build_gateway_components(work_dir=str(tmp_path))

    assert [b.id for b in components.bots] == ["rudi-butler"]
    assert "rudi-butler" in components.outbound_senders_by_bot_id


def test_explicit_empty_list_suppresses_auto_read(tmp_path):
    """An explicit ``bot_configs=[]`` skips the settings-store read.

    The empty-list path is how the legacy single-bot env-var fallback
    is tested without leaking the on-disk store contents.
    """
    _seed_bots(tmp_path, [
        BotConfig(id="should-be-ignored", channel_type="telegram", bot_token="x")
    ])

    components = build_gateway_components(work_dir=str(tmp_path), bot_configs=[])

    assert components.bots == []
    assert components.outbound_senders_by_bot_id == {}


def test_explicit_bot_configs_take_precedence(tmp_path):
    """If the caller passes a bot list, it wins over the store."""
    _seed_bots(tmp_path, [
        BotConfig(id="from-store", channel_type="telegram", bot_token="x")
    ])

    explicit = BotConfig(id="from-arg", channel_type="telegram", bot_token="y")
    components = build_gateway_components(
        work_dir=str(tmp_path),
        bot_configs=[explicit],
    )

    assert [b.id for b in components.bots] == ["from-arg"]


def test_missing_store_falls_back_silently(tmp_path):
    """An unreadable settings store doesn't break the gateway build."""
    # No settings.json.enc at all — should produce empty bots without raising.
    components = build_gateway_components(work_dir=str(tmp_path / "does-not-exist"))
    assert components.bots == []


def test_corrupt_store_falls_back_silently(tmp_path):
    """A corrupt settings document doesn't break the gateway build either."""
    (tmp_path / "settings.json.enc").write_bytes(b"not-valid-fernet")
    components = build_gateway_components(work_dir=str(tmp_path))
    assert components.bots == []
