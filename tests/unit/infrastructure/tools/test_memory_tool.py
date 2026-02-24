"""Unit tests for MemoryTool.

Tests memory CRUD operations, validation, and dispatching.
"""

from unittest.mock import AsyncMock, patch

import pytest

from taskforce.core.domain.memory import MemoryKind, MemoryRecord, MemoryScope
from taskforce.core.interfaces.tools import ApprovalRiskLevel
from taskforce.infrastructure.tools.native.memory_tool import MemoryTool


@pytest.fixture
def mock_store() -> AsyncMock:
    """Create a mock FileMemoryStore."""
    store = AsyncMock()
    store.add = AsyncMock()
    store.get = AsyncMock()
    store.list = AsyncMock(return_value=[])
    store.search = AsyncMock(return_value=[])
    store.update = AsyncMock()
    store.delete = AsyncMock()
    return store


@pytest.fixture
def tool(mock_store: AsyncMock, tmp_path) -> MemoryTool:
    """Create a MemoryTool with a mocked store."""
    with patch(
        "taskforce.infrastructure.tools.native.memory_tool.FileMemoryStore",
        return_value=mock_store,
    ):
        t = MemoryTool(store_dir=str(tmp_path / "memory"))
    return t


@pytest.fixture
def sample_record() -> MemoryRecord:
    """Create a sample memory record for testing."""
    return MemoryRecord(
        scope=MemoryScope.USER,
        kind=MemoryKind.LONG_TERM,
        content="Test memory content",
        tags=["test", "sample"],
        metadata={"source": "unit_test"},
    )


class TestMemoryToolMetadata:
    """Test MemoryTool metadata properties."""

    def test_name(self, tool: MemoryTool) -> None:
        assert tool.name == "memory"

    def test_description(self, tool: MemoryTool) -> None:
        desc = tool.description.lower()
        assert "memory" in desc

    def test_parameters_schema(self, tool: MemoryTool) -> None:
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "action" in schema["properties"]
        assert schema["required"] == ["action"]
        actions = schema["properties"]["action"]["enum"]
        assert "add" in actions
        assert "get" in actions
        assert "list" in actions
        assert "search" in actions
        assert "update" in actions
        assert "delete" in actions

    def test_requires_approval(self, tool: MemoryTool) -> None:
        assert tool.requires_approval is False

    def test_approval_risk_level(self, tool: MemoryTool) -> None:
        assert tool.approval_risk_level == ApprovalRiskLevel.LOW

    def test_supports_parallelism(self, tool: MemoryTool) -> None:
        assert tool.supports_parallelism is False


class TestMemoryToolAddAction:
    """Test the 'add' action."""

    async def test_add_record(
        self, tool: MemoryTool, mock_store: AsyncMock, sample_record: MemoryRecord
    ) -> None:
        mock_store.add.return_value = sample_record
        result = await tool.execute(
            action="add",
            scope="user",
            kind="long_term",
            content="Test memory content",
            tags=["test", "sample"],
            metadata={"source": "unit_test"},
        )
        assert result["success"] is True
        assert "record" in result
        assert result["record"]["content"] == "Test memory content"
        mock_store.add.assert_called_once()

    async def test_add_missing_required_field(self, tool: MemoryTool) -> None:
        with pytest.raises(ValueError, match="scope"):
            await tool.execute(action="add", kind="long_term", content="no scope")


class TestMemoryToolGetAction:
    """Test the 'get' action."""

    async def test_get_existing_record(
        self, tool: MemoryTool, mock_store: AsyncMock, sample_record: MemoryRecord
    ) -> None:
        mock_store.get.return_value = sample_record
        result = await tool.execute(action="get", record_id=sample_record.id)
        assert result["success"] is True
        assert result["record"]["id"] == sample_record.id
        mock_store.get.assert_called_once_with(sample_record.id)

    async def test_get_nonexistent_record(
        self, tool: MemoryTool, mock_store: AsyncMock
    ) -> None:
        mock_store.get.return_value = None
        result = await tool.execute(action="get", record_id="nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestMemoryToolListAction:
    """Test the 'list' action."""

    async def test_list_records(
        self, tool: MemoryTool, mock_store: AsyncMock, sample_record: MemoryRecord
    ) -> None:
        mock_store.list.return_value = [sample_record]
        result = await tool.execute(action="list", scope="user")
        assert result["success"] is True
        assert len(result["records"]) == 1

    async def test_list_empty(self, tool: MemoryTool, mock_store: AsyncMock) -> None:
        mock_store.list.return_value = []
        result = await tool.execute(action="list")
        assert result["success"] is True
        assert result["records"] == []


class TestMemoryToolSearchAction:
    """Test the 'search' action."""

    async def test_search_with_results(
        self, tool: MemoryTool, mock_store: AsyncMock, sample_record: MemoryRecord
    ) -> None:
        mock_store.search.return_value = [sample_record]
        result = await tool.execute(action="search", query="test")
        assert result["success"] is True
        assert len(result["records"]) == 1
        mock_store.search.assert_called_once()

    async def test_search_with_filters(
        self, tool: MemoryTool, mock_store: AsyncMock
    ) -> None:
        mock_store.search.return_value = []
        await tool.execute(
            action="search", query="test", scope="user", kind="long_term", limit=5
        )
        call_kwargs = mock_store.search.call_args.kwargs
        assert call_kwargs["query"] == "test"
        assert call_kwargs["scope"] == MemoryScope.USER
        assert call_kwargs["kind"] == MemoryKind.LONG_TERM
        assert call_kwargs["limit"] == 5


class TestMemoryToolUpdateAction:
    """Test the 'update' action."""

    async def test_update_record(
        self, tool: MemoryTool, mock_store: AsyncMock, sample_record: MemoryRecord
    ) -> None:
        mock_store.update.return_value = sample_record
        result = await tool.execute(
            action="update",
            record_id=sample_record.id,
            scope="user",
            kind="long_term",
            content="Updated content",
        )
        assert result["success"] is True
        mock_store.update.assert_called_once()


class TestMemoryToolDeleteAction:
    """Test the 'delete' action."""

    async def test_delete_existing_record(
        self, tool: MemoryTool, mock_store: AsyncMock
    ) -> None:
        mock_store.delete.return_value = True
        result = await tool.execute(action="delete", record_id="abc123")
        assert result["success"] is True
        assert result["deleted"] is True

    async def test_delete_nonexistent_record(
        self, tool: MemoryTool, mock_store: AsyncMock
    ) -> None:
        mock_store.delete.return_value = False
        result = await tool.execute(action="delete", record_id="nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestMemoryToolUnknownAction:
    """Test unknown action handling."""

    async def test_unknown_action(self, tool: MemoryTool) -> None:
        result = await tool.execute(action="invalid_action")
        assert result["success"] is False
        assert "unknown" in result["error"].lower()
