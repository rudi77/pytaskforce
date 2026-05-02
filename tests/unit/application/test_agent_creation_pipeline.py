"""Tests for ``AgentCreationPipeline._resolve_deployment_context``."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from taskforce.application.agent_creation_pipeline import AgentCreationPipeline
from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)
from taskforce.core.domain.agent_models import CustomAgentDefinition
from taskforce.core.domain.errors import ConflictError, NotFoundError


def _custom_agent(agent_id: str = "reviewer") -> CustomAgentDefinition:
    return CustomAgentDefinition(
        agent_id=agent_id,
        name="custom",
        description="d",
        system_prompt="s",
        tool_allowlist=["file_read"],
    )


def _deployment(
    version: str, *, status: AgentDeploymentStatus = AgentDeploymentStatus.DEPLOYED
) -> AgentDeployment:
    return AgentDeployment(
        agent_id="reviewer",
        version=version,
        status=status,
        environment=DeploymentEnvironment.PROD,
        deployed_at=datetime.now(timezone.utc),
    )


def _patch_pipeline(pipeline: AgentCreationPipeline, *, active=None, agent=None) -> None:
    pipeline._build_deployment_registry = lambda: SimpleNamespace(  # type: ignore[method-assign]
        get_active=lambda agent_id, environment: active,
    )
    pipeline._lookup_agent_definition = lambda agent_id: agent  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_create_agent_with_environment_resolves_active_deployment() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)
    _patch_pipeline(pipeline, active=_deployment("1.2.3"), agent=_custom_agent())

    result = await pipeline.create_agent(
        profile="coding_agent", agent_id="reviewer", environment="prod"
    )

    assert result == "agent"
    factory.create_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_agent_with_environment_falls_back_to_custom_agent() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)
    _patch_pipeline(pipeline, active=None, agent=_custom_agent())

    result = await pipeline.create_agent(
        profile="coding_agent", agent_id="reviewer", environment="staging"
    )

    assert result == "agent"


@pytest.mark.asyncio
async def test_create_agent_with_environment_raises_not_found_without_deployment_or_fallback() -> (
    None
):
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)
    _patch_pipeline(pipeline, active=None, agent=None)

    with pytest.raises(NotFoundError):
        await pipeline.create_agent(profile="coding_agent", agent_id="missing", environment="prod")


@pytest.mark.asyncio
async def test_create_agent_with_environment_raises_conflict_for_inactive_deployment() -> None:
    factory = SimpleNamespace(create_agent=AsyncMock(return_value="agent"))
    pipeline = AgentCreationPipeline(factory=factory)
    _patch_pipeline(
        pipeline,
        active=_deployment("2.0.0", status=AgentDeploymentStatus.ROLLED_BACK),
        agent=_custom_agent(),
    )

    with pytest.raises(ConflictError):
        await pipeline.create_agent(profile="coding_agent", agent_id="reviewer", environment="prod")
