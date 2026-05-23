"""
Unit tests for FileToolResultStore implementation.

Tests cover:
- Storing and retrieving tool results
- Handle generation and metadata
- Preview creation
- Session cleanup
- Storage statistics
"""

import tempfile

import pytest

from taskforce.core.domain.tool_result import ToolResultHandle
from taskforce.infrastructure.cache.tool_result_store import FileToolResultStore


@pytest.fixture
async def store():
    """Create a temporary FileToolResultStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileToolResultStore(store_dir=tmpdir)
        yield store


@pytest.mark.asyncio
async def test_put_and_fetch_small_result(store):
    """Test storing and retrieving a small tool result."""
    # Arrange
    tool_name = "test_tool"
    result = {
        "success": True,
        "output": "Test output",
        "data": {"key": "value"},
    }
    session_id = "test_session_1"

    # Act
    handle = await store.put(tool_name, result, session_id)

    # Assert - handle properties
    assert handle.id is not None
    assert handle.tool == tool_name
    assert handle.created_at is not None
    assert handle.size_bytes > 0
    assert handle.size_chars > 0
    assert handle.schema_version == "1.0"
    assert handle.metadata["session_id"] == session_id
    assert handle.metadata["success"] is True

    # Act - fetch result
    fetched = await store.fetch(handle)

    # Assert - fetched result matches original
    assert fetched is not None
    assert fetched["success"] == result["success"]
    assert fetched["output"] == result["output"]
    assert fetched["data"] == result["data"]


@pytest.mark.spec("tools.tool_result_store_returns_handle_with_size")
@pytest.mark.asyncio
async def test_put_large_result(store):
    """Test storing a large tool result."""
    # Arrange
    tool_name = "large_tool"
    large_output = "x" * 100000  # 100k characters
    result = {
        "success": True,
        "output": large_output,
    }

    # Act
    handle = await store.put(tool_name, result, "session_large")

    # Assert
    assert handle.size_chars >= 100000
    assert handle.size_bytes >= 100000

    # Fetch and verify
    fetched = await store.fetch(handle)
    assert fetched is not None
    assert len(fetched["output"]) == 100000


@pytest.mark.asyncio
async def test_fetch_with_max_chars(store):
    """Test fetching with character limit."""
    # Arrange
    result = {
        "success": True,
        "output": "x" * 10000,
    }
    handle = await store.put("test_tool", result, "session_1")

    # Act - fetch with limit
    fetched = await store.fetch(handle, max_chars=1000)

    # Assert - output is truncated
    assert fetched is not None
    assert len(fetched["output"]) < 10000
    assert "TRUNCATED" in fetched["output"]


@pytest.mark.asyncio
async def test_fetch_nonexistent_handle(store):
    """Test fetching a handle that doesn't exist."""
    # Arrange
    fake_handle = ToolResultHandle(
        id="nonexistent-id",
        tool="fake_tool",
        created_at="2024-01-01T00:00:00Z",
        size_bytes=100,
        size_chars=100,
    )

    # Act
    result = await store.fetch(fake_handle)

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_fetch_quarantines_corrupt_file(store):
    """Corrupt JSON is moved aside instead of silently swallowed."""
    handle = await store.put("test_tool", {"success": True, "output": "ok"}, "session_1")
    result_path = store._result_path(handle.id)
    result_path.write_text("{not json", encoding="utf-8")

    # First fetch trips the corruption path and returns None.
    fetched = await store.fetch(handle)
    assert fetched is None

    # The corrupt file has been renamed aside — a subsequent fetch is
    # now an honest "not found", and the bytes survive for forensics.
    assert not result_path.exists()
    quarantined = list(result_path.parent.glob(f"{handle.id}.json.corrupt-*"))
    assert len(quarantined) == 1


@pytest.mark.asyncio
async def test_delete_result(store):
    """Test deleting a stored result."""
    # Arrange
    result = {"success": True, "output": "test"}
    handle = await store.put("test_tool", result, "session_1")

    # Act
    deleted = await store.delete(handle)

    # Assert
    assert deleted is True

    # Verify it's gone
    fetched = await store.fetch(handle)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_nonexistent_result(store):
    """Test deleting a result that doesn't exist."""
    # Arrange
    fake_handle = ToolResultHandle(
        id="nonexistent-id",
        tool="fake_tool",
        created_at="2024-01-01T00:00:00Z",
        size_bytes=100,
        size_chars=100,
    )

    # Act
    deleted = await store.delete(fake_handle)

    # Assert
    assert deleted is False


@pytest.mark.spec("tools.cleanup_session_deletes_only_matching_handles")
@pytest.mark.asyncio
async def test_cleanup_session(store):
    """Test cleaning up all results for a session."""
    # Arrange - create results for multiple sessions
    session_1_results = []
    for i in range(3):
        handle = await store.put(
            f"tool_{i}",
            {"success": True, "output": f"output_{i}"},
            "session_1",
        )
        session_1_results.append(handle)

    session_2_results = []
    for i in range(2):
        handle = await store.put(
            f"tool_{i}",
            {"success": True, "output": f"output_{i}"},
            "session_2",
        )
        session_2_results.append(handle)

    # Act - cleanup session_1
    count = await store.cleanup_session("session_1")

    # Assert
    assert count == 3

    # Verify session_1 results are gone
    for handle in session_1_results:
        fetched = await store.fetch(handle)
        assert fetched is None

    # Verify session_2 results still exist
    for handle in session_2_results:
        fetched = await store.fetch(handle)
        assert fetched is not None


@pytest.mark.asyncio
async def test_get_stats_empty_store(store):
    """Test getting stats from an empty store."""
    # Act
    stats = await store.get_stats()

    # Assert
    assert stats["total_results"] == 0
    assert stats["total_bytes"] == 0
    assert stats["total_mb"] == 0
    assert stats["oldest_result"] is None
    assert stats["newest_result"] is None


@pytest.mark.asyncio
async def test_get_stats_with_results(store):
    """Test getting stats with stored results."""
    # Arrange - store multiple results
    for i in range(5):
        await store.put(
            f"tool_{i}",
            {"success": True, "output": f"output_{i}" * 100},
            f"session_{i}",
        )

    # Act
    stats = await store.get_stats()

    # Assert
    assert stats["total_results"] == 5
    assert stats["total_bytes"] > 0
    assert stats["total_mb"] >= 0  # Can be 0.0 for small results
    assert stats["oldest_result"] is not None
    assert stats["newest_result"] is not None
    assert stats["oldest_result"] <= stats["newest_result"]


@pytest.mark.asyncio
async def test_handle_serialization(store):
    """Test handle to_dict and from_dict methods."""
    # Arrange
    result = {"success": True, "output": "test"}
    handle = await store.put("test_tool", result, "session_1", metadata={"step": 5})

    # Act - serialize and deserialize
    handle_dict = handle.to_dict()
    restored_handle = ToolResultHandle.from_dict(handle_dict)

    # Assert
    assert restored_handle.id == handle.id
    assert restored_handle.tool == handle.tool
    assert restored_handle.created_at == handle.created_at
    assert restored_handle.size_bytes == handle.size_bytes
    assert restored_handle.size_chars == handle.size_chars
    assert restored_handle.schema_version == handle.schema_version
    assert restored_handle.metadata == handle.metadata


@pytest.mark.asyncio
async def test_concurrent_puts(store):
    """Test concurrent put operations."""
    import asyncio

    # Arrange
    async def put_result(i):
        return await store.put(
            f"tool_{i}",
            {"success": True, "output": f"output_{i}"},
            "session_concurrent",
        )

    # Act - concurrent puts
    handles = await asyncio.gather(*[put_result(i) for i in range(10)])

    # Assert - all handles are unique
    handle_ids = [h.id for h in handles]
    assert len(handle_ids) == len(set(handle_ids))  # All unique

    # All results can be fetched
    for handle in handles:
        fetched = await store.fetch(handle)
        assert fetched is not None


@pytest.mark.asyncio
async def test_error_result_storage(store):
    """Test storing tool results with errors."""
    # Arrange
    result = {
        "success": False,
        "error": "Tool execution failed",
        "output": "",
    }

    # Act
    handle = await store.put("failing_tool", result, "session_error")

    # Assert
    assert handle.metadata["success"] is False

    # Fetch and verify
    fetched = await store.fetch(handle)
    assert fetched is not None
    assert fetched["success"] is False
    assert fetched["error"] == "Tool execution failed"



@pytest.mark.asyncio
async def test_store_dir_resolved_to_absolute_path(tmp_path, monkeypatch):
    """Regression: store_dir must be absolute so that paths leaked into
    messages are still findable after CWD changes (e.g. pinchbench
    solver re-resolves agent paths against its temp workspace).
    See per-task post-mortem for ``task_competitive_research`` and
    ``task_oss_alternative_research`` — both failed because the agent
    received a relative ``.taskforce_pinchbench/tool_results/...`` path
    and tried to read it under the workspace, not the cwd."""
    import os
    from pathlib import Path

    relative_dir = Path("./relative_store_test")
    store = FileToolResultStore(store_dir=relative_dir)

    # Store path must be absolute even though we passed a relative one.
    assert store.store_dir.is_absolute(), (
        f"store_dir should be absolute, got {store.store_dir}"
    )
    assert store.results_dir.is_absolute()
    assert store.handles_dir.is_absolute()

    # And _result_path / _handle_path must yield absolute paths too.
    rp = store._result_path("abc")
    hp = store._handle_path("abc")
    assert rp.is_absolute() and hp.is_absolute()

    # Critical guarantee: after a CWD change, the absolute paths still
    # point at the originally-resolved location.
    original_path = str(rp)
    monkeypatch.chdir(tmp_path)
    rp_after = store._result_path("abc")
    assert str(rp_after) == original_path
