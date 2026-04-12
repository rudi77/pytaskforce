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
        """Immediate strategy: distill + persist, no integration when no existing."""
        exp = _make_experience()

        # Simplified pipeline: Phase 2 (Distill) calls LLM once per session.
        # Phase 3 (Integrate) is skipped when existing_memories is empty.
        responses = [
            # Phase 2: Distill
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
        ]
        mock_llm.complete = AsyncMock(side_effect=responses)

        result = await engine.consolidate([exp], [], strategy="immediate")

        assert result.sessions_processed == 1
        assert result.memories_created >= 1
        # Quality score is now algorithmic (not LLM-based)
        assert result.quality_score > 0.0
        assert result.ended_at is not None
        mock_memory_store.add.assert_awaited()

    async def test_consolidate_batch_includes_pattern_detection(
        self, engine, mock_llm, mock_memory_store
    ):
        """Batch strategy: distill + integrate (patterns+contradictions+schemas)."""
        exp1 = _make_experience("sess-1")
        exp2 = _make_experience("sess-2")

        # Simplified pipeline: 2 Distill calls + 1 Integrate call.
        responses = [
            # Phase 2: Distill sess-1
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
            # Phase 2: Distill sess-2
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
            # Phase 3: Integrate (combined patterns + contradictions + schemas)
            {
                "content": json.dumps(
                    {
                        "patterns": [
                            {
                                "pattern": "Agent consistently uses Python.",
                                "frequency": 2,
                                "confidence": 0.9,
                                "memory_kind": "procedural",
                                "tags": ["python"],
                                "importance": 0.8,
                            }
                        ],
                        "contradictions": [],
                        "schemas": [],
                    }
                ),
                "usage": {"total_tokens": 80},
            },
        ]
        mock_llm.complete = AsyncMock(side_effect=responses)

        result = await engine.consolidate([exp1, exp2], [], strategy="batch")

        assert result.sessions_processed == 2
        # 2 learnings from summaries + 1 pattern
        assert result.memories_created >= 3
        # Quality is now algorithmic
        assert result.quality_score > 0.0

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
            # Phase 2: Distill
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
            # Phase 3: Integrate — contradiction detected
            {
                "content": json.dumps(
                    {
                        "patterns": [],
                        "contradictions": [
                            {
                                "new_learning": "Use pandas instead of numpy",
                                "existing_memory_id": "existing-1",
                                "resolution": "keep_new",
                            }
                        ],
                        "schemas": [],
                    }
                ),
                "usage": {"total_tokens": 50},
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
