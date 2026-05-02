from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from taskforce.application.agent_creation_pipeline import AgentCreationPipeline
from taskforce.core.domain.agent_models import CustomAgentDefinition
from taskforce.core.domain.errors import ConflictError, NotFoundError


@pytest.mark.asyncio
async def test_create_agent_with_environment_resolves_active_deployment() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)

    pipeline._build_agent_registry = lambda: SimpleNamespace(  # type: ignore[method-assign]
        get_active_deployment=lambda agent_id, environment: SimpleNamespace(
            version="1.2.3", status="active"
        )
    )
    pipeline._lookup_agent_definition = lambda agent_id: CustomAgentDefinition(  # type: ignore[method-assign]
        agent_id=agent_id,
        name="custom",
        description="d",
        system_prompt="s",
        tool_allowlist=["file_read"],
    )

    result = await pipeline.create_agent(profile="coding_agent", agent_id="reviewer", environment="prod")

    assert result == "agent"
    factory.create_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_agent_with_environment_falls_back_to_custom_agent() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)

    pipeline._build_agent_registry = lambda: SimpleNamespace(  # type: ignore[method-assign]
        get_active_deployment=lambda agent_id, environment: None
    )
    pipeline._lookup_agent_definition = lambda agent_id: CustomAgentDefinition(  # type: ignore[method-assign]
        agent_id=agent_id,
        name="custom",
        description="d",
        system_prompt="s",
        tool_allowlist=["file_read"],
    )

    result = await pipeline.create_agent(profile="coding_agent", agent_id="reviewer", environment="staging")

    assert result == "agent"


@pytest.mark.asyncio
async def test_create_agent_with_environment_raises_not_found_without_deployment_or_fallback() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)

    pipeline._build_agent_registry = lambda: SimpleNamespace(  # type: ignore[method-assign]
        get_active_deployment=lambda agent_id, environment: None
    )
    pipeline._lookup_agent_definition = lambda agent_id: None  # type: ignore[method-assign]

    with pytest.raises(NotFoundError):
        await pipeline.create_agent(profile="coding_agent", agent_id="missing", environment="prod")


@pytest.mark.asyncio
async def test_create_agent_with_environment_raises_conflict_for_inactive_deployment() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)

    pipeline._build_agent_registry = lambda: SimpleNamespace(  # type: ignore[method-assign]
        get_active_deployment=lambda agent_id, environment: SimpleNamespace(
            version="2.0.0", status="paused"
        )
    )

    with pytest.raises(ConflictError):
        await pipeline.create_agent(profile="coding_agent", agent_id="reviewer", environment="prod")
