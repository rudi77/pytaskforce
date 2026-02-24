"""Rule engine for evaluating trigger rules against agent events.

Maintains a set of TriggerRules and evaluates them against incoming
AgentEvents, returning matching actions to dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from taskforce.core.domain.agent_event import AgentEvent
from taskforce.core.domain.trigger_rule import RuleAction, TriggerRule

logger = structlog.get_logger(__name__)


def _match_filter(value: Any, condition: Any) -> bool:
    """Evaluate a single filter condition against a value.

    Supports operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $contains.
    If condition is a plain value (not a dict), uses equality check.
    """
    if not isinstance(condition, dict):
        return value == condition  # type: ignore[no-any-return]

    for op, expected in condition.items():
        if op == "$eq" and value != expected:
            return False
        if op == "$ne" and value == expected:
            return False
        if op == "$gt" and not (value > expected):
            return False
        if op == "$gte" and not (value >= expected):
            return False
        if op == "$lt" and not (value < expected):
            return False
        if op == "$lte" and not (value <= expected):
            return False
        if op == "$in" and value not in expected:
            return False
        if op == "$contains" and expected not in str(value):
            return False
    return True


def _matches_event(rule: TriggerRule, event: AgentEvent) -> bool:
    """Check whether a rule's trigger condition matches an event."""
    trigger = rule.trigger

    # Check source
    if trigger.source != "*" and trigger.source != event.source:
        return False

    # Check event type
    if trigger.event_type != "*" and trigger.event_type != event.event_type.value:
        return False

    # Check payload filters
    for key, condition in trigger.filters.items():
        actual = event.payload.get(key)
        if not _match_filter(actual, condition):
            return False

    return True


def _render_template(template: str, event: AgentEvent) -> str:
    """Render a Jinja2-style template with event data.

    Falls back to simple string.format_map if jinja2 is not available.
    """
    context = {
        "event": {
            "source": event.source,
            "event_type": event.event_type.value,
            **event.payload,
        },
        "metadata": event.metadata,
    }

    try:
        from jinja2 import Template

        return Template(template).render(**context)
    except ImportError:
        # Fallback: simple {{key}} replacement
        result = template
        for key, val in context.get("event", {}).items():
            result = result.replace("{{event." + key + "}}", str(val))
        for key, val in context.get("metadata", {}).items():
            result = result.replace("{{metadata." + key + "}}", str(val))
        return result


class RuleEngine:
    """Evaluates trigger rules against agent events.

    Rules are stored in-memory and persisted to a JSON file
    for survival across restarts.
    """

    def __init__(self, work_dir: str = ".taskforce") -> None:
        self._rules: dict[str, TriggerRule] = {}
        self._store_path = Path(work_dir) / "butler" / "rules.json"

    async def load(self) -> None:
        """Load persisted rules from disk."""
        if not self._store_path.exists():
            return
        try:
            async with aiofiles.open(self._store_path) as f:
                raw = await f.read()
            data = json.loads(raw)
            for item in data:
                rule = TriggerRule.from_dict(item)
                self._rules[rule.rule_id] = rule
            logger.info("rule_engine.loaded", count=len(self._rules))
        except Exception as exc:
            logger.warning("rule_engine.load_failed", error=str(exc))

    async def _persist(self) -> None:
        """Persist rules to disk."""
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._rules.values()]
        raw = json.dumps(data, indent=2, default=str)
        tmp = self._store_path.with_suffix(".json.tmp")
        async with aiofiles.open(tmp, "w") as f:
            await f.write(raw)
        tmp.rename(self._store_path)

    async def add_rule(self, rule: TriggerRule) -> str:
        """Add a new trigger rule."""
        self._rules[rule.rule_id] = rule
        await self._persist()
        logger.info("rule_engine.rule_added", rule_id=rule.rule_id, name=rule.name)
        return rule.rule_id

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a trigger rule."""
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        await self._persist()
        logger.info("rule_engine.rule_removed", rule_id=rule_id)
        return True

    async def get_rule(self, rule_id: str) -> TriggerRule | None:
        """Retrieve a rule by ID."""
        return self._rules.get(rule_id)

    async def list_rules(self) -> list[TriggerRule]:
        """List all rules, sorted by priority descending."""
        return sorted(self._rules.values(), key=lambda r: r.priority, reverse=True)

    async def evaluate(self, event: AgentEvent) -> list[RuleAction]:
        """Evaluate all rules against an event, return matching actions.

        Actions are returned in priority order (highest first).
        If a rule has a template, the action's params['message'] is rendered.
        """
        rules_sorted = sorted(self._rules.values(), key=lambda r: r.priority, reverse=True)

        matching_actions: list[RuleAction] = []
        for rule in rules_sorted:
            if not rule.enabled:
                continue
            if _matches_event(rule, event):
                action = rule.action
                # Render template if present
                if action.template:
                    rendered = _render_template(action.template, event)
                    params = dict(action.params)
                    params["message"] = rendered
                    action = RuleAction(
                        action_type=action.action_type,
                        params=params,
                        template=action.template,
                    )
                matching_actions.append(action)
                logger.info(
                    "rule_engine.rule_matched",
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    event_type=event.event_type.value,
                )

        return matching_actions
