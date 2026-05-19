from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.application.executor import ProgressUpdate
from taskforce.application.executor import AgentExecutor
from taskforce.application.learning_service import LlmExtractingLearningService
from taskforce.core.domain.enums import EventType


def test_learning_service_rejects_ephemeral_case_artifacts() -> None:
    service = LlmExtractingLearningService(
        wiki_store=MagicMock(),
        llm_service=MagicMock(),
    )

    assert not service._is_future_relevant_fact(
        {
            "kind": "concepts",
            "slug": "mueller-case-draft",
            "title": "Mueller Draft",
            "body": "Concrete email draft for this run.",
            "tags": ["draft"],
            "future_relevance": "Only useful for this run.",
        }
    )


def test_learning_service_accepts_future_relevant_preferences() -> None:
    service = LlmExtractingLearningService(
        wiki_store=MagicMock(),
        llm_service=MagicMock(),
    )

    assert service._is_future_relevant_fact(
        {
            "kind": "preferences",
            "slug": "draft-only-palettenklaerung",
            "title": "Draft-only Palettenklaerung",
            "body": (
                "For Palettenklaerung workflows, produce local artifacts only."
            ),
            "tags": ["workflow"],
            "future_relevance": (
                "Applies to recurring Palettenklaerung requests."
            ),
        }
    )


def test_learning_service_rejects_missing_future_relevance() -> None:
    service = LlmExtractingLearningService(
        wiki_store=MagicMock(),
        llm_service=MagicMock(),
    )

    assert not service._is_future_relevant_fact(
        {
            "kind": "preferences",
            "slug": "palettenklaerung",
            "title": "Palettenklaerung",
            "body": "Use local artifacts for recurring workflows.",
            "tags": ["workflow"],
        }
    )


@pytest.mark.asyncio
async def test_post_mission_learning_skips_unsuccessful_missions() -> None:
    executor = AgentExecutor.__new__(AgentExecutor)
    executor.logger = MagicMock()
    agent = MagicMock()
    agent.context.messages = [{"role": "user", "content": "x"}]

    with patch(
        "taskforce.application.learning_service."
        "LlmExtractingLearningService.learn_from_mission",
        new_callable=AsyncMock,
    ) as learn_mock:
        await executor._run_post_mission_learning(
            mission="write `drafts/out.md`",
            agent=agent,
            profile="default",
            session_id="s1",
            mission_success=False,
        )

    learn_mock.assert_not_awaited()
    executor.logger.info.assert_called_with(
        "post_mission_learning_skipped",
        session_id="s1",
        reason="mission_not_successful",
    )


@pytest.mark.asyncio
async def test_salvaged_final_answer_skips_post_mission_learning() -> None:
    executor = AgentExecutor.__new__(AgentExecutor)
    executor.logger = MagicMock()
    executor._active_agents = {}
    executor._gateway = None
    executor._agent_pipeline = MagicMock()
    executor._error_handler = MagicMock()
    executor._resolve_session_id = MagicMock(return_value="s-salvaged")
    executor._emit_mission_started = AsyncMock()
    executor._emit_mission_completed = AsyncMock()
    executor._maybe_store_conversation_history = AsyncMock()
    executor._run_post_mission_learning = AsyncMock()

    async def fake_execute_streaming(*_: object, **__: object):
        yield ProgressUpdate(
            timestamp=datetime.now(UTC),
            event_type=EventType.FINAL_ANSWER,
            message="salvaged",
            details={
                "content": "partial",
                "salvaged": True,
                "salvage_reason": "stall",
            },
        )

    executor._execute_streaming = fake_execute_streaming
    agent = MagicMock()
    agent.clear_interrupt.return_value = None

    async for _ in executor.execute_mission_streaming(
        mission="write `drafts/out.md`",
        profile="default",
        agent=agent,
    ):
        pass

    executor._run_post_mission_learning.assert_not_awaited()
    executor._emit_mission_completed.assert_awaited()
    assert executor._emit_mission_completed.await_args.kwargs["success"] is False
