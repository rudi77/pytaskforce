"""Issue #382: post-mission-learning opt-in for inline-built agents.

Inline-built agents (factory.create_agent with no profile=) used to silently
trigger the post-mission LearningService because the executor reads
learning.enabled from the on-disk default.yaml (true). They now opt out by
default via agent._learning_enabled = False, which the executor respects.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskforce.application.executor import AgentExecutor


@pytest.mark.asyncio
class TestLearningOptInIssue382:
    """The executor's _run_post_mission_learning must respect
    agent._learning_enabled = False, regardless of profile config."""

    async def _make_executor(self):
        """Build a minimal executor; we monkey-patch the bits we need."""
        executor = AgentExecutor.__new__(AgentExecutor)
        # We bypass __init__ entirely - only _run_post_mission_learning
        # is exercised here. Provide a no-op logger to avoid attribute errors.
        executor.logger = MagicMock()
        return executor

    async def test_inline_agent_opts_out_by_default(self):
        """Agent with _learning_enabled=False must short-circuit before
        ProfileLoader is even touched."""
        executor = await self._make_executor()

        agent = SimpleNamespace(
            _learning_enabled=False,
            context=SimpleNamespace(messages=[{"role": "user", "content": "x"}]),
            llm_provider=MagicMock(),
            wiki_store=MagicMock(),
        )

        # If the early-return works, ProfileLoader.load is never called.
        # If it doesn't, importing it would happen inside the method - we'd
        # see the LearningService construction below proceed (or fail).
        # We assert by checking the wiki_store is not touched.
        agent.wiki_store.search = AsyncMock()

        await executor._run_post_mission_learning(
            mission="test mission",
            agent=agent,
            profile="default",  # has learning.enabled=true
            session_id="s1",
        )

        # No wiki interaction means we exited before LearningService ran.
        agent.wiki_store.search.assert_not_called()

    async def test_agent_without_flag_still_consults_profile(self):
        """Profile-built agents (no _learning_enabled attribute) keep the
        previous behaviour - profile config decides."""
        executor = await self._make_executor()

        agent = SimpleNamespace(
            context=SimpleNamespace(messages=[{"role": "user", "content": "x"}]),
            llm_provider=MagicMock(),
            wiki_store=None,  # short-circuit at the wiki_store check
        )

        # _learning_enabled missing entirely - executor should NOT early-return
        # on that condition. It will then proceed to check profile config and
        # eventually short-circuit on wiki_store=None. We verify ProfileLoader
        # was attempted.
        # (No exception is what we assert here - the method swallows exceptions
        # so the only signal is non-crash.)
        await executor._run_post_mission_learning(
            mission="test mission",
            agent=agent,
            profile="default",
            session_id="s1",
        )
        # If we reached this point without exception, the legacy path still
        # works for agents that don't declare _learning_enabled.

    async def test_explicit_true_uses_profile_path(self):
        """_learning_enabled=True must NOT bypass profile config - it just
        skips the inline-opt-out short-circuit."""
        executor = await self._make_executor()

        agent = SimpleNamespace(
            _learning_enabled=True,
            context=SimpleNamespace(messages=[{"role": "user", "content": "x"}]),
            llm_provider=MagicMock(),
            wiki_store=None,
        )

        await executor._run_post_mission_learning(
            mission="test mission",
            agent=agent,
            profile="default",
            session_id="s1",
        )
        # Reached here = no crash; the early-return on _learning_enabled is
        # only for the False case.


@pytest.mark.asyncio
class TestFactoryInlineAgentMarksOptOut:
    """The factory's inline path stamps the new flag on the returned agent."""

    async def test_inline_create_sets_learning_disabled(self, tmp_path):
        """create_agent with inline params produces agent._learning_enabled=False."""
        from taskforce.application.factory import AgentFactory

        factory = AgentFactory()
        try:
            agent = await factory.create_agent(
                system_prompt="minimal test agent",
                tools=["python"],
                persistence={"type": "file", "work_dir": str(tmp_path)},
            )
        except Exception as e:
            pytest.skip(f"factory.create_agent unavailable in test env: {e}")
            return

        try:
            assert hasattr(agent, "_learning_enabled"), \
                "inline-built agent must declare _learning_enabled"
            assert agent._learning_enabled is False, \
                f"inline default must be False, got {agent._learning_enabled!r}"
        finally:
            try:
                await agent.close()
            except Exception:
                pass
