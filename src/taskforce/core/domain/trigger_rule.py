"""Trigger rule domain models for the butler rule engine.

Defines the "if X then Y" primitives that connect events to actions.
Rules are evaluated by the RuleEngine when an AgentEvent arrives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from taskforce.core.utils.time import utc_now


class RuleActionType(str, Enum):
    """Type of action a rule can trigger."""

    NOTIFY = "notify"
    EXECUTE_MISSION = "execute_mission"
    LOG_MEMORY = "log_memory"


@dataclass
class TriggerCondition:
    """Condition that must be met for a rule to fire.

    Attributes:
        source: Event source to match ("calendar", "email", "*" for any).
        event_type: Event type string to match (supports "*" wildcard).
        filters: JSONPath-style filters on the event payload.
                 Supported operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $contains.
                 Example: {"minutes_until": {"$lte": 30}}
    """

    source: str = "*"
    event_type: str = "*"
    filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "source": self.source,
            "event_type": self.event_type,
            "filters": self.filters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerCondition:
        """Deserialize from stored dict."""
        return cls(
            source=str(data.get("source", "*")),
            event_type=str(data.get("event_type", "*")),
            filters=dict(data.get("filters", {})),
        )


@dataclass
class RuleAction:
    """Action to perform when a rule fires.

    Attributes:
        action_type: What kind of action to perform.
        params: Action-specific parameters (channel, mission text, etc.).
        template: Optional Jinja2 template for dynamic message generation.
                  Template variables come from the event payload.
    """

    action_type: RuleActionType
    params: dict[str, Any] = field(default_factory=dict)
    template: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        result: dict[str, Any] = {
            "action_type": self.action_type.value,
            "params": self.params,
        }
        if self.template is not None:
            result["template"] = self.template
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleAction:
        """Deserialize from stored dict."""
        return cls(
            action_type=RuleActionType(data["action_type"]),
            params=dict(data.get("params", {})),
            template=data.get("template"),
        )


@dataclass
class TriggerRule:
    """A trigger rule that connects events to actions.

    Rules are evaluated by the RuleEngine against incoming AgentEvents.
    When a rule's condition matches, its action is dispatched.

    Attributes:
        rule_id: Unique identifier for this rule.
        name: Human-readable rule name (e.g. "calendar_reminder_30min").
        description: What this rule does, for documentation.
        trigger: Condition that must be met for the rule to fire.
        action: Action to perform when fired.
        enabled: Whether the rule is active.
        priority: Higher priority rules are evaluated first.
        created_at: When the rule was created.
    """

    rule_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    trigger: TriggerCondition = field(default_factory=TriggerCondition)
    action: RuleAction = field(
        default_factory=lambda: RuleAction(action_type=RuleActionType.NOTIFY)
    )
    enabled: bool = True
    priority: int = 0
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.to_dict(),
            "action": self.action.to_dict(),
            "enabled": self.enabled,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerRule:
        """Deserialize from stored dict."""
        created_raw = data.get("created_at")
        return cls(
            rule_id=str(data.get("rule_id", uuid4().hex)),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            trigger=TriggerCondition.from_dict(data.get("trigger", {})),
            action=RuleAction.from_dict(data.get("action", {})),
            enabled=bool(data.get("enabled", True)),
            priority=int(data.get("priority", 0)),
            created_at=datetime.fromisoformat(created_raw) if created_raw else utc_now(),
        )
