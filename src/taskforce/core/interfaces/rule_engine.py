"""Protocol for trigger-based rule evaluation against agent events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent_event import AgentEvent
    from taskforce.core.domain.trigger_rule import RuleAction, TriggerRule


class RuleEngineProtocol(Protocol):
    """Protocol for evaluating trigger rules against agent events."""

    async def add_rule(self, rule: TriggerRule) -> str:
        """Add a new trigger rule. Returns the rule_id."""
        ...

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a trigger rule. Returns True if found and removed."""
        ...

    async def get_rule(self, rule_id: str) -> TriggerRule | None:
        """Retrieve a rule by ID."""
        ...

    async def list_rules(self) -> list[TriggerRule]:
        """List all registered rules, sorted by priority descending."""
        ...

    async def evaluate(self, event: AgentEvent) -> list[RuleAction]:
        """Evaluate all rules against an event and return matching actions."""
        ...
