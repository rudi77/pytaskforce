"""Integration test for the memory consolidation pipeline.

Tests the full flow: experience capture → persistence → consolidation → memory creation.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from taskforce.application.consolidation_service import ConsolidationService
from taskforce.core.domain.experience import (
    SessionExperience,
    ToolCallExperience,
)
from taskforce.core.domain.memory import MemoryKind, MemoryScope
from taskforce.infrastructure.memory.consolidation_engine import ConsolidationEngine
from taskforce.infrastructure.memory.file_experience_store import FileExperienceStore
from taskforce.infrastructure.memory.file_memory_store import FileMemoryStore


def _make_experience(session_id: str, mission: str) -> SessionExperience:
    exp = SessionExperience(
        session_id=session_id,
        profile="dev",
        mission=mission,
        started_at=datetime.now(UTC),
        total_steps=3,
        final_answer="Done.",
    )
    exp.tool_calls.append(
        ToolCallExperience(
            tool_name="python",
            arguments={"code": "print('hello')"},
            success=True,
            duration_ms=50,
        )
    )
    return exp


@pytest.fixture
def mock_llm():
    """Mock LLM that returns valid consolidation responses."""
    llm = AsyncMock()

    call_count = 0

    async def _complete(**kwargs):
        nonlocal call_count
        call_count += 1

        # Determine which phase based on prompt content
        messages = kwargs.get("messages", [])
        prompt = messages[0]["content"] if messages else ""

        if "Summarize the following agent session" in prompt:
            return {
                "content": json.dumps(
                    {
                        "narrative": f"Session {call_count} completed a Python task.",
                        "key_learnings": [f"Learning from session {call_count}"],
                        "tool_patterns": ["python"],
                        "memory_kind": "procedural",
                    }
                ),
                "usage": {"total_tokens": 100},
            }
        elif "identify recurring patterns" in prompt:
            return {
                "content": json.dumps(
                    [
                        {
                            "pattern": "Agent consistently uses Python for tasks.",
                            "frequency": 2,
                            "confidence": 0.85,
                            "memory_kind": "procedural",
                            "tags": ["python"],
                        }
                    ]
                ),
                "usage": {"total_tokens": 80},
            }
        elif "Compare these new learnings" in prompt:
            return {
                "content": json.dumps({"contradictions": []}),
                "usage": {"total_tokens": 50},
            }
        else:
            # Quality assessment (default)
            return {
                "content": json.dumps({"score": 0.85, "reasoning": "Good coverage"}),
                "usage": {"total_tokens": 30},
            }

    llm.complete = _complete
    return llm


class TestMemoryConsolidationIntegration:
    async def test_full_pipeline(self, tmp_path, mock_llm):
        """End-to-end: save experiences → consolidate → verify memories."""
        exp_dir = tmp_path / "experiences"
        mem_dir = tmp_path / "memory"

        experience_store = FileExperienceStore(exp_dir)
        memory_store = FileMemoryStore(mem_dir)

        # 1. Save two session experiences
        exp1 = _make_experience("sess-1", "Analyze CSV data")
        exp2 = _make_experience("sess-2", "Process JSON files")
        await experience_store.save_experience(exp1)
        await experience_store.save_experience(exp2)

        # Verify experiences are saved
        exps = await experience_store.list_experiences()
        assert len(exps) == 2

        # 2. Create engine and service
        engine = ConsolidationEngine(mock_llm, memory_store)
        service = ConsolidationService(
            experience_store=experience_store,
            consolidation_engine=engine,
            memory_store=memory_store,
            strategy="batch",
        )

        # 3. Run consolidation
        result = await service.trigger_consolidation(strategy="batch")

        assert result.sessions_processed == 2
        assert result.memories_created >= 2
        assert result.quality_score > 0
        assert result.ended_at is not None

        # 4. Verify memories were created in memory store
        memories = await memory_store.list(scope=MemoryScope.USER, kind=MemoryKind.CONSOLIDATED)
        assert len(memories) >= 2

        # Check metadata
        for mem in memories:
            assert mem.metadata.get("source") == "consolidation"
            assert mem.metadata.get("consolidation_id") == result.consolidation_id

        # 5. Verify experiences are marked as processed
        unprocessed = await experience_store.list_experiences(unprocessed_only=True)
        assert len(unprocessed) == 0

        # 6. Verify consolidation history
        history = await experience_store.list_consolidations()
        assert len(history) == 1
        assert history[0].consolidation_id == result.consolidation_id

    async def test_incremental_consolidation(self, tmp_path, mock_llm):
        """Only unprocessed experiences are consolidated."""
        exp_dir = tmp_path / "experiences2"
        mem_dir = tmp_path / "memory2"

        experience_store = FileExperienceStore(exp_dir)
        memory_store = FileMemoryStore(mem_dir)
        engine = ConsolidationEngine(mock_llm, memory_store)
        service = ConsolidationService(
            experience_store=experience_store,
            consolidation_engine=engine,
            memory_store=memory_store,
            strategy="immediate",
        )

        # Save and consolidate first experience
        exp1 = _make_experience("sess-1", "First task")
        await experience_store.save_experience(exp1)
        result1 = await service.trigger_consolidation()
        assert result1.sessions_processed == 1

        # Save a second experience
        exp2 = _make_experience("sess-2", "Second task")
        await experience_store.save_experience(exp2)

        # Second consolidation should only process the new one
        result2 = await service.trigger_consolidation()
        assert result2.sessions_processed == 1
