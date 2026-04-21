"""Rule manager tool for creating and managing trigger rules.

Allows the agent to create, list, enable/disable, and remove
event-to-action trigger rules at runtime.
"""

from __future__ import annotations

from typing import Any

import structlog

from taskforce.core.domain.errors import ToolError, tool_error_payload
from taskforce.core.domain.trigger_rule import (
    RuleAction,
    RuleActionType,
    TriggerCondition,
    TriggerRule,
)
from taskforce.core.interfaces.tools import ApprovalRiskLevel

logger = structlog.get_logger(__name__)


class RuleManagerTool:
    """Tool for managing trigger rules within the butler's rule engine.

    Supports creating rules that connect external events to actions
    like sending notifications or executing agent missions.
    """

    def __init__(self, rule_engine: Any = None) -> None:
        self._rule_engine = rule_engine

    @property
    def name(self) -> str:
        return "rule_manager"

    @property
    def description(self) -> str:
        return (
            "Manage trigger rules that connect events to actions. "
            "Create rules like 'when a calendar event is in 30 minutes, "
            "send a Telegram notification'. Actions: add, list, remove, get. "
            "Rules support conditions on event source, type, and payload filters."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove", "get"],
                    "description": "Rule management action to perform",
                },
                "rule_id": {
                    "type": "string",
                    "description": "Rule ID (for remove/get)",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable rule name",
                },
                "description": {
                    "type": "string",
                    "description": "What the rule does",
                },
                "trigger_source": {
                    "type": "string",
                    "description": "Event source to match ('calendar', 'email', '*')",
                },
                "trigger_event_type": {
                    "type": "string",
                    "description": "Event type to match ('calendar.upcoming', '*')",
                },
                "trigger_filters": {
                    "type": "object",
                    "description": "Filters on event payload (e.g. {minutes_until: {$lte: 30}})",
                },
                "action_type": {
                    "type": "string",
                    "enum": ["notify", "execute_mission", "log_memory"],
                    "description": "What action to take when the rule fires",
                },
                "action_params": {
                    "type": "object",
                    "description": "Action parameters (channel, message, mission text, etc.)",
                },
                "action_template": {
                    "type": "string",
                    "description": "Jinja2 template for dynamic messages using event payload variables",
                },
                "priority": {
                    "type": "integer",
                    "description": "Rule priority (higher = evaluated first, default: 0)",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def approval_risk_level(self) -> ApprovalRiskLevel:
        return ApprovalRiskLevel.MEDIUM

    @property
    def supports_parallelism(self) -> bool:
        return False

    def get_approval_preview(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        return f"Tool: {self.name}\nOperation: {action}\nRule: {name}"

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute a rule management action."""
        if not self._rule_engine:
            return {"success": False, "error": "Rule engine not configured."}

        action = kwargs.get("action")
        try:
            if action == "add":
                return await self._add_rule(**kwargs)
            if action == "list":
                return await self._list_rules()
            if action == "remove":
                return await self._remove_rule(kwargs.get("rule_id", ""))
            if action == "get":
                return await self._get_rule(kwargs.get("rule_id", ""))
            return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as exc:
            return tool_error_payload(ToolError(f"{self.name} failed: {exc}", tool_name=self.name))

    async def _add_rule(self, **kwargs: Any) -> dict[str, Any]:
        """Add a new trigger rule."""
        rule = TriggerRule(
            name=kwargs.get("name", "unnamed"),
            description=kwargs.get("description", ""),
            trigger=TriggerCondition(
                source=kwargs.get("trigger_source", "*"),
                event_type=kwargs.get("trigger_event_type", "*"),
                filters=kwargs.get("trigger_filters", {}),
            ),
            action=RuleAction(
                action_type=RuleActionType(kwargs.get("action_type", "notify")),
                params=kwargs.get("action_params", {}),
                template=kwargs.get("action_template"),
            ),
            priority=int(kwargs.get("priority", 0)),
        )
        rule_id = await self._rule_engine.add_rule(rule)
        return {
            "success": True,
            "rule_id": rule_id,
            "name": rule.name,
            "message": f"Rule '{rule.name}' created with ID {rule_id}",
        }

    async def _list_rules(self) -> dict[str, Any]:
        """List all trigger rules."""
        rules = await self._rule_engine.list_rules()
        return {
            "success": True,
            "rules": [r.to_dict() for r in rules],
            "count": len(rules),
        }

    async def _remove_rule(self, rule_id: str) -> dict[str, Any]:
        """Remove a trigger rule."""
        removed = await self._rule_engine.remove_rule(rule_id)
        if removed:
            return {"success": True, "message": f"Rule {rule_id} removed"}
        return {"success": False, "error": f"Rule {rule_id} not found"}

    async def _get_rule(self, rule_id: str) -> dict[str, Any]:
        """Get details of a specific rule."""
        rule = await self._rule_engine.get_rule(rule_id)
        if rule:
            return {"success": True, "rule": rule.to_dict()}
        return {"success": False, "error": f"Rule {rule_id} not found"}

    def validate_params(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate parameters."""
        action = kwargs.get("action")
        if not action:
            return False, "Missing required parameter: action"
        if action == "add":
            if not kwargs.get("name"):
                return False, "Missing required parameter: name"
            if not kwargs.get("action_type"):
                return False, "Missing required parameter: action_type"
        if action in ("remove", "get"):
            if not kwargs.get("rule_id"):
                return False, "Missing required parameter: rule_id"
        return True, None
