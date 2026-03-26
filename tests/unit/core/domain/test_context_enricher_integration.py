"""Integration tests for context enricher within the Agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from taskforce.core.domain.context_enricher import EnricherConfig
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.infrastructure.memory.slm_context_enricher import SLMContextEnricher


def _make_memory(content: str) -> MemoryRecord:
    return MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.LONG_TERM,
        content=content,
        tags=["test"],
    )


def _make_memory_store(memories: list[MemoryRecord]) -> AsyncMock:
    store = AsyncMock()
    store.list = AsyncMock(return_value=memories)
    store.search = AsyncMock(return_value=memories)
    return store


async def test_agent_enrichment_context_injected_into_prompt() -> None:
    """Verify enrichment context appears in the built system prompt."""
    from taskforce.core.domain.lean_agent import Agent

    slm_output = "[Factual]\n- The API limit is 5000 requests."
    llm_mock = AsyncMock()
    llm_mock.complete = AsyncMock(return_value={"content": slm_output})

    memories = [_make_memory("API limit is 5000")]
    memory_store = _make_memory_store(memories)

    config = EnricherConfig(enabled=True, model_alias="slm")
    enricher = SLMContextEnricher(llm_provider=llm_mock, config=config)

    logger_mock = Mock()
    logger_mock.debug = Mock()
    logger_mock.info = Mock()
    logger_mock.warning = Mock()
    logger_mock.bind = Mock(return_value=logger_mock)

    state_manager = AsyncMock()
    state_manager.save_state = AsyncMock()
    state_manager.load_state = AsyncMock(return_value=None)

    agent = Agent(
        state_manager=state_manager,
        llm_provider=llm_mock,
        tools=[],
        logger=logger_mock,
        memory_store=memory_store,
        context_enricher=enricher,
    )

    # Run enrichment
    await agent.run_context_enrichment(mission="Check the API rate limit")

    # Verify enrichment result was cached
    assert agent._enrichment_context is not None
    assert "Internal Intuition" in agent._enrichment_context
    assert "5000" in agent._enrichment_context

    # Verify it appears in the system prompt
    prompt = agent._build_system_prompt(mission="Check the API rate limit")
    assert "Internal Intuition" in prompt


async def test_agent_without_enricher_works_normally() -> None:
    """Agent without enricher does not fail and has no enrichment context."""
    from taskforce.core.domain.lean_agent import Agent

    logger_mock = Mock()
    logger_mock.debug = Mock()
    logger_mock.info = Mock()
    logger_mock.warning = Mock()
    logger_mock.bind = Mock(return_value=logger_mock)

    state_manager = AsyncMock()
    state_manager.save_state = AsyncMock()
    state_manager.load_state = AsyncMock(return_value=None)

    llm_mock = AsyncMock()

    agent = Agent(
        state_manager=state_manager,
        llm_provider=llm_mock,
        tools=[],
        logger=logger_mock,
    )

    # Should be a no-op
    await agent.run_context_enrichment(mission="Do something")

    assert agent._enrichment_context is None
    prompt = agent._build_system_prompt(mission="Do something")
    assert "Internal Intuition" not in prompt


async def test_agent_enrichment_failure_is_graceful() -> None:
    """Enricher failure does not crash the agent."""
    from taskforce.core.domain.lean_agent import Agent

    llm_mock = AsyncMock()
    llm_mock.complete = AsyncMock(side_effect=RuntimeError("SLM offline"))

    memory_store = _make_memory_store([_make_memory("some fact")])
    config = EnricherConfig(enabled=True, timeout_seconds=2.0)
    enricher = SLMContextEnricher(llm_provider=llm_mock, config=config)

    logger_mock = Mock()
    logger_mock.debug = Mock()
    logger_mock.info = Mock()
    logger_mock.warning = Mock()
    logger_mock.bind = Mock(return_value=logger_mock)

    state_manager = AsyncMock()
    state_manager.save_state = AsyncMock()
    state_manager.load_state = AsyncMock(return_value=None)

    agent = Agent(
        state_manager=state_manager,
        llm_provider=llm_mock,
        tools=[],
        logger=logger_mock,
        memory_store=memory_store,
        context_enricher=enricher,
    )

    # Should not raise
    await agent.run_context_enrichment(mission="Fix something")

    assert agent._enrichment_context is None
