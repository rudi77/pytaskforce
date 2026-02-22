"""
LLM Router - Dynamic model selection based on call context.

A transparent wrapper around LLMProviderProtocol that selects different
models based on configurable routing rules. The router evaluates each
rule in order and uses the first matching rule's model alias.

Routing decisions are based on context signals:
- ``has_tools`` / ``no_tools`` — whether tools are provided (reasoning vs. summarizing)
- ``message_count > N`` — conversation length (proxy for task complexity)
- ``hint:<name>`` — explicit hint passed as the ``model`` parameter by strategies

The router implements LLMProviderProtocol itself, so it is a drop-in
replacement that requires no changes to agents or planning strategies.

Example profile configuration::

    llm:
      routing:
        enabled: true
        default_model: main
        rules:
          - condition: "hint:planning"
            model: powerful
          - condition: "hint:reflecting"
            model: powerful
          - condition: "hint:summarizing"
            model: fast
          - condition: has_tools
            model: main
          - condition: no_tools
            model: fast
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

from taskforce.core.interfaces.llm import LLMProviderProtocol

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RoutingRule:
    """A single routing rule mapping a condition to a model alias.

    Attributes:
        condition: Rule expression. Supported forms:
            - ``"has_tools"`` — matches when tools list is non-empty
            - ``"no_tools"`` — matches when tools list is empty or None
            - ``"message_count > N"`` — matches when message count exceeds N
            - ``"hint:<name>"`` — matches when the caller passes ``<name>``
              as the ``model`` parameter (strategies use this for phase hints)
        model: Model alias to use when condition matches (e.g. ``"fast"``).
    """

    condition: str
    model: str


@dataclass
class LLMRouter:
    """Routes LLM calls to different models based on context.

    Wraps an existing ``LLMProviderProtocol`` implementation and overrides
    model selection based on configurable rules.  Implements the same
    protocol, so it is a transparent drop-in.

    When no rule matches the call context, ``default_model`` is used.
    If the caller passes a model alias that exists in the delegate's
    ``models`` dict (i.e. it's a real alias, not a hint), the router
    passes it through unchanged — explicit alias selection always wins.

    Attributes:
        delegate: The underlying LLM provider (e.g. ``LiteLLMService``).
        rules: Ordered list of routing rules (first match wins).
        default_model: Fallback model alias when no rule matches.
        known_aliases: Set of real model aliases the delegate knows about.
            Used to distinguish "this is a real alias" from "this is a hint".
    """

    delegate: LLMProviderProtocol
    rules: list[RoutingRule] = field(default_factory=list)
    default_model: str = "main"
    known_aliases: frozenset[str] = field(default_factory=frozenset)

    def _select_model(
        self,
        model_hint: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> str:
        """Evaluate routing rules and return the best model alias.

        Args:
            model_hint: The ``model`` parameter from the caller. May be a
                real alias, a phase hint, or None.
            messages: Conversation messages (used for ``message_count`` rules).
            tools: Tool definitions (used for ``has_tools``/``no_tools`` rules).

        Returns:
            Resolved model alias to pass to the delegate.
        """
        # If caller passed a known alias, respect it — no routing override
        if model_hint and model_hint in self.known_aliases:
            return model_hint

        for rule in self.rules:
            cond = rule.condition.strip()

            # Hint-based: match when model_hint equals the hint name
            if cond.startswith("hint:"):
                hint_name = cond[5:].strip()
                if model_hint == hint_name:
                    logger.debug(
                        "llm_router.rule_matched",
                        condition=cond,
                        selected_model=rule.model,
                    )
                    return rule.model

            # Tool presence
            elif cond == "has_tools":
                if tools:
                    logger.debug(
                        "llm_router.rule_matched",
                        condition=cond,
                        selected_model=rule.model,
                        tool_count=len(tools),
                    )
                    return rule.model

            elif cond == "no_tools":
                if not tools:
                    logger.debug(
                        "llm_router.rule_matched",
                        condition=cond,
                        selected_model=rule.model,
                    )
                    return rule.model

            # Message count threshold
            elif cond.startswith("message_count"):
                try:
                    threshold = int(cond.split(">")[1].strip())
                    if len(messages) > threshold:
                        logger.debug(
                            "llm_router.rule_matched",
                            condition=cond,
                            selected_model=rule.model,
                            message_count=len(messages),
                        )
                        return rule.model
                except (IndexError, ValueError):
                    logger.warning("llm_router.invalid_rule", condition=cond)

        # No rule matched — use default
        resolved = model_hint if model_hint and model_hint in self.known_aliases else self.default_model
        logger.debug(
            "llm_router.no_rule_matched",
            model_hint=model_hint,
            fallback=resolved,
        )
        return resolved

    # ── LLMProviderProtocol implementation ──────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Route completion call to the appropriate model.

        See ``LLMProviderProtocol.complete`` for full documentation.
        """
        resolved = self._select_model(model, messages, tools)
        return await self.delegate.complete(
            messages=messages,
            model=resolved,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Route generation call (no routing — pass through).

        Generate is a convenience wrapper with no tools/messages context,
        so routing rules don't apply. Falls back to default or explicit alias.
        """
        resolved = model if model and model in self.known_aliases else self.default_model
        if model and resolved != model:
            logger.debug(
                "llm_router.generate_fallback",
                hint=model,
                resolved=resolved,
            )
        return await self.delegate.generate(
            prompt=prompt,
            context=context,
            model=resolved,
            **kwargs,
        )

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Route streaming completion call to the appropriate model.

        See ``LLMProviderProtocol.complete_stream`` for full documentation.
        """
        resolved = self._select_model(model, messages, tools)
        async for chunk in self.delegate.complete_stream(
            messages=messages,
            model=resolved,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        ):
            yield chunk


def build_llm_router(
    delegate: LLMProviderProtocol,
    routing_config: dict[str, Any],
    default_model: str = "main",
) -> LLMRouter:
    """Build an LLMRouter from ``llm_config.yaml`` routing configuration.

    Always returns a router. When no routing rules are configured, the
    router acts as a transparent pass-through that maps unknown hint
    strings (e.g. ``"reasoning"``, ``"planning"``) back to the default
    model alias. This is necessary because planning strategies always
    pass phase hints as the ``model`` parameter.

    Args:
        delegate: The underlying LLM provider.
        routing_config: The ``routing`` section from ``llm_config.yaml``.
            May be empty for default hint-only routing.
        default_model: Fallback model alias.

    Returns:
        Configured ``LLMRouter``.
    """
    rules: list[RoutingRule] = []

    if routing_config.get("enabled", False):
        rules = [
            RoutingRule(
                condition=r.get("condition", ""),
                model=r.get("model", default_model),
            )
            for r in routing_config.get("rules", [])
            if r.get("condition")
        ]

    # Extract known aliases from the delegate (if it's a LiteLLMService)
    known_aliases: frozenset[str] = frozenset()
    if hasattr(delegate, "models") and isinstance(delegate.models, dict):
        known_aliases = frozenset(delegate.models.keys())

    router_default = routing_config.get("default_model", default_model)

    logger.info(
        "llm_router.initialized",
        rule_count=len(rules),
        default_model=router_default,
        known_aliases=sorted(known_aliases),
        routing_enabled=routing_config.get("enabled", False),
    )

    return LLMRouter(
        delegate=delegate,
        rules=rules,
        default_model=router_default,
        known_aliases=known_aliases,
    )
