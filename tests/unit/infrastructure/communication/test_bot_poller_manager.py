"""Unit tests for :class:`BotPollerManager`.

Pins the reconcile contract: adding a bot to the live components
provider's bot list starts a poller; removing it stops one;
disabling the same bot stops it; toggling re-runs work; and a single
failing poller doesn't poison the rest.

The tests substitute :class:`TelegramPoller` with a recording fake so
no real network calls or asyncio loop quirks leak in.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from taskforce.core.domain.settings import BotConfig, BotOwnerKind, PairingMode
from taskforce.infrastructure.communication.bot_poller_manager import BotPollerManager


class FakeGateway:
    def __init__(self) -> None:
        self.handled: list[Any] = []

    async def handle_message(self, message: Any) -> None:
        self.handled.append(message)


class FakePoller:
    """Stand-in for :class:`TelegramPoller`. Records start/stop calls."""

    instances: list["FakePoller"] = []

    def __init__(self, *, bot_token: str, **kwargs: Any) -> None:
        self.bot_token = bot_token
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        FakePoller.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class FailingPoller(FakePoller):
    async def start(self) -> None:
        await super().start()
        raise RuntimeError("bad token")


class FakeComponents:
    def __init__(self, bots: list[BotConfig]) -> None:
        self.bots = bots
        self.outbound_senders_by_bot_id: dict[str, Any] = {}
        self.recipient_registry = None


@pytest.fixture(autouse=True)
def _reset_fake_poller():
    FakePoller.instances.clear()
    yield
    FakePoller.instances.clear()


def _make_manager(bots: list[BotConfig], *, poller_cls=FakePoller, monkeypatch):
    monkeypatch.setattr(
        "taskforce.infrastructure.communication.bot_poller_manager.TelegramPoller",
        poller_cls,
    )
    components = FakeComponents(bots)
    manager = BotPollerManager(
        gateway=FakeGateway(),
        components_provider=lambda: components,
        pending_store=object(),
    )
    return manager, components


@pytest.mark.asyncio
async def test_reconcile_starts_pollers_for_enabled_bots(monkeypatch):
    bots = [
        BotConfig(id="rudi", channel_type="telegram", bot_token="t1", owner_kind=BotOwnerKind.USER, owner_user_id="u1"),
        BotConfig(id="support", channel_type="telegram", bot_token="t2", owner_kind=BotOwnerKind.TENANT),
    ]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)

    result = await manager.reconcile()

    assert sorted(result["started"]) == ["rudi", "support"]
    assert result["stopped"] == []
    assert manager.running_bot_ids() == ["rudi", "support"]
    assert all(p.started for p in FakePoller.instances)


@pytest.mark.asyncio
async def test_reconcile_skips_disabled_and_tokenless(monkeypatch):
    bots = [
        BotConfig(id="ok", channel_type="telegram", bot_token="t"),
        BotConfig(id="disabled", channel_type="telegram", bot_token="t", enabled=False),
        BotConfig(id="tokenless", channel_type="telegram", bot_token=""),
        BotConfig(id="teams", channel_type="teams", bot_token="t"),  # wrong channel
    ]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)
    result = await manager.reconcile()

    assert result["started"] == ["ok"]
    assert manager.running_bot_ids() == ["ok"]


@pytest.mark.asyncio
async def test_reconcile_stops_removed_bot(monkeypatch):
    bots = [BotConfig(id="b1", channel_type="telegram", bot_token="t1")]
    manager, components = _make_manager(bots, monkeypatch=monkeypatch)
    await manager.reconcile()
    assert manager.running_bot_ids() == ["b1"]

    # Remove the bot and reconcile again
    components.bots = []
    result = await manager.reconcile()

    assert result["stopped"] == ["b1"]
    assert manager.running_bot_ids() == []
    # The poller that was started must also have been stopped.
    assert FakePoller.instances[0].stopped


@pytest.mark.asyncio
async def test_reconcile_stops_disabled_bot(monkeypatch):
    bot = BotConfig(id="b1", channel_type="telegram", bot_token="t1")
    manager, components = _make_manager([bot], monkeypatch=monkeypatch)
    await manager.reconcile()

    components.bots = [
        BotConfig(id="b1", channel_type="telegram", bot_token="t1", enabled=False)
    ]
    result = await manager.reconcile()
    assert result["stopped"] == ["b1"]
    assert manager.running_bot_ids() == []


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(monkeypatch):
    bots = [BotConfig(id="b1", channel_type="telegram", bot_token="t1")]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)

    first = await manager.reconcile()
    second = await manager.reconcile()
    assert first["started"] == ["b1"]
    assert second == {"started": [], "stopped": []}
    # Only one poller instance should ever have been created.
    assert len(FakePoller.instances) == 1


@pytest.mark.asyncio
async def test_failing_poller_does_not_block_others(monkeypatch):
    """A poller whose start() raises (bad token / network) must not poison reconcile."""

    instances: list[Any] = []

    class MixedPoller(FakePoller):
        async def start(self) -> None:
            await super().start()
            instances.append(self)
            if self.bot_token == "bad":
                raise RuntimeError("bad token")

    bots = [
        BotConfig(id="ok", channel_type="telegram", bot_token="good"),
        BotConfig(id="bad", channel_type="telegram", bot_token="bad"),
    ]
    manager, _ = _make_manager(bots, poller_cls=MixedPoller, monkeypatch=monkeypatch)

    result = await manager.reconcile()
    assert "ok" in result["started"]
    assert "bad" not in result["started"]
    assert manager.running_bot_ids() == ["ok"]


@pytest.mark.asyncio
async def test_stop_cancels_all_pollers(monkeypatch):
    bots = [
        BotConfig(id="a", channel_type="telegram", bot_token="t"),
        BotConfig(id="b", channel_type="telegram", bot_token="t"),
    ]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)
    await manager.start()

    await manager.stop()
    assert manager.running_bot_ids() == []
    assert all(p.stopped for p in FakePoller.instances)


@pytest.mark.asyncio
async def test_inbound_handler_stamps_bot_id_on_message(monkeypatch):
    """The per-bot closure must tag InboundMessage.bot_id correctly."""
    bots = [BotConfig(id="rudi-bot", channel_type="telegram", bot_token="t")]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)
    await manager.reconcile()

    handler = FakePoller.instances[0].kwargs["inbound_message_handler"]
    await handler("chat-1", "user-7", "hello", None)

    assert len(manager._gateway.handled) == 1
    msg = manager._gateway.handled[0]
    assert msg.channel == "telegram"
    assert msg.conversation_id == "chat-1"
    assert msg.sender_id == "user-7"
    assert msg.message == "hello"
    assert msg.bot_id == "rudi-bot"


@pytest.mark.asyncio
async def test_inbound_handler_swallows_gateway_errors(monkeypatch):
    """A bad gateway dispatch must not break the poller loop."""
    bots = [BotConfig(id="rudi", channel_type="telegram", bot_token="t")]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)
    await manager.reconcile()

    async def boom(message: Any) -> None:
        raise RuntimeError("kaboom")

    manager._gateway.handle_message = boom  # type: ignore[assignment]
    handler = FakePoller.instances[0].kwargs["inbound_message_handler"]
    # Should NOT raise
    await handler("c", "s", "t", None)


@pytest.mark.asyncio
async def test_reconcile_lock_serialises_concurrent_calls(monkeypatch):
    """Two concurrent reconcile() calls must not race each other into half-state."""
    bots = [BotConfig(id="b1", channel_type="telegram", bot_token="t")]
    manager, _ = _make_manager(bots, monkeypatch=monkeypatch)

    await asyncio.gather(manager.reconcile(), manager.reconcile(), manager.reconcile())
    assert manager.running_bot_ids() == ["b1"]
    assert len(FakePoller.instances) == 1
