"""Tests for ConsolidationEngine."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from taskforce.core.domain.experience import SessionExperience, ToolCallExperience
from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.infrastructure.memory.consolidation_engine import ConsolidationEngine


@pytest.fixture
def mock_llm():
    """Mock LLM provider that returns structured JSON responses."""
    llm = AsyncMock()

    def _make_response(content: str):
        return {"content": content, "usage": {"total_tokens": 100}}

    # Default: return a valid JSON response
    llm.complete = AsyncMock(
        return_value=_make_response(
            json.dumps(
                {
                    "narrative": "Agent analyzed data successfully.",
                    "key_learnings": ["Use pandas for data analysis"],
                    "tool_patterns": ["python", "file_read"],
                    "memory_kind": "procedural",
                }
            )
        )
    )
    return llm


@pytest.fixture
def mock_memory_store():
    store = AsyncMock()
    store.add = AsyncMock(side_effect=lambda r: r)
    store.get = AsyncMock(return_value=None)
    store.list = AsyncMock(return_value=[])
    store.update = AsyncMock(side_effect=lambda r: r)
    return store


@pytest.fixture
def engine(mock_llm, mock_memory_store):
    return ConsolidationEngine(mock_llm, mock_memory_store)


def _make_experience(session_id: str = "sess-1") -> SessionExperience:
    exp = SessionExperience(
        session_id=session_id,
        profile="dev",
        mission="Analyze data",
        started_at=datetime.now(UTC),
        total_steps=5,
        final_answer="Done.",
    )
    exp.tool_calls.append(
        ToolCallExperience(
            tool_name="python",
            arguments={"code": "import pandas"},
            success=True,
            duration_ms=100,
        )
    )
    return exp


class TestConsolidationEngine:
    async def test_consolidate_empty_experiences(self, engine):
        result = await engine.consolidate([], [])
        assert result.sessions_processed == 0
        assert result.memories_created == 0

    async def test_consolidate_immediate_creates_memories(
        self, engine, mock_llm, mock_memory_store
    ):
        """Immediate strategy: summarize + write, skip pattern detection."""
        exp = _make_experience()

        # Configure LLM responses for each phase.
        # Phase 3 (contradictions) is skipped when existing_memories is empty,
        # so only phase 1 (summarize) and phase 5 (quality) call the LLM.
        responses = [
            # Phase 1: Summarize
            {
                "content": json.dumps(
                    {
                        "narrative": "Agent used pandas for data analysis.",
                        "key_learnings": ["Use pandas for tabular data"],
                        "tool_patterns": ["python"],
                        "memory_kind": "procedural",
                    }
                ),
                "usage": {"total_tokens": 100},
            },
            # Phase 5: Quality
            {
                "content": json.dumps({"score": 0.8, "reasoning": "Good"}),
                "usage": {"total_tokens": 30},
            },
        ]
        mock_llm.complete = AsyncMock(side_effect=responses)

        result = await engine.consolidate([exp], [], strategy="immediate")

        assert result.sessions_processed == 1
        assert result.memories_created >= 1
        assert result.quality_score == 0.8
        assert result.ended_at is not None
        mock_memory_store.add.assert_awaited()

    async def test_consolidate_batch_includes_pattern_detection(
        self, engine, mock_llm, mock_memory_store
    ):
        """Batch strategy: includes cross-session pattern detection."""
        exp1 = _make_experience("sess-1")
        exp2 = _make_experience("sess-2")

        # Phase 3 (contradictions) is skipped when existing_memories=[],
        # so LLM calls are: summarize1, summarize2, pattern_detect, quality.
        responses = [
            # Phase 1: Summarize sess-1
            {
                "content": json.dumps(
                    {
                        "narrative": "Session 1 analysis.",
                        "key_learnings": ["Learning 1"],
                        "tool_patterns": ["python"],
                        "memory_kind": "semantic",
                    }
                ),
                "usage": {"total_tokens": 100},
            },
            # Phase 1: Summarize sess-2
            {
                "content": json.dumps(
                    {
                        "narrative": "Session 2 analysis.",
                        "key_learnings": ["Learning 2"],
                        "tool_patterns": ["python"],
                        "memory_kind": "semantic",
                    }
                ),
                "usage": {"total_tokens": 100},
            },
            # Phase 2: Pattern detection
            {
                "content": json.dumps(
                    [
                        {
                            "pattern": "Agent consistently uses Python.",
                            "frequency": 2,
                            "confidence": 0.9,
                            "memory_kind": "procedural",
                            "tags": ["python"],
                        }
                    ]
                ),
                "usage": {"total_tokens": 80},
            },
            # Phase 5: Quality
            {
                "content": json.dumps({"score": 0.9, "reasoning": "Great"}),
                "usage": {"total_tokens": 30},
            },
        ]
        mock_llm.complete = AsyncMock(side_effect=responses)

        result = await engine.consolidate([exp1, exp2], [], strategy="batch")

        assert result.sessions_processed == 2
        # 2 learnings from summaries + 1 pattern
        assert result.memories_created >= 3
        assert result.quality_score == 0.9

    async def test_contradiction_resolution(self, engine, mock_llm, mock_memory_store):
        """Test that contradictions are handled (update/retire)."""
        exp = _make_experience()
        existing = MemoryRecord(
            id="existing-1",
            scope=MemoryScope.USER,
            kind=MemoryKind.CONSOLIDATED,
            content="Use numpy for data analysis",
        )

        responses = [
            # Phase 1: Summarize
            {
                "content": json.dumps(
                    {
                        "narrative": "Agent used pandas.",
                        "key_learnings": ["Use pandas instead of numpy"],
                        "tool_patterns": ["python"],
                        "memory_kind": "procedural",
                    }
                ),
                "usage": {"total_tokens": 100},
            },
            # Phase 3: Contradiction detected
            {
                "content": json.dumps(
                    {
                        "contradictions": [
                            {
                                "new_learning": "Use pandas instead of numpy",
                                "existing_memory_id": "existing-1",
                                "resolution": "keep_new",
                            }
                        ]
                    }
                ),
                "usage": {"total_tokens": 50},
            },
            # Phase 5: Quality
            {
                "content": json.dumps({"score": 0.7, "reasoning": "OK"}),
                "usage": {"total_tokens": 30},
            },
        ]
        mock_llm.complete = AsyncMock(side_effect=responses)
        mock_memory_store.get = AsyncMock(return_value=existing)

        result = await engine.consolidate([exp], [existing], strategy="immediate")

        assert result.contradictions_resolved == 1
        assert result.memories_retired >= 1

    async def test_llm_failure_handled_gracefully(self, engine, mock_llm, mock_memory_store):
        """Engine should not crash if LLM returns invalid JSON."""
        exp = _make_experience()
        mock_llm.complete = AsyncMock(
            return_value={"content": "not json at all", "usage": {"total_tokens": 0}}
        )

        result = await engine.consolidate([exp], [], strategy="immediate")
        # Should complete without error, with 0 memories
        assert result.sessions_processed == 1
        assert result.ended_at is not None
