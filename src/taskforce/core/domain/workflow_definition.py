"""First-class workflow definition models (ADR-022 §7).

A workflow names the agents that participate, the trigger that
launches it (chat command, schedule, event, webhook), and the
orchestration topology (linear sequence, fan-out + join via
``depends_on``). Definitions are storable per tenant; the runtime
materialises them on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final


# ADR-022 §7 trigger kinds. Stored as plain strings so YAML / JSON stay
# human-friendly. The framework treats unknown values as ``manual`` to
# stay forward-compatible with future kinds an enterprise plugin might
# introduce.
WORKFLOW_TRIGGER_MANUAL: Final[str] = "manual"
WORKFLOW_TRIGGER_CHAT: Final[str] = "chat"
WORKFLOW_TRIGGER_SCHEDULE: Final[str] = "schedule"
WORKFLOW_TRIGGER_EVENT: Final[str] = "event"
WORKFLOW_TRIGGER_WEBHOOK: Final[str] = "webhook"

WORKFLOW_TRIGGER_KINDS: Final[frozenset[str]] = frozenset(
    {
        WORKFLOW_TRIGGER_MANUAL,
        WORKFLOW_TRIGGER_CHAT,
        WORKFLOW_TRIGGER_SCHEDULE,
        WORKFLOW_TRIGGER_EVENT,
        WORKFLOW_TRIGGER_WEBHOOK,
    }
)


@dataclass(frozen=True)
class WorkflowStep:
    """One node in a workflow definition.

    A step normally runs a local agent (``executor.execute_mission``).
    When ``acp_peer`` is set, the runtime calls that ACP peer instead
    (ADR-022 §7, G7). The framework's existing cross-tenant authorizer
    still applies — a remote peer in a different tenant requires the
    caller to hold ``acp:peer:cross_tenant``.
    """

    step_id: str
    agent: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    acp_peer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow step."""
        payload: dict[str, Any] = {
            "step_id": self.step_id,
            "agent": self.agent,
            "task": self.task,
            "depends_on": list(self.depends_on),
            "metadata": dict(self.metadata),
        }
        if self.acp_peer is not None:
            payload["acp_peer"] = self.acp_peer
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        """Deserialize a workflow step."""
        acp_peer = data.get("acp_peer")
        return cls(
            step_id=str(data["step_id"]),
            agent=str(data["agent"]),
            task=str(data["task"]),
            depends_on=[str(item) for item in data.get("depends_on", [])],
            metadata=dict(data.get("metadata", {})),
            acp_peer=str(acp_peer) if acp_peer else None,
        )


@dataclass(frozen=True)
class WorkflowDefinition:
    """Tenant-storable workflow definition composed of named agent steps.

    ``trigger`` is the kind name (one of :data:`WORKFLOW_TRIGGER_KINDS`).
    ``trigger_config`` carries trigger-specific settings — e.g. a cron
    expression for ``schedule``, an event-type name for ``event``, or
    a webhook path for ``webhook``. The framework treats it opaquely;
    the workflow runtime / scheduler / gateway each interpret the keys
    they care about.
    """

    workflow_id: str
    name: str
    description: str = ""
    trigger: str = WORKFLOW_TRIGGER_MANUAL
    trigger_config: dict[str, Any] = field(default_factory=dict)
    steps: list[WorkflowStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow definition."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "trigger_config": dict(self.trigger_config),
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDefinition:
        """Deserialize a workflow definition.

        Tolerant of older payloads that lacked ``trigger_config`` and
        of payloads where ``trigger`` is a dict instead of a string
        (alternative YAML shape: ``trigger: {kind: schedule, config:
        {cron: ...}}``).
        """
        raw_trigger = data.get("trigger", WORKFLOW_TRIGGER_MANUAL)
        raw_trigger_config = data.get("trigger_config", {})
        if isinstance(raw_trigger, dict):
            kind = str(raw_trigger.get("kind", WORKFLOW_TRIGGER_MANUAL))
            config = dict(raw_trigger.get("config", {}))
        else:
            kind = str(raw_trigger)
            config = dict(raw_trigger_config or {})
        return cls(
            workflow_id=str(data["workflow_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            trigger=kind,
            trigger_config=config,
            steps=[WorkflowStep.from_dict(item) for item in data.get("steps", [])],
            metadata=dict(data.get("metadata", {})),
        )
