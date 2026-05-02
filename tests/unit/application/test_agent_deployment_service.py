from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from taskforce.application.agent_deployment_service import AgentDeploymentService


class _Registry:
    def __init__(self, agent: object | None) -> None:
        self._agent = agent

    def get_agent(self, agent_id: str):
        return self._agent if getattr(self._agent, "agent_id", None) == agent_id else None


def _agent() -> SimpleNamespace:
    return SimpleNamespace(
        agent_id="coder",
        tool_allowlist=[],
        mcp_servers=[],
        mcp_tool_allowlist=[],
        name="Coder",
    )


def test_prepare_deploy_creates_snapshot_and_audit(tmp_path) -> None:
    service = AgentDeploymentService(_Registry(_agent()), work_dir=tmp_path)

    result = service.prepare_deploy("coder")

    assert result["status"] == "prepared"
    assert "snapshot_path" in result
    assert (tmp_path / "agent_deployments" / "audit.log").exists()


def test_deploy_activate_and_rollback_persist_state(tmp_path) -> None:
    service = AgentDeploymentService(_Registry(_agent()), work_dir=tmp_path)

    service.prepare_deploy("coder")
    deployed = service.deploy("coder", "1.0.0", "prod")
    active = service.activate("coder", "1.0.0", "prod")
    rolled = service.rollback("coder", "1.0.0", "prod")

    assert deployed["status"] in {"deployed", "active"}
    assert active["status"] == "active"
    assert rolled["status"] == "active"

    state = json.loads((tmp_path / "agent_deployments" / "state.json").read_text(encoding="utf-8"))
    assert state["active"]["coder:prod"]["version"] == "1.0.0"


def test_deploy_persists_failed_state_when_agent_missing(tmp_path) -> None:
    service = AgentDeploymentService(_Registry(None), work_dir=tmp_path)

    with pytest.raises(ValueError, match="not found"):
        service.deploy("missing", "1.0.0", "prod")

    state = json.loads((tmp_path / "agent_deployments" / "state.json").read_text(encoding="utf-8"))
    record = state["deployments"]["missing:1.0.0:prod"]
    assert record["status"] == "failed"
    assert "not found" in record["error"]
