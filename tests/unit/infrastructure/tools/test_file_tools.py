"""
Unit tests for File Tools

Tests FileReadTool and FileWriteTool functionality.
"""

import pytest
from pathlib import Path

from taskforce.infrastructure.tools.native.file_tools import (
    FileReadTool,
    FileWriteTool,
)


class TestFileReadTool:
    """Test suite for FileReadTool."""

    @pytest.fixture
    def tool(self):
        """Create a FileReadTool instance."""
        return FileReadTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "file_read"
        assert "Read file contents" in tool.description
        assert tool.requires_approval is False

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "encoding" in schema["properties"]
        assert "max_size_mb" in schema["properties"]
        assert "path" in schema["required"]

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, tmp_path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content)

        result = await tool.execute(path=str(test_file))

        assert result["success"] is True
        assert result["content"] == test_content
        assert result["size"] == len(test_content)
        assert "path" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool):
        """Test reading a non-existent file."""
        result = await tool.execute(path="/nonexistent/file.txt")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_file_size_limit(self, tool, tmp_path):
        """Test file size limit enforcement."""
        test_file = tmp_path / "large.txt"
        # Create a file larger than 1MB
        test_file.write_text("x" * (2 * 1024 * 1024))

        result = await tool.execute(path=str(test_file), max_size_mb=1)

        assert result["success"] is False
        assert "too large" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_custom_encoding(self, tool, tmp_path):
        """Test reading file with custom encoding."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content", encoding="ascii")

        result = await tool.execute(path=str(test_file), encoding="ascii")

        assert result["success"] is True
        assert result["content"] == "Test content"

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(path="/test/file.txt")

        assert valid is True
        assert error is None

    def test_validate_params_missing_path(self, tool):
        """Test parameter validation with missing path."""
        valid, error = tool.validate_params()

        assert valid is False
        assert "path" in error


class TestFileWriteTool:
    """Test suite for FileWriteTool."""

    @pytest.fixture
    def tool(self):
        """Create a FileWriteTool instance."""
        return FileWriteTool()

    def test_tool_metadata(self, tool):
        """Test tool metadata properties."""
        assert tool.name == "file_write"
        assert "Write content to file" in tool.description
        assert tool.requires_approval is True

    def test_parameters_schema(self, tool):
        """Test parameter schema structure."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "content" in schema["properties"]
        assert "backup" in schema["properties"]
        assert "path" in schema["required"]
        assert "content" in schema["required"]

    @pytest.mark.asyncio
    async def test_write_new_file(self, tool, tmp_path):
        """Test writing a new file."""
        test_file = tmp_path / "new.txt"
        test_content = "New content"

        result = await tool.execute(path=str(test_file), content=test_content)

        assert result["success"] is True
        assert result["size"] == len(test_content)
        assert test_file.exists()
        assert test_file.read_text() == test_content

    @pytest.mark.asyncio
    async def test_overwrite_existing_file(self, tool, tmp_path):
        """Test overwriting an existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        new_content = "New content"
        result = await tool.execute(path=str(test_file), content=new_content)

        assert result["success"] is True
        assert test_file.read_text() == new_content

    @pytest.mark.asyncio
    async def test_backup_creation(self, tool, tmp_path):
        """Test that backup is created when overwriting."""
        test_file = tmp_path / "test.txt"
        old_content = "Old content"
        test_file.write_text(old_content)

        result = await tool.execute(
            path=str(test_file), content="New content", backup=True
        )

        assert result["success"] is True
        assert result["backed_up"] is True

        backup_file = tmp_path / "test.txt.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == old_content

    @pytest.mark.asyncio
    async def test_no_backup(self, tool, tmp_path):
        """Test writing without backup."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Old content")

        result = await tool.execute(
            path=str(test_file), content="New content", backup=False
        )

        assert result["success"] is True
        assert result["backed_up"] is False

        backup_file = tmp_path / "test.txt.bak"
        assert not backup_file.exists()

    @pytest.mark.asyncio
    async def test_create_parent_directories(self, tool, tmp_path):
        """Test that parent directories are created automatically."""
        test_file = tmp_path / "subdir" / "nested" / "file.txt"

        result = await tool.execute(path=str(test_file), content="Content")

        assert result["success"] is True
        assert test_file.exists()
        assert test_file.read_text() == "Content"

    def test_validate_params_success(self, tool):
        """Test parameter validation with valid params."""
        valid, error = tool.validate_params(path="/test.txt", content="test")

        assert valid is True
        assert error is None

    def test_validate_params_missing_path(self, tool):
        """Test parameter validation with missing path."""
        valid, error = tool.validate_params(content="test")

        assert valid is False
        assert "path" in error

    def test_validate_params_missing_content(self, tool):
        """Test parameter validation with missing content."""
        valid, error = tool.validate_params(path="/test.txt")

        assert valid is False
        assert "content" in error

