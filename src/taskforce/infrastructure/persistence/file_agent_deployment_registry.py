"""File-backed registry for agent deployment lifecycle records.

Storage layout (under ``<work_dir>/deployments/<agent_id>/``)::

    history.yaml                      # ordered list of deployment records
    active/<environment>.yaml         # pointer to the currently-active version

Implements :class:`DeploymentRegistryProtocol` and is the single source of
truth for deployment lifecycle data. The agent definition itself remains in
the agent registry (``configs/custom/<agent_id>.yaml``) — this module never
mutates it.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from taskforce.core.domain.agent_deployment import (
    AgentDeployment,
    AgentDeploymentStatus,
    DeploymentEnvironment,
)
from taskforce.infrastructure.persistence.yaml_io import (
    atomic_write_yaml,
    safe_load_yaml,
)


class FileAgentDeploymentRegistry:
    """File-based implementation of :class:`DeploymentRegistryProtocol`."""

    def __init__(self, work_dir: str | Path | None = None) -> None:
        base = Path(work_dir) if work_dir else Path(os.getenv("TASKFORCE_WORK_DIR", ".taskforce"))
        self._root = base / "deployments"
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ API

    def record(self, deployment: AgentDeployment) -> AgentDeployment:
        """Append a deployment record and update the active pointer."""
        history = self._load_history(deployment.agent_id)
        history.append(self._to_dict(deployment))
        atomic_write_yaml(self._history_path(deployment.agent_id), {"deployments": history})

        env = deployment.environment
        if deployment.status == AgentDeploymentStatus.DEPLOYED:
            self._write_active_pointer(deployment.agent_id, env, deployment)
        elif deployment.status == AgentDeploymentStatus.ROLLED_BACK:
            # The rolled-back version is no longer active.
            active_path = self._active_path(deployment.agent_id, env)
            if active_path.exists():
                active_path.unlink()

        return deployment

    def get_active(
        self,
        agent_id: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
    ) -> AgentDeployment | None:
        env = DeploymentEnvironment.coerce(environment)
        data = safe_load_yaml(self._active_path(agent_id, env))
        if not isinstance(data, dict):
            return None
        return self._from_dict(data)

    def list_for_agent(self, agent_id: str) -> list[AgentDeployment]:
        history = self._load_history(agent_id)
        return [self._from_dict(item) for item in reversed(history)]

    def is_deployed(
        self,
        agent_id: str,
        environment: DeploymentEnvironment | str = DeploymentEnvironment.LOCAL,
    ) -> bool:
        active = self.get_active(agent_id, environment)
        return active is not None and active.status == AgentDeploymentStatus.DEPLOYED

    # --------------------------------------------------------------- helpers

    def _load_history(self, agent_id: str) -> list[dict[str, Any]]:
        data = safe_load_yaml(self._history_path(agent_id))
        if not isinstance(data, dict):
            return []
        items = data.get("deployments")
        return list(items) if isinstance(items, list) else []

    def _write_active_pointer(
        self,
        agent_id: str,
        environment: DeploymentEnvironment,
        deployment: AgentDeployment,
    ) -> None:
        atomic_write_yaml(self._active_path(agent_id, environment), self._to_dict(deployment))

    def _agent_dir(self, agent_id: str) -> Path:
        path = self._root / agent_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _history_path(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "history.yaml"

    def _active_path(self, agent_id: str, environment: DeploymentEnvironment) -> Path:
        active_dir = self._agent_dir(agent_id) / "active"
        active_dir.mkdir(parents=True, exist_ok=True)
        return active_dir / f"{environment.value}.yaml"

    @staticmethod
    def _to_dict(deployment: AgentDeployment) -> dict[str, Any]:
        return {
            "agent_id": deployment.agent_id,
            "version": deployment.version,
            "status": deployment.status.value,
            "environment": deployment.environment.value,
            "deployed_at": deployment.deployed_at.isoformat() if deployment.deployed_at else None,
            "deployed_by": deployment.deployed_by,
            "message": deployment.message,
            "rollback_from": deployment.rollback_from,
            "error": deployment.error,
            "config_snapshot": dict(deployment.config_snapshot),
        }

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> AgentDeployment:
        deployed_at_raw = data.get("deployed_at")
        deployed_at: datetime | None = None
        if deployed_at_raw:
            try:
                deployed_at = datetime.fromisoformat(deployed_at_raw)
            except (TypeError, ValueError):
                deployed_at = None

        return AgentDeployment(
            agent_id=data["agent_id"],
            version=str(data.get("version", "")),
            status=AgentDeploymentStatus(data["status"]),
            environment=DeploymentEnvironment.coerce(data["environment"]),
            deployed_at=deployed_at,
            deployed_by=data.get("deployed_by"),
            message=data.get("message"),
            rollback_from=data.get("rollback_from"),
            error=data.get("error"),
            config_snapshot=data.get("config_snapshot") or {},
        )
