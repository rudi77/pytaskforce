"""
Unit tests for FileStateManager

Tests verify:
- State save/load operations
- Session listing
- State deletion
- Versioning behavior
- Atomic writes
- Concurrent access safety
- Error handling
"""

import asyncio
import json

import pytest

from taskforce.infrastructure.persistence.file_state import FileStateManager


@pytest.mark.asyncio
async def test_save_and_load_state(tmp_path):
    """Test basic save and load operations."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {
        "mission": "Test mission",
        "status": "in_progress",
        "answers": {"project_name": "test-project"}
    }

    # Save state
    success = await manager.save_state("test-session", state_data)
    assert success is True

    # Verify version was added
    assert state_data["_version"] == 1
    assert "_updated_at" in state_data

    # Load state
    loaded = await manager.load_state("test-session")
    assert loaded is not None
    assert loaded["mission"] == "Test mission"
    assert loaded["status"] == "in_progress"
    assert loaded["answers"]["project_name"] == "test-project"
    assert loaded["_version"] == 1


@pytest.mark.asyncio
async def test_load_nonexistent_session(tmp_path):
    """Test loading a session that doesn't exist returns empty dict."""
    manager = FileStateManager(work_dir=str(tmp_path))

    loaded = await manager.load_state("nonexistent-session")
    assert loaded == {}


@pytest.mark.asyncio
async def test_state_versioning(tmp_path):
    """Test that version increments on each save."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {"mission": "Test"}

    # First save
    await manager.save_state("test-session", state_data)
    assert state_data["_version"] == 1

    # Second save
    await manager.save_state("test-session", state_data)
    assert state_data["_version"] == 2

    # Third save
    await manager.save_state("test-session", state_data)
    assert state_data["_version"] == 3

    # Verify loaded state has latest version
    loaded = await manager.load_state("test-session")
    assert loaded["_version"] == 3


@pytest.mark.asyncio
async def test_list_sessions(tmp_path):
    """Test listing all sessions."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Initially empty
    sessions = await manager.list_sessions()
    assert sessions == []

    # Create multiple sessions
    await manager.save_state("session-1", {"data": "one"})
    await manager.save_state("session-2", {"data": "two"})
    await manager.save_state("session-3", {"data": "three"})

    # List sessions
    sessions = await manager.list_sessions()
    assert len(sessions) == 3
    assert "session-1" in sessions
    assert "session-2" in sessions
    assert "session-3" in sessions

    # Verify sorted order
    assert sessions == sorted(sessions)


@pytest.mark.asyncio
async def test_delete_state(tmp_path):
    """Test deleting session state."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Create a session
    await manager.save_state("test-session", {"data": "test"})

    # Verify it exists
    loaded = await manager.load_state("test-session")
    assert loaded is not None

    # Delete it
    await manager.delete_state("test-session")

    # Verify it's gone
    loaded = await manager.load_state("test-session")
    assert loaded == {}

    # Verify not in session list
    sessions = await manager.list_sessions()
    assert "test-session" not in sessions


@pytest.mark.asyncio
async def test_delete_nonexistent_state(tmp_path):
    """Test that deleting nonexistent state doesn't raise error."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Should not raise exception
    await manager.delete_state("nonexistent-session")


@pytest.mark.asyncio
async def test_atomic_write(tmp_path):
    """Test that writes are atomic (no partial writes)."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {"mission": "Test", "large_data": "x" * 10000}

    # Save state
    success = await manager.save_state("test-session", state_data)
    assert success is True

    # Verify no .tmp file left behind
    tmp_files = list(manager.states_dir.glob("*.tmp"))
    assert len(tmp_files) == 0

    # Verify state file exists and is valid JSON
    state_file = manager.states_dir / "test-session.json"
    assert state_file.exists()

    with open(state_file, encoding="utf-8") as f:
        content = json.load(f)
        assert content["session_id"] == "test-session"
        assert "state_data" in content


@pytest.mark.asyncio
async def test_concurrent_writes(tmp_path):
    """Test that concurrent writes to same session don't corrupt files."""
    manager = FileStateManager(work_dir=str(tmp_path))

    async def write_state(value: int):
        state_data = {"value": value}
        await manager.save_state("test-session", state_data)

    # Perform concurrent writes
    await asyncio.gather(
        write_state(1),
        write_state(2),
        write_state(3),
        write_state(4),
        write_state(5)
    )

    # Load final state
    loaded = await manager.load_state("test-session")

    # Lock ensures no file corruption - should successfully load
    assert loaded is not None
    assert "value" in loaded

    # Should have one of the values (last write wins)
    assert loaded["value"] in [1, 2, 3, 4, 5]

    # Each write had version 1 (no read-modify-write pattern)
    # Lock prevents corruption, not race conditions in application logic
    assert loaded["_version"] == 1


@pytest.mark.asyncio
async def test_state_file_format(tmp_path):
    """Test that state file has correct JSON format."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {
        "todolist_id": "abc-123",
        "answers": {"name": "test"},
        "pending_question": None
    }

    await manager.save_state("test-session", state_data)

    # Read file directly
    state_file = manager.states_dir / "test-session.json"
    with open(state_file, encoding="utf-8") as f:
        content = json.load(f)

    # Verify structure
    assert "session_id" in content
    assert content["session_id"] == "test-session"
    assert "timestamp" in content
    assert "state_data" in content

    # Verify state_data contents
    state = content["state_data"]
    assert state["todolist_id"] == "abc-123"
    assert state["answers"]["name"] == "test"
    assert state["pending_question"] is None
    assert "_version" in state
    assert "_updated_at" in state


@pytest.mark.asyncio
async def test_work_dir_creation(tmp_path):
    """Test that work directory is created if it doesn't exist."""
    work_dir = tmp_path / "new_work_dir"
    assert not work_dir.exists()

    manager = FileStateManager(work_dir=str(work_dir))

    # Verify directories were created
    assert work_dir.exists()
    assert manager.states_dir.exists()
    assert manager.states_dir == work_dir / "states"


@pytest.mark.asyncio
async def test_empty_state_data(tmp_path):
    """Test saving and loading empty state."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {}
    success = await manager.save_state("test-session", state_data)
    assert success is True

    loaded = await manager.load_state("test-session")
    assert loaded is not None
    assert "_version" in loaded
    assert "_updated_at" in loaded


@pytest.mark.asyncio
async def test_complex_state_data(tmp_path):
    """Test saving and loading complex nested state data."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {
        "todolist_id": "abc-123",
        "answers": {
            "project_name": "test-project",
            "features": ["auth", "api", "ui"],
            "config": {
                "debug": True,
                "port": 8000
            }
        },
        "message_history": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ],
        "pending_question": {
            "question": "What port?",
            "context": "Server configuration"
        }
    }

    await manager.save_state("test-session", state_data)
    loaded = await manager.load_state("test-session")

    # Verify all nested data preserved
    assert loaded["todolist_id"] == "abc-123"
    assert loaded["answers"]["project_name"] == "test-project"
    assert loaded["answers"]["features"] == ["auth", "api", "ui"]
    assert loaded["answers"]["config"]["debug"] is True
    assert loaded["answers"]["config"]["port"] == 8000
    assert len(loaded["message_history"]) == 2
    assert loaded["pending_question"]["question"] == "What port?"


@pytest.mark.asyncio
async def test_protocol_compliance(tmp_path):
    """Test that FileStateManager implements StateManagerProtocol."""

    manager = FileStateManager(work_dir=str(tmp_path))

    # Verify all protocol methods exist and are callable
    assert hasattr(manager, "save_state")
    assert hasattr(manager, "load_state")
    assert hasattr(manager, "delete_state")
    assert hasattr(manager, "list_sessions")

    # Verify methods are async
    assert asyncio.iscoroutinefunction(manager.save_state)
    assert asyncio.iscoroutinefunction(manager.load_state)
    assert asyncio.iscoroutinefunction(manager.delete_state)
    assert asyncio.iscoroutinefunction(manager.list_sessions)

