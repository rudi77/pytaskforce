"""Tests for AgentDeploymentService — the deploy lifecycle entry point."""

from __future__ import annotations

import pytest

from taskforce.application.agent_deployment_service import (
    AgentDeploymentService,
    DeploymentPreflightError,
)
from taskforce.core.domain.agent_deployment import (
    AgentDeploymentStatus,
    DeploymentEnvironment,
)
from taskforce.core.domain.agent_models import CustomAgentDefinition, ProfileAgentDefinition
from taskforce.infrastructure.persistence.file_agent_deployment_registry import (
    FileAgentDeploymentRegistry,
)


# --- helpers ---------------------------------------------------------------


class _Agents:
    """Tiny fake agent registry holding one agent at a time.

    Mutable on purpose: tests can call ``set(agent)`` to simulate
    edits to the agent definition between deploys without poking the
    ``AgentDeploymentService`` internals.
    """

    def __init__(self, agent: object | None) -> None:
        self._agent = agent

    def set(self, agent: object | None) -> None:
        self._agent = agent

    def get_agent(self, agent_id: str):
        if self._agent is None:
            return None
        return self._agent if getattr(self._agent, "agent_id", None) == agent_id else None


class _Tools:
    """Tool-catalog stub honouring an explicit allowlist."""

    def __init__(self, known: set[str] | None = None) -> None:
        self._known = known or {"python", "file_read"}

    def validate_native_tools(self, names):
        invalid = [n for n in names if n not in self._known]
        return (not invalid, invalid)

    def get_native_tool_names(self):
        return list(self._known)


def _custom_agent(**overrides) -> CustomAgentDefinition:
    defaults = dict(
        agent_id="writer",
        name="Writer",
        description="A writer",
        system_prompt="You write things.",
        tool_allowlist=["python"],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-02-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return CustomAgentDefinition(**defaults)


@pytest.fixture
def deployment_registry(tmp_path):
    return FileAgentDeploymentRegistry(work_dir=tmp_path / ".taskforce")


@pytest.fixture
def service_factory(deployment_registry):
    """Build a service plus the underlying ``_Agents`` stub.

    Returning the stub lets tests advance the agent definition between
    deploys without touching service internals.
    """

    def _make(agent=None, tools=None) -> tuple[AgentDeploymentService, _Agents]:
        agents = _Agents(agent)
        service = AgentDeploymentService(
            agent_registry=agents,
            deployment_registry=deployment_registry,
            tool_catalog=tools or _Tools(),
        )
        return service, agents

    return _make


# --- deploy ----------------------------------------------------------------


def test_deploy_records_active_deployment(service_factory):
    service, _ = service_factory(agent=_custom_agent())

    result = service.deploy("writer", deployed_by="alice", message="initial")

    assert result.status is AgentDeploymentStatus.DEPLOYED
    assert result.environment is DeploymentEnvironment.LOCAL
    assert result.version == "2025-02-01T00:00:00+00:00"
    assert result.deployed_by == "alice"
    assert result.message == "initial"
    assert result.deployed_at is not None
    assert service.is_deployed("writer")


def test_deploy_includes_config_snapshot(service_factory):
    service, _ = service_factory(agent=_custom_agent())

    result = service.deploy("writer")

    assert result.config_snapshot["system_prompt"] == "You write things."
    assert result.config_snapshot["tool_allowlist"] == ["python"]


def test_deploy_unknown_agent_raises_preflight(service_factory):
    service, _ = service_factory(agent=None)

    with pytest.raises(DeploymentPreflightError) as excinfo:
        service.deploy("missing")
    assert excinfo.value.code == "agent_not_found"


def test_deploy_profile_agent_rejected(deployment_registry):
    class _ProfileLookup:
        def get_agent(self, agent_id):
            return ProfileAgentDefinition(profile=agent_id)

    service = AgentDeploymentService(
        agent_registry=_ProfileLookup(),
        deployment_registry=deployment_registry,
        tool_catalog=_Tools(),
    )

    with pytest.raises(DeploymentPreflightError) as excinfo:
        service.deploy("dev")
    assert excinfo.value.code == "agent_not_custom"


def test_deploy_with_invalid_tools_persists_failed_record(service_factory):
    service, _ = service_factory(
        agent=_custom_agent(tool_allowlist=["bogus_tool"]),
        tools=_Tools(known={"python"}),
    )

    with pytest.raises(DeploymentPreflightError) as excinfo:
        service.deploy("writer")
    assert excinfo.value.code == "invalid_tools"
    assert excinfo.value.details["invalid_tools"] == ["bogus_tool"]

    history = service.list_history("writer")
    assert len(history) == 1
    assert history[0].status is AgentDeploymentStatus.FAILED
    assert history[0].error
    assert not service.is_deployed("writer")


def test_deploy_empty_system_prompt_rejected(service_factory):
    service, _ = service_factory(agent=_custom_agent(system_prompt="   "))

    with pytest.raises(DeploymentPreflightError) as excinfo:
        service.deploy("writer")
    assert excinfo.value.code == "invalid_agent_config"


def test_deploy_environment_argument_accepts_string(service_factory):
    service, _ = service_factory(agent=_custom_agent())

    result = service.deploy("writer", environment="staging")

    assert result.environment is DeploymentEnvironment.STAGING
    assert service.is_deployed("writer", "staging")
    assert not service.is_deployed("writer", DeploymentEnvironment.LOCAL)


# --- rollback --------------------------------------------------------------


def test_rollback_to_known_version_re_activates_it(service_factory):
    service, agents = service_factory(agent=_custom_agent(updated_at="v1"))
    service.deploy("writer")

    # Advance the agent definition and deploy again so v2 becomes active.
    agents.set(_custom_agent(updated_at="v2"))
    service.deploy("writer")
    assert service.get_active("writer").version == "v2"

    result = service.rollback("writer", to_version="v1", deployed_by="ops")

    assert result.status is AgentDeploymentStatus.DEPLOYED
    assert result.version == "v1"
    assert result.deployed_by == "ops"
    active = service.get_active("writer")
    assert active is not None
    assert active.version == "v1"


def test_rollback_writes_audit_record_for_previous_version(service_factory):
    """The version that was active before the rollback must get a ROLLED_BACK row."""
    service, agents = service_factory(agent=_custom_agent(updated_at="v1"))
    service.deploy("writer")
    agents.set(_custom_agent(updated_at="v2"))
    service.deploy("writer")

    service.rollback("writer", to_version="v1")

    history = service.list_history("writer")
    rolled_back = [d for d in history if d.status is AgentDeploymentStatus.ROLLED_BACK]
    assert len(rolled_back) == 1
    assert rolled_back[0].version == "v2"
    assert rolled_back[0].rollback_from == "v2"


def test_rollback_to_already_active_version_skips_audit(service_factory):
    """Rolling back to the current active version must not record a phantom ROLLED_BACK row."""
    service, _ = service_factory(agent=_custom_agent(updated_at="v1"))
    service.deploy("writer")

    service.rollback("writer", to_version="v1")

    history = service.list_history("writer")
    assert all(d.status is not AgentDeploymentStatus.ROLLED_BACK for d in history)
    assert service.get_active("writer").version == "v1"


def test_rollback_to_missing_version_raises_preflight(service_factory):
    service, _ = service_factory(agent=_custom_agent())
    service.deploy("writer")

    with pytest.raises(DeploymentPreflightError) as excinfo:
        service.rollback("writer", to_version="nope")
    assert excinfo.value.code == "rollback_target_not_found"
