"""Unit tests for the channel-link registry (issue #162)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from taskforce.infrastructure.communication.channel_link_registry import (
    FileChannelLinkRegistry,
    InMemoryChannelLinkRegistry,
    _now_utc,
)


@pytest.fixture
def file_registry(tmp_path):
    return FileChannelLinkRegistry(work_dir=str(tmp_path))


@pytest.fixture
def memory_registry():
    return InMemoryChannelLinkRegistry()


@pytest.fixture(params=["file", "memory"])
def registry(request, tmp_path):
    """Parametrised fixture so every conformance test runs against both impls."""
    if request.param == "file":
        return FileChannelLinkRegistry(work_dir=str(tmp_path))
    return InMemoryChannelLinkRegistry()


async def test_create_pending_code_returns_numeric_six_digit_code(registry) -> None:
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="uid")
    assert code.channel == "telegram"
    assert code.tenant_id == "tid"
    assert code.user_id == "uid"
    assert code.code.isdigit()
    assert len(code.code) == 6
    assert code.expires_at > _now_utc()


async def test_consume_code_creates_link_and_invalidates_code(registry) -> None:
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="uid")
    link = await registry.consume_code(channel="telegram", code=code.code, sender_id="11111")
    assert link is not None
    assert link.sender_id == "11111"
    assert link.tenant_id == "tid"
    assert link.user_id == "uid"

    # Single-use: a replay must fail.
    replay = await registry.consume_code(channel="telegram", code=code.code, sender_id="11111")
    assert replay is None


async def test_consume_code_unknown_returns_none(registry) -> None:
    assert await registry.consume_code(channel="telegram", code="000000", sender_id="1") is None


async def test_consume_code_expired_returns_none(registry) -> None:
    code = await registry.create_pending_code(
        channel="telegram", tenant_id="tid", user_id="uid", ttl_seconds=60
    )
    # Reach into the registry's internal state and rewind the expiry.
    past = _now_utc() - timedelta(seconds=120)
    if isinstance(registry, FileChannelLinkRegistry):
        data = await registry._read("telegram")
        data["pending"][code.code]["expires_at"] = past.isoformat()
        await registry._write("telegram", data)
    else:
        registry._pending["telegram"][code.code]["expires_at"] = past

    assert await registry.consume_code(channel="telegram", code=code.code, sender_id="1") is None


async def test_consume_code_rejects_zero_ttl(registry) -> None:
    with pytest.raises(ValueError):
        await registry.create_pending_code(
            channel="telegram", tenant_id="t", user_id="u", ttl_seconds=0
        )


async def test_lookup_returns_existing_link(registry) -> None:
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="uid")
    await registry.consume_code(channel="telegram", code=code.code, sender_id="42")

    link = await registry.lookup(channel="telegram", sender_id="42")
    assert link is not None
    assert link.user_id == "uid"
    assert link.tenant_id == "tid"


async def test_lookup_unlinked_sender_returns_none(registry) -> None:
    assert await registry.lookup(channel="telegram", sender_id="missing") is None


async def test_remove_link_returns_true_then_false(registry) -> None:
    code = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="uid")
    await registry.consume_code(channel="telegram", code=code.code, sender_id="42")

    assert await registry.remove_link(channel="telegram", sender_id="42") is True
    assert await registry.remove_link(channel="telegram", sender_id="42") is False
    assert await registry.lookup(channel="telegram", sender_id="42") is None


async def test_list_links_filters_by_tenant_and_user(registry) -> None:
    c1 = await registry.create_pending_code(channel="telegram", tenant_id="tid-a", user_id="alice")
    c2 = await registry.create_pending_code(channel="telegram", tenant_id="tid-a", user_id="bob")
    c3 = await registry.create_pending_code(channel="teams", tenant_id="tid-b", user_id="alice")
    await registry.consume_code(channel="telegram", code=c1.code, sender_id="s-alice-tg")
    await registry.consume_code(channel="telegram", code=c2.code, sender_id="s-bob-tg")
    await registry.consume_code(channel="teams", code=c3.code, sender_id="s-alice-teams")

    by_tenant_a = await registry.list_links(tenant_id="tid-a")
    assert {link.user_id for link in by_tenant_a} == {"alice", "bob"}

    by_alice = await registry.list_links(user_id="alice")
    assert {link.channel for link in by_alice} == {"telegram", "teams"}

    by_alice_tenant_a = await registry.list_links(tenant_id="tid-a", user_id="alice")
    assert len(by_alice_tenant_a) == 1
    assert by_alice_tenant_a[0].channel == "telegram"


async def test_new_link_for_same_sender_overwrites(registry) -> None:
    c1 = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="alice")
    await registry.consume_code(channel="telegram", code=c1.code, sender_id="s")

    c2 = await registry.create_pending_code(channel="telegram", tenant_id="tid", user_id="bob")
    await registry.consume_code(channel="telegram", code=c2.code, sender_id="s")

    link = await registry.lookup(channel="telegram", sender_id="s")
    assert link is not None
    assert link.user_id == "bob"


async def test_file_registry_persists_across_instances(tmp_path) -> None:
    work_dir = str(tmp_path)
    first = FileChannelLinkRegistry(work_dir=work_dir)
    code = await first.create_pending_code(channel="telegram", tenant_id="tid", user_id="uid")
    await first.consume_code(channel="telegram", code=code.code, sender_id="42")

    # Fresh instance pointed at the same directory must see the link.
    second = FileChannelLinkRegistry(work_dir=work_dir)
    link = await second.lookup(channel="telegram", sender_id="42")
    assert link is not None
    assert link.user_id == "uid"
