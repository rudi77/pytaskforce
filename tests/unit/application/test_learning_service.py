"""Tests for LearningService."""

import pytest
from unittest.mock import AsyncMock

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.application.learning_service import LearningService


class TestLearningService:
    """Tests for the LearningService."""

    @pytest.fixture
    def mock_memory_store(self) -> AsyncMock:
        store = AsyncMock()
        store.add = AsyncMock(side_effect=lambda r: r)
        store.search = AsyncMock(return_value=[])
        store.list = AsyncMock(return_value=[])
        store.delete = AsyncMock(return_value=True)
        return store

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        llm = AsyncMock()
        llm.complete = AsyncMock(
            return_value={
                "content": '[{"kind": "preference", "content": "User prefers Python", "tags": ["coding"]}]'
            }
        )
        return llm

    @pytest.fixture
    def service(self, mock_memory_store: AsyncMock, mock_llm: AsyncMock) -> LearningService:
        return LearningService(
            memory_store=mock_memory_store,
            llm_provider=mock_llm,
            auto_extract=True,
        )

    async def test_extract_learnings(
        self, service: LearningService, mock_llm: AsyncMock
    ) -> None:
        conversation = [
            {"role": "user", "content": "I prefer Python with type hints"},
            {"role": "assistant", "content": "Noted, I'll use type hints in Python code."},
        ]
        records = await service.extract_learnings(
            conversation=conversation,
            session_context={"session_id": "test-session", "profile": "dev"},
        )
        assert len(records) == 1
        assert records[0].kind == MemoryKind.PREFERENCE
        assert "Python" in records[0].content
        assert "coding" in records[0].tags

    async def test_extract_learnings_disabled(self, mock_memory_store: AsyncMock) -> None:
        service = LearningService(
            memory_store=mock_memory_store,
            llm_provider=AsyncMock(),
            auto_extract=False,
        )
        records = await service.extract_learnings(
            conversation=[{"role": "user", "content": "test"}],
            session_context={},
        )
        assert records == []

    async def test_extract_learnings_short_conversation(
        self, service: LearningService
    ) -> None:
        records = await service.extract_learnings(
            conversation=[{"role": "user", "content": "hi"}],
            session_context={},
        )
        assert records == []

    async def test_extract_learnings_empty_response(
        self, service: LearningService, mock_llm: AsyncMock
    ) -> None:
        mock_llm.complete.return_value = {"content": "[]"}
        records = await service.extract_learnings(
            conversation=[
                {"role": "user", "content": "What time is it?"},
                {"role": "assistant", "content": "I don't have real-time clock access."},
            ],
            session_context={},
        )
        assert records == []

    async def test_extract_learnings_llm_error(
        self, service: LearningService, mock_llm: AsyncMock
    ) -> None:
        mock_llm.complete.side_effect = Exception("LLM error")
        records = await service.extract_learnings(
            conversation=[
                {"role": "user", "content": "test"},
                {"role": "assistant", "content": "response"},
            ],
            session_context={},
        )
        assert records == []

    async def test_enrich_context(
        self, service: LearningService, mock_memory_store: AsyncMock
    ) -> None:
        pref = MemoryRecord(
            scope=MemoryScope.USER,
            kind=MemoryKind.PREFERENCE,
            content="User prefers Python",
        )
        mock_memory_store.list.return_value = [pref]
        mock_memory_store.search.return_value = []

        results = await service.enrich_context(
            mission="Write a Python script",
            user_id="user-1",
        )
        assert len(results) >= 1
        assert any("Python" in r.content for r in results)

    async def test_compact_memories_no_llm(self, mock_memory_store: AsyncMock) -> None:
        service = LearningService(
            memory_store=mock_memory_store,
            llm_provider=None,
        )
        count = await service.compact_memories(MemoryScope.USER, max_age_days=30)
        assert count == 0

    def test_extract_keywords(self, service: LearningService) -> None:
        keywords = service._extract_keywords("Write a Python script for data analysis")
        assert "python" in keywords
        assert "script" in keywords
        assert "analysis" in keywords
        # Stop words should be excluded
        assert "for" not in keywords
        assert "a" not in keywords

    def test_parse_extraction_valid(self, service: LearningService) -> None:
        result = service._parse_extraction(
            '[{"kind": "preference", "content": "test", "tags": []}]'
        )
        assert len(result) == 1

    def test_parse_extraction_invalid(self, service: LearningService) -> None:
        result = service._parse_extraction("not json at all")
        assert result == []

    def test_parse_extraction_with_surrounding_text(self, service: LearningService) -> None:
        result = service._parse_extraction(
            'Here are the results:\n[{"content": "test"}]\nDone.'
        )
        assert len(result) == 1
