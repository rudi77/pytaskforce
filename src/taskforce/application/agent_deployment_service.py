"""Agent deployment service use-cases.

Provides a dedicated application service to prepare, deploy, activate,
and rollback agent versions with immutable snapshots and audit trails.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from taskforce.api.routes.agents import _validate_tool_allowlists

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DeploymentRecord:
    """Persisted deployment metadata for a specific agent version/environment."""

    agent_id: str
    version: str
    environment: str
    status: str
    snapshot_path: str
    created_at: str
    updated_at: str
    error: str | None = None


class AgentDeploymentService:
    """Service implementing agent deployment lifecycle use-cases."""

    def __init__(self, registry: Any, work_dir: str | Path = ".taskforce") -> None:
        self._registry = registry
        self._root = Path(work_dir) / "agent_deployments"
        self._snapshots = self._root / "snapshots"
        self._state_file = self._root / "state.json"
        self._audit_file = self._root / "audit.log"
        self._logger = logger.bind(component="agent_deployment_service")
        self._root.mkdir(parents=True, exist_ok=True)
        self._snapshots.mkdir(parents=True, exist_ok=True)

    def prepare_deploy(self, agent_id: str) -> dict[str, Any]:
        """Validate agent/tool configuration and create immutable snapshot."""
        agent = self._require_agent(agent_id)
        self._validate_agent_config(agent)
        snapshot_path = self._create_snapshot(agent_id, agent)
        self._append_audit("prepare_deploy", agent_id, {"snapshot_path": str(snapshot_path)})
        return {"agent_id": agent_id, "snapshot_path": str(snapshot_path), "status": "prepared"}

    def deploy(self, agent_id: str, version: str, environment: str) -> dict[str, Any]:
        """Deploy a version from snapshot and persist status transitions."""
        state = self._load_state()
        now = self._now_iso()
        key = self._record_key(agent_id, version, environment)
        try:
            agent = self._require_agent(agent_id)
            self._validate_agent_config(agent)
            snapshot_path = self._resolve_or_create_snapshot(agent_id)
            state["deployments"][key] = {
                "agent_id": agent_id,
                "version": version,
                "environment": environment,
                "status": "deployed",
                "snapshot_path": str(snapshot_path),
                "created_at": state["deployments"].get(key, {}).get("created_at", now),
                "updated_at": now,
                "error": None,
            }
            self._atomic_write_json(self._state_file, state)
            self._append_audit("deploy", agent_id, {"version": version, "environment": environment})
            return state["deployments"][key]
        except Exception as exc:
            self._persist_failed(state, key, agent_id, version, environment, str(exc))
            raise

    def activate(self, agent_id: str, version: str, environment: str) -> dict[str, Any]:
        """Atomically mark a deployed version as active in an environment."""
        state = self._load_state()
        key = self._record_key(agent_id, version, environment)
        record = state["deployments"].get(key)
        if not record:
            raise ValueError("Deployment record not found for activation")

        state["active"][f"{agent_id}:{environment}"] = {
            "version": version,
            "updated_at": self._now_iso(),
        }
        record["status"] = "active"
        record["updated_at"] = self._now_iso()
        self._atomic_write_json(self._state_file, state)
        self._append_audit("activate", agent_id, {"version": version, "environment": environment})
        return record

    def rollback(self, agent_id: str, to_version: str, environment: str) -> dict[str, Any]:
        """Rollback active version to an existing deployed version."""
        state = self._load_state()
        key = self._record_key(agent_id, to_version, environment)
        record = state["deployments"].get(key)
        if not record:
            raise ValueError("Target rollback version is not deployed")

        state["active"][f"{agent_id}:{environment}"] = {
            "version": to_version,
            "updated_at": self._now_iso(),
        }
        record["status"] = "active"
        record["updated_at"] = self._now_iso()
        self._atomic_write_json(self._state_file, state)
        self._append_audit("rollback", agent_id, {"to_version": to_version, "environment": environment})
        return record

    def _require_agent(self, agent_id: str) -> Any:
        agent = self._registry.get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent '{agent_id}' not found")
        return agent

    def _validate_agent_config(self, agent: Any) -> None:
        _validate_tool_allowlists(
            getattr(agent, "tool_allowlist", []) or [],
            getattr(agent, "mcp_servers", []) or [],
            getattr(agent, "mcp_tool_allowlist", []) or [],
        )

    def _create_snapshot(self, agent_id: str, agent: Any) -> Path:
        payload = deepcopy(agent.__dict__)
        payload["snapshot_created_at"] = self._now_iso()
        payload["agent_id"] = agent_id
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self._snapshots / f"{agent_id}-{timestamp}.json"
        self._atomic_write_json(path, payload)
        return path

    def _resolve_or_create_snapshot(self, agent_id: str) -> Path:
        candidates = sorted(self._snapshots.glob(f"{agent_id}-*.json"))
        if candidates:
            return candidates[-1]
        agent = self._require_agent(agent_id)
        return self._create_snapshot(agent_id, agent)

    def _load_state(self) -> dict[str, Any]:
        if not self._state_file.exists():
            return {"deployments": {}, "active": {}}
        return json.loads(self._state_file.read_text(encoding="utf-8"))

    def _persist_failed(
        self,
        state: dict[str, Any],
        key: str,
        agent_id: str,
        version: str,
        environment: str,
        error: str,
    ) -> None:
        now = self._now_iso()
        state.setdefault("deployments", {})[key] = {
            "agent_id": agent_id,
            "version": version,
            "environment": environment,
            "status": "failed",
            "snapshot_path": "",
            "created_at": state.get("deployments", {}).get(key, {}).get("created_at", now),
            "updated_at": now,
            "error": error,
        }
        self._atomic_write_json(self._state_file, state)
        self._append_audit("deploy_failed", agent_id, {"version": version, "environment": environment, "error": error})

    def _append_audit(self, event: str, agent_id: str, details: dict[str, Any]) -> None:
        entry = {
            "ts": self._now_iso(),
            "event": event,
            "agent_id": agent_id,
            "details": details,
        }
        with self._audit_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        self._logger.info("agent.deployment.audit", **entry)

    @staticmethod
    def _record_key(agent_id: str, version: str, environment: str) -> str:
        return f"{agent_id}:{version}:{environment}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
