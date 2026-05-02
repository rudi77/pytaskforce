"""Tests for FileAgentDeploymentRegistry."""

from datetime import datetime, timezone

import pytest

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)
from taskforce.infrastructure.persistence.file_agent_deployment_registry import (
    FileAgentDeploymentRegistry,
)


def _make_deployment(
    *,
    agent_id: str = "agent-a",
    version: str = "1",
    status: AgentDeploymentStatus = AgentDeploymentStatus.DEPLOYED,
    environment: DeploymentEnvironment = DeploymentEnvironment.LOCAL,
    deployed_at: datetime | None = None,
    **extra,
) -> AgentDeployment:
    return AgentDeployment(
        agent_id=agent_id,
        version=version,
        status=status,
        environment=environment,
        deployed_at=deployed_at or datetime.now(timezone.utc),
        **extra,
    )


@pytest.fixture
def registry(tmp_path):
    return FileAgentDeploymentRegistry(work_dir=tmp_path / ".taskforce")


def test_record_deployed_updates_active_pointer(registry, tmp_path):
    deployment = _make_deployment(version="1")
    registry.record(deployment)

    active = registry.get_active("agent-a", DeploymentEnvironment.LOCAL)
    assert active is not None
    assert active.version == "1"
    assert active.status is AgentDeploymentStatus.DEPLOYED

    pointer = tmp_path / ".taskforce" / "deployments" / "agent-a" / "active" / "local.yaml"
    assert pointer.exists()


def test_record_failed_does_not_update_active(registry):
    failed = _make_deployment(status=AgentDeploymentStatus.FAILED, error="boom")
    registry.record(failed)
    assert registry.get_active("agent-a") is None


def test_record_rolled_back_clears_active_pointer(registry):
    registry.record(_make_deployment(version="1"))
    assert registry.is_deployed("agent-a")

    registry.record(_make_deployment(version="1", status=AgentDeploymentStatus.ROLLED_BACK))
    assert registry.get_active("agent-a") is None


def test_history_returns_records_newest_first(registry):
    registry.record(_make_deployment(version="1"))
    registry.record(_make_deployment(version="2"))
    registry.record(_make_deployment(version="3"))

    history = registry.list_for_agent("agent-a")
    assert [d.version for d in history] == ["3", "2", "1"]


def test_environments_are_isolated(registry):
    registry.record(_make_deployment(version="1", environment=DeploymentEnvironment.LOCAL))
    registry.record(_make_deployment(version="2", environment=DeploymentEnvironment.STAGING))

    local = registry.get_active("agent-a", DeploymentEnvironment.LOCAL)
    staging = registry.get_active("agent-a", DeploymentEnvironment.STAGING)
    assert local and local.version == "1"
    assert staging and staging.version == "2"


def test_environment_string_is_coerced(registry):
    registry.record(_make_deployment(version="1"))
    assert registry.is_deployed("agent-a", "local")
    assert not registry.is_deployed("agent-a", "staging")


def test_unknown_agent_returns_empty(registry):
    assert registry.list_for_agent("unknown") == []
    assert registry.get_active("unknown") is None
    assert not registry.is_deployed("unknown")
