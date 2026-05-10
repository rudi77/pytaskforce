"""Tests for AgentCreationPipeline foreign-runtime dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from taskforce.application import agent_runtime_registry as registry_mod
from taskforce.application.agent_creation_pipeline import AgentCreationPipeline
from taskforce.application.agent_runtime_registry import register_runtime
from taskforce.core.domain.errors import ValidationError


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot/restore registry state around each test."""
    snapshot = dict(registry_mod._runtimes)
    yield
    registry_mod._runtimes.clear()
    registry_mod._runtimes.update(snapshot)


def _make_factory(profile_dict: dict, *, create_agent_return="native_agent"):
    """Build a SimpleNamespace mock of AgentFactory for the pipeline."""
    profile_loader = SimpleNamespace(load=lambda name: dict(profile_dict))
    return SimpleNamespace(
        create_agent=AsyncMock(return_value=create_agent_return),
        profile_loader=profile_loader,
    )


@pytest.mark.asyncio
async def test_profile_without_runtime_uses_native_taskforce_path() -> None:
    factory = _make_factory({})  # no runtime field
    pipeline = AgentCreationPipeline(factory=factory)
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    result = await pipeline.create_agent(profile="dev")

    assert result == "native_agent"
    factory.create_agent.assert_awaited_once()
    # No foreign-runtime detour: the factory was called with config="dev"
    call_kwargs = factory.create_agent.await_args.kwargs
    assert call_kwargs.get("config") == "dev"


@pytest.mark.asyncio
async def test_profile_with_runtime_taskforce_uses_native_path() -> None:
    factory = _make_factory({"runtime": "taskforce"})
    pipeline = AgentCreationPipeline(factory=factory)
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    result = await pipeline.create_agent(profile="dev")

    assert result == "native_agent"
    factory.create_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_with_foreign_runtime_dispatches_to_registered_factory() -> None:
    captured: dict = {}

    async def hermes_factory(profile_dict):
        captured.update(profile_dict)
        return SimpleNamespace(runtime_name="hermes")

    register_runtime("hermes", hermes_factory)

    factory = _make_factory({"runtime": "hermes", "runtime_config": {"endpoint": "http://x"}})
    pipeline = AgentCreationPipeline(factory=factory)
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    result = await pipeline.create_agent(
        profile="hermes_default",
        user_context={"user_id": "u1"},
        planning_strategy="native_react",
        planning_strategy_params={"max_step_iterations": 2},
    )

    # Native factory must NOT be called when a foreign runtime is selected.
    factory.create_agent.assert_not_awaited()
    assert getattr(result, "runtime_name", None) == "hermes"

    # Pipeline must hand the resolved profile dict + metadata to the runtime.
    assert captured["__profile_name__"] == "hermes_default"
    assert captured["__user_context__"] == {"user_id": "u1"}
    assert captured["__planning_strategy__"] == "native_react"
    assert captured["__planning_strategy_params__"] == {"max_step_iterations": 2}
    assert captured["runtime"] == "hermes"
    assert captured["runtime_config"] == {"endpoint": "http://x"}


@pytest.mark.asyncio
async def test_profile_with_unknown_runtime_raises_validation_error() -> None:
    factory = _make_factory({"runtime": "nonexistent"})
    pipeline = AgentCreationPipeline(factory=factory)
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    with pytest.raises(ValidationError) as exc_info:
        await pipeline.create_agent(profile="bogus")

    assert "nonexistent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_runtime_name_stamped_when_adapter_omits_it() -> None:
    async def bare_factory(profile_dict):
        # No runtime_name attribute on the returned object.
        return SimpleNamespace()

    register_runtime("openclaw", bare_factory)

    factory = _make_factory({"runtime": "openclaw"})
    pipeline = AgentCreationPipeline(factory=factory)
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    result = await pipeline.create_agent(profile="oc_default")

    assert getattr(result, "runtime_name", None) == "openclaw"


@pytest.mark.asyncio
async def test_runtime_name_normalized_to_lowercase() -> None:
    captured = {}

    async def fake_factory(profile_dict):
        captured["called"] = True
        return SimpleNamespace()

    register_runtime("hermes", fake_factory)

    factory = _make_factory({"runtime": "Hermes"})  # mixed case in profile
    pipeline = AgentCreationPipeline(factory=factory)
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    result = await pipeline.create_agent(profile="hermes_default")

    assert captured.get("called") is True
    assert getattr(result, "runtime_name", None) == "hermes"
