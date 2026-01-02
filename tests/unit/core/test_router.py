"""
Unit tests for QueryRouter classification logic.

Tests the router's ability to correctly classify queries as
follow-up (fast path) or new mission (full planning path).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from taskforce.core.domain.router import (
    QueryRouter,
    RouterContext,
    RouterResult,
    RouteDecision,
)


@pytest.fixture
def router():
    """Create a QueryRouter instance without LLM classification."""
    return QueryRouter(use_llm_classification=False)


@pytest.fixture
def router_with_llm():
    """Create a QueryRouter with mocked LLM provider."""
    mock_llm = AsyncMock()
    return QueryRouter(
        llm_provider=mock_llm,
        use_llm_classification=True,
    )


class TestRouteDecision:
    """Test RouteDecision enum."""

    def test_route_decision_values(self):
        """Test RouteDecision enum has expected values."""
        assert RouteDecision.NEW_MISSION.value == "new_mission"
        assert RouteDecision.FOLLOW_UP.value == "follow_up"


class TestRouterContext:
    """Test RouterContext dataclass."""

    def test_router_context_creation_minimal(self):
        """Test creating RouterContext with minimal fields."""
        context = RouterContext(
            query="Test query",
            has_active_todolist=False,
            todolist_completed=False,
            previous_results=[],
            conversation_history=[],
        )

        assert context.query == "Test query"
        assert context.has_active_todolist is False
        assert context.todolist_completed is False
        assert context.previous_results == []
        assert context.conversation_history == []
        assert context.last_query is None

    def test_router_context_creation_full(self):
        """Test creating RouterContext with all fields."""
        context = RouterContext(
            query="Test query",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"step": 1, "result": {"data": "test"}}],
            conversation_history=[{"role": "user", "content": "hello"}],
            last_query="Previous query",
        )

        assert context.has_active_todolist is True
        assert context.todolist_completed is True
        assert len(context.previous_results) == 1
        assert context.last_query == "Previous query"


class TestRouterResult:
    """Test RouterResult dataclass."""

    def test_router_result_creation(self):
        """Test creating RouterResult."""
        result = RouterResult(
            decision=RouteDecision.FOLLOW_UP,
            confidence=0.85,
            rationale="Short query with question word",
        )

        assert result.decision == RouteDecision.FOLLOW_UP
        assert result.confidence == 0.85
        assert result.rationale == "Short query with question word"


class TestQueryRouterNoContext:
    """Test router behavior when there's no active context."""

    @pytest.mark.asyncio
    async def test_new_mission_without_context(self, router):
        """Query without context should be classified as new mission."""
        context = RouterContext(
            query="Create a REST API for user management",
            has_active_todolist=False,
            todolist_completed=False,
            previous_results=[],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.NEW_MISSION
        assert result.confidence == 1.0
        assert "No active context" in result.rationale


class TestQueryRouterHeuristics:
    """Test heuristic-based classification."""

    @pytest.mark.asyncio
    async def test_follow_up_short_german_question(self, router):
        """Short German question should be classified as follow-up."""
        context = RouterContext(
            query="Was steht da drin?",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "wiki_get_page", "result": {"content": "..."}}],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.FOLLOW_UP
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_follow_up_short_english_question(self, router):
        """Short English question should be classified as follow-up."""
        context = RouterContext(
            query="What does it say?",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "file_read", "result": {"content": "..."}}],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.FOLLOW_UP
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_follow_up_with_pronoun_reference(self, router):
        """Query with pronouns referencing previous context."""
        context = RouterContext(
            query="Erkläre das genauer",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[
                {"tool": "file_read", "result": {"content": "Complex explanation..."}}
            ],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.FOLLOW_UP
        assert result.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_follow_up_continuation_word(self, router):
        """Query starting with continuation word."""
        context = RouterContext(
            query="And what about the other files?",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "file_read", "result": {}}],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.FOLLOW_UP

    @pytest.mark.asyncio
    async def test_new_mission_pattern_override(self, router):
        """New mission patterns should override follow-up heuristics."""
        context = RouterContext(
            query="Erstelle ein neues Projekt für die API",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "wiki_get_page", "result": {}}],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.NEW_MISSION
        assert result.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_new_mission_create_pattern(self, router):
        """Query with create/build pattern should be new mission."""
        context = RouterContext(
            query="Create a new Python project with FastAPI",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.NEW_MISSION

    @pytest.mark.asyncio
    async def test_new_mission_analyze_pattern(self, router):
        """Query with analyze pattern should be new mission."""
        context = RouterContext(
            query="Analyze the data in the logs folder",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.NEW_MISSION

    @pytest.mark.asyncio
    async def test_long_query_is_new_mission(self, router):
        """Long queries should be classified as new missions."""
        long_query = (
            "Ich möchte eine komplette Analyse der Verkaufsdaten durchführen, "
            * 10
        )

        context = RouterContext(
            query=long_query,
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[],
            conversation_history=[],
        )

        result = await router.classify(context)

        assert result.decision == RouteDecision.NEW_MISSION
        assert result.confidence >= 0.7


class TestQueryRouterContextReferences:
    """Test detection of context references in queries."""

    def test_references_previous_context_pronoun(self, router):
        """Test detection of pronoun references."""
        context = RouterContext(
            query="Tell me more about that",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "search", "result": {"data": "test"}}],
            conversation_history=[],
        )

        assert router._references_previous_context(context) is True

    def test_references_previous_context_german_pronoun(self, router):
        """Test detection of German pronoun references."""
        context = RouterContext(
            query="Erkläre das bitte",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "wiki", "result": {}}],
            conversation_history=[],
        )

        assert router._references_previous_context(context) is True

    def test_no_context_reference(self, router):
        """Test query without context references."""
        context = RouterContext(
            query="Write a Python function",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "search", "result": {"data": "test"}}],
            conversation_history=[],
        )

        assert router._references_previous_context(context) is False


class TestQueryRouterLLMFallback:
    """Test LLM-based classification fallback."""

    @pytest.mark.asyncio
    async def test_llm_classification_success(self, router_with_llm):
        """Test successful LLM classification."""
        router_with_llm.llm_provider.complete.return_value = {
            "success": True,
            "content": '{"decision": "follow_up", "confidence": 0.9, "rationale": "Simple clarification question"}'
        }

        context = RouterContext(
            query="Can you clarify?",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "search", "result": {}}],
            conversation_history=[],
        )

        result = await router_with_llm.classify(context)

        assert result.decision == RouteDecision.FOLLOW_UP
        assert result.confidence == 0.9
        assert "clarification" in result.rationale.lower()

    @pytest.mark.asyncio
    async def test_llm_classification_failure_fallback(self, router_with_llm):
        """Test fallback when LLM classification fails."""
        router_with_llm.llm_provider.complete.return_value = {
            "success": False,
            "error": "LLM error"
        }

        context = RouterContext(
            query="Something ambiguous",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "search", "result": {}}],
            conversation_history=[],
        )

        result = await router_with_llm.classify(context)

        # Should fallback to new mission
        assert result.decision == RouteDecision.NEW_MISSION
        assert "failed" in result.rationale.lower()


class TestQueryRouterApplyHeuristics:
    """Test the _apply_heuristics method directly."""

    def test_heuristics_new_mission_pattern(self, router):
        """Test heuristics detect new mission patterns."""
        context = RouterContext(
            query="Create a new project for the API",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[],
            conversation_history=[],
        )

        result = router._apply_heuristics(context)

        assert result.decision == RouteDecision.NEW_MISSION
        assert result.confidence == 0.9

    def test_heuristics_follow_up_short_question(self, router):
        """Test heuristics detect short follow-up questions."""
        context = RouterContext(
            query="How many are there?",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[{"tool": "list", "result": {}}],
            conversation_history=[],
        )

        result = router._apply_heuristics(context)

        assert result.decision == RouteDecision.FOLLOW_UP
        assert result.confidence == 0.8

    def test_heuristics_uncertain_defaults_to_new_mission(self, router):
        """Test uncertain queries default to new mission."""
        context = RouterContext(
            query="Something ambiguous here",
            has_active_todolist=True,
            todolist_completed=True,
            previous_results=[],
            conversation_history=[],
        )

        result = router._apply_heuristics(context)

        assert result.decision == RouteDecision.NEW_MISSION
        assert result.confidence == 0.5


class TestQueryRouterConfiguration:
    """Test router configuration options."""

    def test_custom_max_follow_up_length(self):
        """Test custom max follow-up length configuration."""
        router = QueryRouter(max_follow_up_length=50)
        assert router.MAX_FOLLOW_UP_LENGTH == 50

    def test_llm_classification_disabled_by_default(self):
        """Test LLM classification is disabled by default."""
        router = QueryRouter()
        assert router.use_llm_classification is False
        assert router.llm_provider is None

    def test_llm_classification_enabled(self):
        """Test LLM classification can be enabled."""
        mock_llm = MagicMock()
        router = QueryRouter(
            llm_provider=mock_llm,
            use_llm_classification=True,
        )
        assert router.use_llm_classification is True
        assert router.llm_provider is mock_llm

