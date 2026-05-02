"""File-backed registry for agent deployment releases and environment pointers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from taskforce.infrastructure.persistence.yaml_io import atomic_write_yaml, safe_load_yaml


class FileAgentDeploymentRegistry:
    """Persist agent releases, active environment pointers, and rollback history."""

    def __init__(self, root_dir: str | Path = ".taskforce/deployments") -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def create_release(
        self,
        agent_id: str,
        release_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a release record for an agent."""
        release = {
            "agent_id": agent_id,
            "release_id": release_id,
            "created_at": self._now_iso(),
            "metadata": metadata,
            "deployments": [],
        }
        release_path = self._release_path(agent_id, release_id)
        if release_path.exists():
            msg = f"Release '{release_id}' already exists for agent '{agent_id}'"
            raise FileExistsError(msg)
        release_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_yaml(release_path, release)
        return release

    def mark_deployed(
        self,
        agent_id: str,
        release_id: str,
        environment: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append deployment metadata to a release and update active pointer."""
        release = self._load_release(agent_id, release_id)
        deployment_event = {
            "environment": environment,
            "deployed_at": self._now_iso(),
            "metadata": metadata or {},
        }
        release.setdefault("deployments", []).append(deployment_event)
        atomic_write_yaml(self._release_path(agent_id, release_id), release)
        self.set_active(agent_id, environment, release_id)
        return deployment_event

    def set_active(self, agent_id: str, environment: str, release_id: str) -> dict[str, Any]:
        """Set active release pointer for an environment."""
        self._load_release(agent_id, release_id)
        active_record = {
            "agent_id": agent_id,
            "environment": environment,
            "release_id": release_id,
            "updated_at": self._now_iso(),
        }
        pointer_path = self._active_pointer_path(agent_id, environment)
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        previous = safe_load_yaml(pointer_path)
        atomic_write_yaml(pointer_path, active_record)
        self._append_history(agent_id, environment, previous, active_record)
        return active_record

    def list_releases(self, agent_id: str) -> list[dict[str, Any]]:
        """Return releases for an agent sorted by creation time descending."""
        releases_dir = self._agent_dir(agent_id) / "releases"
        if not releases_dir.exists():
            return []
        releases: list[dict[str, Any]] = []
        for path in sorted(releases_dir.glob("*.yaml")):
            data = safe_load_yaml(path)
            if data is not None:
                releases.append(data)
        return sorted(releases, key=lambda item: item.get("created_at", ""), reverse=True)

    def rollback_to(self, agent_id: str, environment: str, release_id: str) -> dict[str, Any]:
        """Rollback environment active pointer to an existing release."""
        self._load_release(agent_id, release_id)
        rollback_event = {
            "agent_id": agent_id,
            "environment": environment,
            "release_id": release_id,
            "rolled_back_at": self._now_iso(),
        }
        self.set_active(agent_id, environment, release_id)
        history_path = self._history_path(agent_id, environment)
        history = safe_load_yaml(history_path) or {"events": []}
        history.setdefault("events", []).append({"type": "rollback", **rollback_event})
        atomic_write_yaml(history_path, history)
        return rollback_event

    def _append_history(
        self,
        agent_id: str,
        environment: str,
        previous: dict[str, Any] | None,
        current: dict[str, Any],
    ) -> None:
        history_path = self._history_path(agent_id, environment)
        history = safe_load_yaml(history_path) or {"events": []}
        history.setdefault("events", []).append(
            {
                "type": "set_active",
                "changed_at": self._now_iso(),
                "previous": previous,
                "current": current,
            }
        )
        history_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_yaml(history_path, history)

    def _load_release(self, agent_id: str, release_id: str) -> dict[str, Any]:
        release_path = self._release_path(agent_id, release_id)
        release = safe_load_yaml(release_path)
        if release is None:
            msg = f"Release '{release_id}' not found for agent '{agent_id}'"
            raise FileNotFoundError(msg)
        return release

    def _agent_dir(self, agent_id: str) -> Path:
        return self._root_dir / agent_id

    def _release_path(self, agent_id: str, release_id: str) -> Path:
        return self._agent_dir(agent_id) / "releases" / f"{release_id}.yaml"

    def _active_pointer_path(self, agent_id: str, environment: str) -> Path:
        return self._agent_dir(agent_id) / "active" / f"{environment}.yaml"

    def _history_path(self, agent_id: str, environment: str) -> Path:
        return self._agent_dir(agent_id) / "history" / f"{environment}.yaml"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
