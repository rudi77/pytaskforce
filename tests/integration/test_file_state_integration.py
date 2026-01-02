"""
Integration tests for FileStateManager

Tests verify:
- Actual filesystem operations
- State persistence across manager instances
- Directory structure creation
- File format compatibility
- Real-world usage patterns
"""

import asyncio
import json

import pytest

from taskforce.infrastructure.persistence.file_state import FileStateManager


@pytest.mark.asyncio
async def test_state_persistence_across_instances(tmp_path):
    """Test that state persists when creating new manager instances."""
    work_dir = str(tmp_path / "agent_work")

    # Create first manager and save state
    manager1 = FileStateManager(work_dir=work_dir)
    state_data = {
        "mission": "Build a web app",
        "todolist_id": "todo-123",
        "answers": {"framework": "FastAPI"}
    }

    success = await manager1.save_state("session-1", state_data)
    assert success is True

    # Create second manager (simulating app restart)
    manager2 = FileStateManager(work_dir=work_dir)

    # Load state with new manager
    loaded = await manager2.load_state("session-1")

    assert loaded is not None
    assert loaded["mission"] == "Build a web app"
    assert loaded["todolist_id"] == "todo-123"
    assert loaded["answers"]["framework"] == "FastAPI"
    assert loaded["_version"] == 1


@pytest.mark.asyncio
async def test_directory_structure_creation(tmp_path):
    """Test that correct directory structure is created."""
    work_dir = tmp_path / "custom_work_dir"

    manager = FileStateManager(work_dir=str(work_dir))

    # Verify directory structure
    assert work_dir.exists()
    assert (work_dir / "states").exists()
    assert (work_dir / "states").is_dir()

    # Save a state and verify file location
    await manager.save_state("test-session", {"data": "test"})

    state_file = work_dir / "states" / "test-session.json"
    assert state_file.exists()
    assert state_file.is_file()


@pytest.mark.asyncio
async def test_json_file_format_compatibility(tmp_path):
    """Test that JSON files are human-readable and properly formatted."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {
        "mission": "Test mission",
        "todolist_id": "abc-123",
        "answers": {"name": "test-project"}
    }

    await manager.save_state("test-session", state_data)

    # Read file directly and verify format
    state_file = tmp_path / "states" / "test-session.json"
    with open(state_file, encoding="utf-8") as f:
        content = f.read()
        data = json.loads(content)

    # Verify it's properly formatted JSON with indentation
    assert "\n" in content  # Has newlines (indented)
    assert "  " in content  # Has indentation

    # Verify structure
    assert data["session_id"] == "test-session"
    assert "timestamp" in data
    assert "state_data" in data
    assert data["state_data"]["mission"] == "Test mission"


@pytest.mark.asyncio
async def test_multiple_sessions_isolation(tmp_path):
    """Test that multiple sessions are properly isolated."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Create multiple sessions
    await manager.save_state("session-1", {"project": "project-1"})
    await manager.save_state("session-2", {"project": "project-2"})
    await manager.save_state("session-3", {"project": "project-3"})

    # Verify each session has its own file
    states_dir = tmp_path / "states"
    assert (states_dir / "session-1.json").exists()
    assert (states_dir / "session-2.json").exists()
    assert (states_dir / "session-3.json").exists()

    # Verify data isolation
    state1 = await manager.load_state("session-1")
    state2 = await manager.load_state("session-2")
    state3 = await manager.load_state("session-3")

    assert state1["project"] == "project-1"
    assert state2["project"] == "project-2"
    assert state3["project"] == "project-3"


@pytest.mark.asyncio
async def test_state_update_workflow(tmp_path):
    """Test realistic state update workflow."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Initial state
    state = {
        "mission": "Build API",
        "todolist_id": None,
        "answers": {},
        "pending_question": "What framework?"
    }
    await manager.save_state("session-1", state)

    # User answers question
    state = await manager.load_state("session-1")
    state["answers"]["framework"] = "FastAPI"
    state["pending_question"] = None
    await manager.save_state("session-1", state)

    # TodoList created
    state = await manager.load_state("session-1")
    state["todolist_id"] = "todo-456"
    await manager.save_state("session-1", state)

    # Verify final state
    final_state = await manager.load_state("session-1")
    assert final_state["mission"] == "Build API"
    assert final_state["todolist_id"] == "todo-456"
    assert final_state["answers"]["framework"] == "FastAPI"
    assert final_state["pending_question"] is None
    assert final_state["_version"] == 3  # 3 saves


@pytest.mark.asyncio
async def test_session_cleanup(tmp_path):
    """Test session deletion and cleanup."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Create multiple sessions
    await manager.save_state("session-1", {"data": "one"})
    await manager.save_state("session-2", {"data": "two"})
    await manager.save_state("session-3", {"data": "three"})

    # Verify all exist
    sessions = await manager.list_sessions()
    assert len(sessions) == 3

    # Delete one session
    await manager.delete_state("session-2")

    # Verify it's gone
    sessions = await manager.list_sessions()
    assert len(sessions) == 2
    assert "session-1" in sessions
    assert "session-2" not in sessions
    assert "session-3" in sessions

    # Verify file is deleted
    state_file = tmp_path / "states" / "session-2.json"
    assert not state_file.exists()


@pytest.mark.asyncio
async def test_large_state_data(tmp_path):
    """Test handling of large state data."""
    manager = FileStateManager(work_dir=str(tmp_path))

    # Create large state with message history
    messages = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(100)
    ]

    state_data = {
        "mission": "Complex task",
        "message_history": messages,
        "answers": {f"key_{i}": f"value_{i}" for i in range(50)}
    }

    # Save and load
    success = await manager.save_state("large-session", state_data)
    assert success is True

    loaded = await manager.load_state("large-session")
    assert loaded is not None
    assert len(loaded["message_history"]) == 100
    assert len(loaded["answers"]) == 50


@pytest.mark.asyncio
async def test_special_characters_in_state(tmp_path):
    """Test handling of special characters and unicode."""
    manager = FileStateManager(work_dir=str(tmp_path))

    state_data = {
        "mission": "Test with special chars: <>&\"'",
        "answers": {
            "name": "Müller",
            "emoji": "🚀 🎉",
            "chinese": "你好世界",
            "json_string": '{"nested": "value"}'
        }
    }

    await manager.save_state("special-session", state_data)
    loaded = await manager.load_state("special-session")

    assert loaded["mission"] == "Test with special chars: <>&\"'"
    assert loaded["answers"]["name"] == "Müller"
    assert loaded["answers"]["emoji"] == "🚀 🎉"
    assert loaded["answers"]["chinese"] == "你好世界"
    assert loaded["answers"]["json_string"] == '{"nested": "value"}'


@pytest.mark.asyncio
async def test_concurrent_sessions(tmp_path):
    """Test concurrent operations on different sessions."""
    manager = FileStateManager(work_dir=str(tmp_path))

    async def create_session(session_id: str, data: str):
        for _i in range(5):
            state = await manager.load_state(session_id)
            if not state:
                state = {"data": data, "count": 0}
            state["count"] = state.get("count", 0) + 1
            await manager.save_state(session_id, state)

    # Run concurrent operations on different sessions
    await asyncio.gather(
        create_session("session-a", "data-a"),
        create_session("session-b", "data-b"),
        create_session("session-c", "data-c")
    )

    # Verify all sessions completed successfully
    state_a = await manager.load_state("session-a")
    state_b = await manager.load_state("session-b")
    state_c = await manager.load_state("session-c")

    assert state_a["count"] == 5
    assert state_b["count"] == 5
    assert state_c["count"] == 5
    assert state_a["data"] == "data-a"
    assert state_b["data"] == "data-b"
    assert state_c["data"] == "data-c"


@pytest.mark.asyncio
async def test_default_work_directory(tmp_path, monkeypatch):
    """Test that default work directory is created in current directory."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create manager with default work_dir
    manager = FileStateManager()

    # Verify default directory structure
    default_dir = tmp_path / ".taskforce"
    assert default_dir.exists()
    assert (default_dir / "states").exists()

    # Verify it works
    await manager.save_state("test", {"data": "test"})
    loaded = await manager.load_state("test")
    assert loaded["data"] == "test"

