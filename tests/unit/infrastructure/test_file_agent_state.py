"""Tests for FileAgentState — singleton agent state persistence."""

import pytest

from taskforce.infrastructure.persistence.file_agent_state import FileAgentState


class TestFileAgentState:
    @pytest.fixture
    def state_manager(self, tmp_path):
        return FileAgentState(work_dir=str(tmp_path))

    async def test_save_and_load(self, state_manager):
        await state_manager.save({"active_conversations": ["abc"]})
        loaded = await state_manager.load()
        assert loaded is not None
        assert loaded["active_conversations"] == ["abc"]
        assert loaded["_version"] == 1

    async def test_load_returns_none_when_empty(self, state_manager):
        result = await state_manager.load()
        assert result is None

    async def test_version_increments(self, state_manager):
        await state_manager.save({"key": "v1"})
        loaded = await state_manager.load()
        assert loaded["_version"] == 1

        await state_manager.save(loaded)
        loaded2 = await state_manager.load()
        assert loaded2["_version"] == 2

    async def test_overwrite_state(self, state_manager):
        await state_manager.save({"a": 1})
        await state_manager.save({"b": 2})
        loaded = await state_manager.load()
        assert "b" in loaded
        # "a" should not be present since it's a full overwrite.
        assert "a" not in loaded
