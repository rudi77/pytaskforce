"""First-class workflow definition models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    """One node in a workflow definition."""

    step_id: str
    agent: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow step."""
        return {
            "step_id": self.step_id,
            "agent": self.agent,
            "task": self.task,
            "depends_on": list(self.depends_on),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        """Deserialize a workflow step."""
        return cls(
            step_id=str(data["step_id"]),
            agent=str(data["agent"]),
            task=str(data["task"]),
            depends_on=[str(item) for item in data.get("depends_on", [])],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class WorkflowDefinition:
    """Tenant-storable workflow definition composed of named agent steps."""

    workflow_id: str
    name: str
    description: str = ""
    trigger: str = "manual"
    steps: list[WorkflowStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow definition."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDefinition:
        """Deserialize a workflow definition."""
        return cls(
            workflow_id=str(data["workflow_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            trigger=str(data.get("trigger", "manual")),
            steps=[WorkflowStep.from_dict(item) for item in data.get("steps", [])],
            metadata=dict(data.get("metadata", {})),
        )
