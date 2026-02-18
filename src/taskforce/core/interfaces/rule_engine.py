"""Rule Engine Protocol for event-to-action mapping.

Defines the contract for evaluating trigger rules against incoming
AgentEvents and returning matching actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from taskforce.core.domain.agent_event import AgentEvent
    from taskforce.core.domain.trigger_rule import RuleAction, TriggerRule


class RuleEngineProtocol(Protocol):
    """Protocol for trigger-based rule evaluation.

    The rule engine maintains a set of TriggerRules and evaluates them
    against incoming AgentEvents, returning a list of actions to dispatch.
    """

    async def add_rule(self, rule: TriggerRule) -> str:
        """Add a new trigger rule.

        Args:
            rule: The rule to add.

        Returns:
            The rule_id of the added rule.
        """
        ...

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a trigger rule.

        Args:
            rule_id: ID of the rule to remove.

        Returns:
            True if the rule was found and removed.
        """
        ...

    async def get_rule(self, rule_id: str) -> TriggerRule | None:
        """Retrieve a rule by ID.

        Args:
            rule_id: ID of the rule to retrieve.

        Returns:
            The rule if found, None otherwise.
        """
        ...

    async def list_rules(self) -> list[TriggerRule]:
        """List all registered rules.

        Returns:
            List of all trigger rules, sorted by priority descending.
        """
        ...

    async def evaluate(self, event: AgentEvent) -> list[RuleAction]:
        """Evaluate all rules against an event and return matching actions.

        Args:
            event: The incoming event to evaluate.

        Returns:
            List of actions from all matching rules, ordered by priority.
        """
        ...
