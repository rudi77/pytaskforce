"""Tests for the agent runtime registry."""

from __future__ import annotations

import pytest

from taskforce.application import agent_runtime_registry as registry_mod
from taskforce.application.agent_runtime_registry import (
    DEFAULT_RUNTIME,
    clear_runtimes,
    get_runtime,
    is_registered,
    list_runtimes,
    register_runtime,
    unregister_runtime,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot/restore registry state around each test."""
    snapshot = dict(registry_mod._runtimes)
    yield
    registry_mod._runtimes.clear()
    registry_mod._runtimes.update(snapshot)


def test_default_taskforce_runtime_is_registered_at_import() -> None:
    assert DEFAULT_RUNTIME == "taskforce"
    assert is_registered("taskforce")
    assert "taskforce" in list_runtimes()


def test_register_runtime_adds_factory() -> None:
    async def fake_factory(profile_dict):  # noqa: ANN001 - test stub
        return object()

    register_runtime("hermes", fake_factory)

    assert is_registered("hermes")
    assert get_runtime("hermes") is fake_factory


def test_register_runtime_normalizes_name() -> None:
    async def fake_factory(profile_dict):  # noqa: ANN001
        return object()

    register_runtime("  HermesAdapter  ", fake_factory)

    assert is_registered("hermesadapter")
    assert get_runtime("HERMESADAPTER") is fake_factory


def test_register_runtime_rejects_empty_name() -> None:
    async def fake_factory(profile_dict):  # noqa: ANN001
        return object()

    with pytest.raises(ValueError):
        register_runtime("", fake_factory)
    with pytest.raises(ValueError):
        register_runtime("   ", fake_factory)


def test_get_runtime_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError) as exc_info:
        get_runtime("does_not_exist")
    # Error message should hint at available runtimes for usability.
    assert "does_not_exist" in str(exc_info.value)
    assert "taskforce" in str(exc_info.value)


def test_register_runtime_overwrite_logs_but_succeeds() -> None:
    async def first(profile_dict):  # noqa: ANN001
        return "first"

    async def second(profile_dict):  # noqa: ANN001
        return "second"

    register_runtime("dup", first)
    register_runtime("dup", second)

    assert get_runtime("dup") is second


def test_unregister_and_clear() -> None:
    async def fake_factory(profile_dict):  # noqa: ANN001
        return object()

    register_runtime("temp", fake_factory)
    assert is_registered("temp")

    unregister_runtime("temp")
    assert not is_registered("temp")

    register_runtime("a", fake_factory)
    register_runtime("b", fake_factory)
    clear_runtimes()
    assert list_runtimes() == []


def test_list_runtimes_returns_sorted_names() -> None:
    clear_runtimes()

    async def fake_factory(profile_dict):  # noqa: ANN001
        return object()

    register_runtime("zeta", fake_factory)
    register_runtime("alpha", fake_factory)
    register_runtime("mu", fake_factory)

    assert list_runtimes() == ["alpha", "mu", "zeta"]
