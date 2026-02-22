"""
Unit tests for LLMRouter — dynamic per-call model selection.

Tests cover:
- Hint-based routing (planning, reasoning, reflecting, summarizing, acting)
- Context-based routing (has_tools, no_tools, message_count)
- Fallback to default model when no rules match
- Known alias pass-through (explicit alias always wins)
- Rule ordering (first match wins)
- build_llm_router factory function
- Backward compatibility (empty routing config)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.infrastructure.llm.llm_router import (
    LLMRouter,
    RoutingRule,
    build_llm_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_delegate():
    """Create a mock LLM provider delegate."""
    delegate = MagicMock()
    delegate.models = {"main": "gpt-4.1", "fast": "gpt-4.1-mini", "powerful": "gpt-5"}
    delegate.complete = AsyncMock(return_value={"success": True, "content": "test"})
    delegate.generate = AsyncMock(return_value={"success": True, "content": "test"})

    # complete_stream needs to be an async generator
    async def mock_stream(**kwargs):
        yield {"type": "token", "content": "hello"}
        yield {"type": "done", "usage": {"total_tokens": 10}}

    delegate.complete_stream = mock_stream
    return delegate


@pytest.fixture
def sample_rules():
    """Standard routing rules for testing."""
    return [
        RoutingRule(condition="hint:planning", model="powerful"),
        RoutingRule(condition="hint:reasoning", model="powerful"),
        RoutingRule(condition="hint:reflecting", model="powerful"),
        RoutingRule(condition="hint:summarizing", model="fast"),
        RoutingRule(condition="hint:acting", model="main"),
        RoutingRule(condition="has_tools", model="main"),
        RoutingRule(condition="no_tools", model="fast"),
    ]


@pytest.fixture
def router(mock_delegate, sample_rules):
    """Create a router with standard rules."""
    return LLMRouter(
        delegate=mock_delegate,
        rules=sample_rules,
        default_model="main",
        known_aliases=frozenset(mock_delegate.models.keys()),
    )


@pytest.fixture
def empty_router(mock_delegate):
    """Create a router with no rules (pass-through mode)."""
    return LLMRouter(
        delegate=mock_delegate,
        rules=[],
        default_model="main",
        known_aliases=frozenset(mock_delegate.models.keys()),
    )


# ---------------------------------------------------------------------------
# _select_model tests
# ---------------------------------------------------------------------------

class TestSelectModel:
    """Tests for the internal _select_model routing logic."""

    def test_hint_planning_routes_to_powerful(self, router):
        result = router._select_model("planning", [], None)
        assert result == "powerful"

    def test_hint_reasoning_routes_to_powerful(self, router):
        result = router._select_model("reasoning", [], None)
        assert result == "powerful"

    def test_hint_reflecting_routes_to_powerful(self, router):
        result = router._select_model("reflecting", [], None)
        assert result == "powerful"

    def test_hint_summarizing_routes_to_fast(self, router):
        result = router._select_model("summarizing", [], None)
        assert result == "fast"

    def test_hint_acting_routes_to_main(self, router):
        result = router._select_model("acting", [], None)
        assert result == "main"

    def test_known_alias_passes_through(self, router):
        """Explicit known aliases bypass all routing rules."""
        result = router._select_model("fast", [], None)
        assert result == "fast"

    def test_known_alias_with_tools(self, router):
        """Even with tools, explicit alias wins."""
        tools = [{"type": "function", "function": {"name": "test"}}]
        result = router._select_model("powerful", [], tools)
        assert result == "powerful"

    def test_has_tools_matches(self, router):
        """When no hint is given and tools are present, has_tools matches."""
        tools = [{"type": "function", "function": {"name": "test"}}]
        result = router._select_model(None, [], tools)
        assert result == "main"

    def test_no_tools_matches(self, router):
        """When no hint is given and no tools, no_tools matches."""
        result = router._select_model(None, [], None)
        assert result == "fast"

    def test_no_tools_empty_list(self, router):
        """Empty tools list also triggers no_tools."""
        result = router._select_model(None, [], [])
        assert result == "fast"

    def test_message_count_rule(self, mock_delegate):
        """message_count > N matches when messages exceed threshold."""
        router = LLMRouter(
            delegate=mock_delegate,
            rules=[RoutingRule(condition="message_count > 5", model="powerful")],
            default_model="main",
            known_aliases=frozenset(mock_delegate.models.keys()),
        )
        short_messages = [{"role": "user", "content": "hi"}] * 3
        long_messages = [{"role": "user", "content": "hi"}] * 10

        assert router._select_model(None, short_messages, None) == "main"
        assert router._select_model(None, long_messages, None) == "powerful"

    def test_message_count_boundary(self, mock_delegate):
        """Exact boundary: > 5 means 6 messages match, 5 don't."""
        router = LLMRouter(
            delegate=mock_delegate,
            rules=[RoutingRule(condition="message_count > 5", model="powerful")],
            default_model="main",
            known_aliases=frozenset(mock_delegate.models.keys()),
        )
        five_messages = [{"role": "user", "content": "hi"}] * 5
        six_messages = [{"role": "user", "content": "hi"}] * 6

        assert router._select_model(None, five_messages, None) == "main"
        assert router._select_model(None, six_messages, None) == "powerful"

    def test_first_rule_wins(self, mock_delegate):
        """When multiple rules could match, first one wins."""
        router = LLMRouter(
            delegate=mock_delegate,
            rules=[
                RoutingRule(condition="has_tools", model="fast"),
                RoutingRule(condition="has_tools", model="powerful"),
            ],
            default_model="main",
            known_aliases=frozenset(),
        )
        tools = [{"type": "function", "function": {"name": "test"}}]
        assert router._select_model(None, [], tools) == "fast"

    def test_unknown_hint_falls_back_to_default(self, router):
        """Unknown hint (not a known alias) falls back to default_model."""
        result = router._select_model("unknown_phase", [], None)
        # "unknown_phase" is not a known alias, and no hint:unknown_phase rule
        # exists, so it falls through to has_tools/no_tools.
        # With no tools, "no_tools" matches → fast
        assert result == "fast"

    def test_none_model_with_no_rules_returns_default(self, empty_router):
        """With no rules and no hint, return default_model."""
        result = empty_router._select_model(None, [], None)
        assert result == "main"

    def test_hint_with_no_rules_returns_default(self, empty_router):
        """With no rules, hints fall back to default_model."""
        result = empty_router._select_model("reasoning", [], None)
        assert result == "main"

    def test_invalid_message_count_rule(self, mock_delegate):
        """Malformed message_count condition is ignored gracefully."""
        router = LLMRouter(
            delegate=mock_delegate,
            rules=[RoutingRule(condition="message_count > abc", model="powerful")],
            default_model="main",
            known_aliases=frozenset(),
        )
        result = router._select_model(None, [{"role": "user"}] * 20, None)
        assert result == "main"


# ---------------------------------------------------------------------------
# Protocol method tests (complete, generate, complete_stream)
# ---------------------------------------------------------------------------

class TestComplete:
    """Tests for the routed complete() method."""

    @pytest.mark.asyncio
    async def test_routes_hint_to_correct_model(self, router, mock_delegate):
        await router.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="planning",
        )
        mock_delegate.complete.assert_called_once()
        call_kwargs = mock_delegate.complete.call_args
        assert call_kwargs.kwargs["model"] == "powerful"

    @pytest.mark.asyncio
    async def test_routes_with_tools(self, router, mock_delegate):
        tools = [{"type": "function", "function": {"name": "test"}}]
        await router.complete(
            messages=[{"role": "user", "content": "hi"}],
            model=None,
            tools=tools,
        )
        mock_delegate.complete.assert_called_once()
        assert mock_delegate.complete.call_args.kwargs["model"] == "main"

    @pytest.mark.asyncio
    async def test_passes_through_kwargs(self, router, mock_delegate):
        await router.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="reasoning",
            temperature=0.5,
            max_tokens=100,
        )
        call_kwargs = mock_delegate.complete.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_passes_tool_choice(self, router, mock_delegate):
        await router.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="reasoning",
            tools=[{"type": "function", "function": {"name": "test"}}],
            tool_choice="auto",
        )
        assert mock_delegate.complete.call_args.kwargs["tool_choice"] == "auto"


class TestGenerate:
    """Tests for the routed generate() method."""

    @pytest.mark.asyncio
    async def test_known_alias_passes_through(self, router, mock_delegate):
        await router.generate(prompt="test", model="fast")
        assert mock_delegate.generate.call_args.kwargs["model"] == "fast"

    @pytest.mark.asyncio
    async def test_unknown_model_uses_default(self, router, mock_delegate):
        await router.generate(prompt="test", model="unknown")
        assert mock_delegate.generate.call_args.kwargs["model"] == "main"

    @pytest.mark.asyncio
    async def test_none_model_uses_default(self, router, mock_delegate):
        await router.generate(prompt="test", model=None)
        assert mock_delegate.generate.call_args.kwargs["model"] == "main"


class TestCompleteStream:
    """Tests for the routed complete_stream() method."""

    @pytest.mark.asyncio
    async def test_routes_hint_and_yields_chunks(self, mock_delegate):
        """Verify routing and that all chunks are yielded."""
        call_log = []

        async def mock_stream(messages, model, tools, tool_choice, **kwargs):
            call_log.append(model)
            yield {"type": "token", "content": "hello"}
            yield {"type": "done", "usage": {"total_tokens": 5}}

        mock_delegate.complete_stream = mock_stream

        router = LLMRouter(
            delegate=mock_delegate,
            rules=[RoutingRule(condition="hint:summarizing", model="fast")],
            default_model="main",
            known_aliases=frozenset(mock_delegate.models.keys()),
        )

        chunks = []
        async for chunk in router.complete_stream(
            messages=[{"role": "user", "content": "hi"}],
            model="summarizing",
        ):
            chunks.append(chunk)

        assert call_log == ["fast"]
        assert len(chunks) == 2
        assert chunks[0]["content"] == "hello"
        assert chunks[1]["type"] == "done"


# ---------------------------------------------------------------------------
# build_llm_router factory tests
# ---------------------------------------------------------------------------

class TestBuildLlmRouter:
    """Tests for the build_llm_router factory function."""

    def test_returns_router_with_empty_config(self, mock_delegate):
        """Empty config → router with no rules (pass-through)."""
        router = build_llm_router(mock_delegate, {}, default_model="main")
        assert isinstance(router, LLMRouter)
        assert len(router.rules) == 0
        assert router.default_model == "main"

    def test_returns_router_when_routing_disabled(self, mock_delegate):
        """Explicitly disabled routing → router with no rules."""
        config = {"enabled": False}
        router = build_llm_router(mock_delegate, config, default_model="main")
        assert isinstance(router, LLMRouter)
        assert len(router.rules) == 0

    def test_returns_router_with_rules_when_enabled(self, mock_delegate):
        """Enabled routing with rules → router with rules."""
        config = {
            "enabled": True,
            "rules": [
                {"condition": "hint:planning", "model": "powerful"},
                {"condition": "has_tools", "model": "main"},
            ],
        }
        router = build_llm_router(mock_delegate, config, default_model="main")
        assert isinstance(router, LLMRouter)
        assert len(router.rules) == 2
        assert router.rules[0].condition == "hint:planning"
        assert router.rules[0].model == "powerful"

    def test_extracts_known_aliases_from_delegate(self, mock_delegate):
        """Known aliases are extracted from delegate.models dict."""
        router = build_llm_router(mock_delegate, {}, default_model="main")
        assert "main" in router.known_aliases
        assert "fast" in router.known_aliases
        assert "powerful" in router.known_aliases

    def test_handles_delegate_without_models_attr(self):
        """Delegate without .models attribute → empty known_aliases."""
        delegate = MagicMock(spec=[])  # No attributes
        router = build_llm_router(delegate, {}, default_model="main")
        assert len(router.known_aliases) == 0

    def test_skips_rules_without_condition(self, mock_delegate):
        """Rules with empty/missing condition are skipped."""
        config = {
            "enabled": True,
            "rules": [
                {"condition": "", "model": "fast"},
                {"model": "powerful"},  # no condition key
                {"condition": "has_tools", "model": "main"},
            ],
        }
        router = build_llm_router(mock_delegate, config, default_model="main")
        assert len(router.rules) == 1
        assert router.rules[0].condition == "has_tools"

    def test_respects_routing_default_model(self, mock_delegate):
        """routing.default_model overrides the passed default."""
        config = {"default_model": "fast"}
        router = build_llm_router(mock_delegate, config, default_model="main")
        assert router.default_model == "fast"


# ---------------------------------------------------------------------------
# Backward compatibility / integration-style tests
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Ensure the router is backward-compatible with existing agent usage."""

    @pytest.mark.asyncio
    async def test_no_routing_config_uses_default_for_hints(self, mock_delegate):
        """Without routing rules, phase hints fall back to default model."""
        router = build_llm_router(mock_delegate, {}, default_model="main")

        # Strategy passes "reasoning" hint → should resolve to "main"
        await router.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="reasoning",
        )
        assert mock_delegate.complete.call_args.kwargs["model"] == "main"

    @pytest.mark.asyncio
    async def test_no_routing_config_preserves_known_alias(self, mock_delegate):
        """Without routing rules, known aliases still pass through."""
        router = build_llm_router(mock_delegate, {}, default_model="main")

        await router.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="fast",
        )
        assert mock_delegate.complete.call_args.kwargs["model"] == "fast"

    @pytest.mark.asyncio
    async def test_all_strategy_hints_resolve(self, mock_delegate):
        """All strategy phase hints are handled without error."""
        router = build_llm_router(mock_delegate, {}, default_model="main")
        hints = ["planning", "reasoning", "acting", "reflecting", "summarizing"]

        for hint in hints:
            mock_delegate.complete.reset_mock()
            await router.complete(
                messages=[{"role": "user", "content": "test"}],
                model=hint,
            )
            resolved = mock_delegate.complete.call_args.kwargs["model"]
            # Without rules, all hints fall back to default
            assert resolved == "main", f"Hint '{hint}' resolved to '{resolved}', expected 'main'"


# ---------------------------------------------------------------------------
# Integration-style: routing_config from LiteLLMService
# ---------------------------------------------------------------------------

class TestRoutingConfigFromDelegate:
    """Tests for routing config extraction from the delegate provider."""

    def test_delegate_with_routing_config(self):
        """Router uses routing_config from delegate when provided."""
        delegate = MagicMock()
        delegate.models = {"main": "gpt-4.1", "fast": "gpt-4.1-mini"}
        delegate.routing_config = {
            "enabled": True,
            "rules": [{"condition": "hint:planning", "model": "fast"}],
        }

        router = build_llm_router(
            delegate,
            delegate.routing_config,
            default_model="main",
        )
        assert len(router.rules) == 1
        assert router.rules[0].model == "fast"

    def test_delegate_without_routing_config_uses_empty_dict(self):
        """Delegates without routing_config → getattr fallback to {}."""
        delegate = MagicMock(spec=[])  # No attributes at all
        routing_config = getattr(delegate, "routing_config", {})

        router = build_llm_router(delegate, routing_config, default_model="main")
        assert len(router.rules) == 0
        assert router.default_model == "main"

    @pytest.mark.asyncio
    async def test_custom_provider_without_routing_config_works(self):
        """Custom LLM provider without routing_config doesn't crash."""
        # Use spec to limit mock attributes — a real custom provider
        # wouldn't have routing_config or default_model attributes.
        delegate = AsyncMock(spec=["complete", "generate", "complete_stream"])
        delegate.complete = AsyncMock(return_value={"success": True, "content": "hi"})

        # Simulate what infrastructure_builder does
        routing_config = getattr(delegate, "routing_config", {})
        default_model = getattr(delegate, "default_model", "main")

        router = build_llm_router(delegate, routing_config, default_model)
        assert isinstance(router, LLMRouter)

        # Phase hints should fall back to default
        await router.complete(
            messages=[{"role": "user", "content": "test"}],
            model="reasoning",
        )
        assert delegate.complete.call_args.kwargs["model"] == "main"

    def test_alias_named_like_hint_takes_priority(self):
        """If a model alias matches a hint name, the alias wins."""
        delegate = MagicMock()
        delegate.models = {"planning": "gpt-5", "main": "gpt-4.1"}

        router = build_llm_router(
            delegate,
            {"enabled": True, "rules": [{"condition": "hint:planning", "model": "main"}]},
            default_model="main",
        )

        # "planning" is a known alias → passes through, hint rule is NOT evaluated
        result = router._select_model("planning", [], None)
        assert result == "planning"
